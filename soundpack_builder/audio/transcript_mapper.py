"""
Transcript-driven event recommendation for character sound packs.

This module is intentionally conservative: if transcription is unavailable or weak,
it falls back to filename-based signals and deterministic ordering.
"""

from __future__ import annotations

import gc
import json
import os
import re
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

try:
    from typing import Literal
except ImportError:  # Python < 3.8
    from typing_extensions import Literal

from soundpack_builder.core.config import hf_token
from soundpack_builder.core.hook_events import EVENT_TARGET_COUNTS, HOOK_EVENT_ORDER

# Backwards-compatible name for hook event iteration order.
EVENT_ORDER: List[str] = list(HOOK_EVENT_ORDER)


def resolve_classifier_device(spec: str) -> Optional[str]:
    """
    Map CLI values ``auto`` / ``cpu`` / ``cuda`` / ``cuda:N`` to a concrete torch-style
    device string, or ``None`` to let Hugging Face pick defaults.
    """
    s = (spec or "auto").strip().lower()
    if s in ("auto", ""):
        return None
    if s == "cpu":
        return "cpu"
    if s.startswith("cuda"):
        try:
            import torch
        except ImportError:
            return None
        if not torch.cuda.is_available():
            return None
        if s == "cuda":
            return "cuda:0"
        return spec.strip()
    return None


def _transformers_pipeline_device_arg(resolved: Optional[str]) -> Optional[int]:
    """``transformers.pipeline`` uses int device index (-1 = CPU)."""
    if resolved is None:
        return None
    if resolved == "cpu":
        return -1
    if resolved.startswith("cuda:"):
        try:
            return int(resolved.split(":", 1)[1])
        except ValueError:
            return 0
    return None


def classifier_runs_on_cpu(classifier_device: str) -> bool:
    """
    Return True when inference is expected to run on CPU (no usable CUDA, or ``--classifier-device cpu``).

    Used to pick a smaller default zero-shot NLI checkpoint on CPU-only machines.
    """
    try:
        import torch

        cuda_ok = bool(torch.cuda.is_available())
    except Exception:
        cuda_ok = False
    spec = (classifier_device or "auto").strip().lower()
    if spec == "cpu":
        return True
    if spec.startswith("cuda"):
        return not cuda_ok
    return not cuda_ok


def default_zero_shot_model_for_classifier_device(classifier_device: str) -> str:
    """Prefer a compact DistilBERT MNLI model on CPU; DistilBART when a GPU is used."""
    return (
        DEFAULT_ZERO_SHOT_MODEL_CPU
        if classifier_runs_on_cpu(classifier_device)
        else DEFAULT_ZERO_SHOT_MODEL
    )


def _zero_shot_safe_premise(tokenizer: Any, text: str) -> Optional[str]:
    """
    Return premise text for NLI, or None if it should be skipped.

    Invisible / zero-width characters can tokenize to an empty sequence; combined with
    SDPA attention on Windows CPU that has triggered native int divide-by-zero in torch.
    """
    t = text.strip()
    if not t:
        return None
    t = re.sub(r"[\u200b-\u200f\uFEFF]", "", t)
    t = t.strip()
    if not t:
        return None
    ids = tokenizer.encode(t, add_special_tokens=False, truncation=False)
    if not ids:
        return None
    return t


def _zero_shot_pipeline_model_kwargs() -> Dict[str, Any]:
    """Avoid SDPA path (scaled_dot_product_attention) which can crash on Windows CPU; use float32."""
    try:
        import torch
    except Exception:
        return {"attn_implementation": "eager"}
    return {"attn_implementation": "eager", "torch_dtype": torch.float32}


# Default Hugging Face models for transcript → hook-event scoring (downloader `--classifier-backend`).
# DistilBART NLI is a good default when CUDA is available; DistilBERT MNLI is smaller and faster on CPU.
DEFAULT_ZERO_SHOT_MODEL = "valhalla/distilbart-mnli-12-1"
DEFAULT_ZERO_SHOT_MODEL_CPU = "typeform/distilbert-base-uncased-mnli"
DEFAULT_SENTENCE_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

ClassifierBackend = Literal["zero-shot", "sentence-embedding"]

EVENT_LABEL_DESCRIPTIONS = {
    "beforeSubmitPrompt": "A short confirmation or ready-to-start prompt before taking action.",
    "afterAgentThought": "A reflective or thinking-style utterance after internal reasoning.",
    "afterAgentResponse": "A completion or response-style utterance after delivering an answer.",
    "preToolUse": "A short action-start cue before running a tool.",
    "postToolUse": "A success or completion cue after a tool finishes successfully.",
    "postToolUseFailure": "A failure or error cue after a tool run fails.",
    "stop": "A stop, halt, cancel, or interruption cue.",
}


def _transcript_text_for_embedding_compare(transcript: str) -> str:
    """Embedding input for the WAV transcription side of similarity scoring."""
    return f'Transcribed line from the audio clip: "{transcript.strip()}"'


def _hook_event_criteria_for_embedding(event: str) -> str:
    """Embedding input: natural-language definition of which utterances fit this hook type."""
    return (
        f'Cursor hook "{event}". A spoken line fits this hook if it sounds like: '
        f"{EVENT_LABEL_DESCRIPTIONS[event]}"
    )


EVENT_KEYWORDS = {
    "beforeSubmitPrompt": [
        "yes",
        "ready",
        "ok",
        "okay",
        "go",
        "lets go",
        "let's go",
        "hmm",
        "what",
        "well",
    ],
    "afterAgentThought": [
        "hmm",
        "thinking",
        "wait",
        "uh",
        "huh",
        "hmmm",
        "what",
        "consider",
    ],
    "afterAgentResponse": [
        "done",
        "finished",
        "there",
        "here",
        "answer",
        "got it",
        "sure",
        "yes",
        "all right",
    ],
    "preToolUse": ["go", "work", "on it", "do it", "start", "ready"],
    "postToolUse": ["done", "finished", "complete", "success", "worked", "nice"],
    "postToolUseFailure": ["no", "can't", "cannot", "failed", "fail", "wrong", "error"],
    "stop": ["stop", "wait", "halt", "hold", "enough", "quiet"],
}

# Tiny weight so Tier A ties on modelScore break on heuristic filename/text signals.
HEURISTIC_TIEBREAK_EPSILON = 0.05

FILENAME_HINTS = {
    "beforeSubmitPrompt": ["ready", "what", "yes", "go", "confirm"],
    "afterAgentThought": ["what", "think", "hmm", "question", "ponder"],
    "afterAgentResponse": ["yes", "ok", "ready", "affirm", "reply"],
    "preToolUse": ["warcry", "go", "start", "ready", "yesattack"],
    "postToolUse": ["yes", "done", "complete", "success", "ready"],
    "postToolUseFailure": ["no", "fail", "error", "wrong", "angry"],
    "stop": ["stop", "wait", "halt", "quiet"],
}


@dataclass(frozen=True)
class ClipSignal:
    filename: str
    transcript: str
    reason: str


# Whisper often wraps non-speech in square brackets; strip before lexical checks.
_WHISPER_BRACKET_SEGMENT = re.compile(r"\[[^\]]*\]")


def speech_eligibility(transcript: str) -> tuple[bool, str]:
    """
    Return (eligible, reason). ``reason`` is ``ok`` when the transcript is kept for
    recommended-config mapping; otherwise a stable machine-readable code:

    - ``empty`` — blank / whitespace only
    - ``noise_or_music_markers`` — only bracket/noise annotations, nothing lexical left
    - ``non_lexical_only`` — text remains but no word-like token (2+ letters)
    """
    if transcript is None:
        return False, "empty"
    raw = transcript.strip()
    if not raw:
        return False, "empty"
    stripped = _WHISPER_BRACKET_SEGMENT.sub(" ", raw)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    if not stripped:
        return False, "noise_or_music_markers"
    if re.search(r"[^\W\d_]{2,}", stripped, re.UNICODE):
        return True, "ok"
    return False, "non_lexical_only"


def partition_clips_by_speech(
    audio_paths: Sequence[Path],
    transcripts: Dict[Path, str],
) -> tuple[List[Path], List[Dict[str, Any]]]:
    """
    Split WAV paths into eligible (lexical speech) vs excluded rows for reporting.

    ``transcripts`` should contain every path in ``audio_paths`` (missing keys treated
    as empty).
    """
    eligible: List[Path] = []
    excluded: List[Dict[str, Any]] = []
    for p in sorted(audio_paths, key=lambda x: x.name.lower()):
        tx = transcripts.get(p, "") or ""
        ok, reason = speech_eligibility(tx)
        if ok:
            eligible.append(p)
        else:
            excluded.append({"file": p.name, "reason": reason, "transcript": tx})
    return eligible, excluded


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def _filename_tokens(filename: str) -> str:
    stem = Path(filename).stem.lower()
    return re.sub(r"[^a-z0-9]+", " ", stem).strip()


def _score_event(event_name: str, transcript: str, filename: str) -> float:
    text = _normalize_text(transcript)
    filename_text = _filename_tokens(filename)
    score = 0.0

    for kw in EVENT_KEYWORDS.get(event_name, []):
        if kw in text:
            score += 3.0 if len(kw) > 3 else 2.0
    for hint in FILENAME_HINTS.get(event_name, []):
        if hint in filename_text:
            score += 1.0

    # Slight preference for shorter "prompt-like" clips in events that are often concise.
    if event_name in {"preToolUse", "postToolUse", "postToolUseFailure", "stop"}:
        word_count = len(text.split()) if text else 0
        if 0 < word_count <= 5:
            score += 0.5
    return score


def _clip_uses_model_ranking(
    clip_path: Path, transcript: str, classifier_map: Dict[Path, Dict[str, float]]
) -> bool:
    """Tier A: non-empty transcript and classifier produced a non-empty score dict for this clip."""
    return bool(transcript.strip()) and bool(classifier_map.get(clip_path))


def _merged_ranking_for_event(
    event_name: str,
    clips: List[Path],
    transcript_map: Dict[Path, str],
    classifier_map: Dict[Path, Dict[str, float]],
) -> List[tuple[str, str]]:
    """
    Return (clip_name, transcript) pairs in selection order: Tier A (model) then Tier B (heuristic).
    """
    clip_metrics: List[tuple[Path, str, str, float, float]] = []
    for clip_path in clips:
        transcript = transcript_map.get(clip_path, "")
        heuristic_score = _score_event(event_name, transcript, clip_path.name)
        model_score = classifier_map.get(clip_path, {}).get(event_name, 0.0)
        clip_metrics.append((clip_path, transcript, clip_path.name, heuristic_score, model_score))

    max_heuristic = max((item[3] for item in clip_metrics), default=0.0)

    tier_a: List[tuple[str, str, float, float]] = []
    tier_b: List[tuple[str, str, float, float]] = []
    for clip_path, transcript, clip_name, heuristic_score, model_score in clip_metrics:
        heuristic_normalized = (heuristic_score / max_heuristic) if max_heuristic > 0 else 0.0
        row = (clip_name, transcript, heuristic_normalized, model_score)
        if _clip_uses_model_ranking(clip_path, transcript, classifier_map):
            tier_a.append(row)
        else:
            tier_b.append(row)

    tier_a.sort(key=lambda r: (-r[3], -r[2], r[0].lower()))
    tier_b.sort(key=lambda r: (-r[2], r[0].lower()))

    out: List[tuple[str, str]] = []
    for clip_name, transcript, _h, _m in tier_a:
        out.append((clip_name, transcript))
    for clip_name, transcript, _h, _m in tier_b:
        out.append((clip_name, transcript))
    return out


def _report_score_for_candidate(
    *,
    use_model_tier: bool,
    model_score: float,
    heuristic_normalized: float,
    classifier_weight: float,
) -> float:
    if use_model_tier:
        return (model_score * classifier_weight) + (HEURISTIC_TIEBREAK_EPSILON * heuristic_normalized)
    return heuristic_normalized


def _expand_event_slots() -> List[str]:
    return [ev for ev in HOOK_EVENT_ORDER for _ in range(EVENT_TARGET_COUNTS[ev])]


def _max_heuristic_by_event(clips: List[Path], transcript_map: Dict[Path, str]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for event_name in HOOK_EVENT_ORDER:
        out[event_name] = max(
            (_score_event(event_name, transcript_map.get(p, ""), p.name) for p in clips),
            default=0.0,
        )
    return out


def _pair_blended_score(
    clip_path: Path,
    event_name: str,
    *,
    transcript_map: Dict[Path, str],
    classifier_map: Dict[Path, Dict[str, float]],
    max_heuristic: Dict[str, float],
    classifier_weight: float,
    clip_boost: Dict[Path, float],
) -> float:
    transcript = transcript_map.get(clip_path, "")
    h = _score_event(event_name, transcript, clip_path.name)
    mh = max_heuristic.get(event_name, 0.0)
    h_norm = (h / mh) if mh > 0 else 0.0
    model_score = classifier_map.get(clip_path, {}).get(event_name, 0.0)
    use_model = _clip_uses_model_ranking(clip_path, transcript, classifier_map)
    base = _report_score_for_candidate(
        use_model_tier=use_model,
        model_score=model_score,
        heuristic_normalized=h_norm,
        classifier_weight=classifier_weight,
    )
    return base + clip_boost.get(clip_path, 0.0)


def _global_event_assignment(
    clips: List[Path],
    transcript_map: Dict[Path, str],
    classifier_map: Dict[Path, Dict[str, float]],
    classifier_weight: float,
    clip_boost: Dict[Path, float],
) -> Dict[str, List[str]]:
    """Assign each WAV to at most one hook slot; maximize blended scores (greedy)."""
    slots = _expand_event_slots()
    recommendations: Dict[str, List[str]] = {e: [] for e in HOOK_EVENT_ORDER}
    if not clips:
        return recommendations

    max_h = _max_heuristic_by_event(clips, transcript_map)
    triples: List[Tuple[float, int, int]] = []
    for si, event_name in enumerate(slots):
        for ci, clip_path in enumerate(clips):
            s = _pair_blended_score(
                clip_path,
                event_name,
                transcript_map=transcript_map,
                classifier_map=classifier_map,
                max_heuristic=max_h,
                classifier_weight=classifier_weight,
                clip_boost=clip_boost,
            )
            triples.append((s, ci, si))
    triples.sort(key=lambda x: -x[0])

    used_clip: Set[int] = set()
    used_slot: Set[int] = set()
    slot_to_clip: Dict[int, int] = {}
    for _s, ci, si in triples:
        if ci in used_clip or si in used_slot:
            continue
        used_clip.add(ci)
        used_slot.add(si)
        slot_to_clip[si] = ci

    for si, event_name in enumerate(slots):
        if si in slot_to_clip:
            continue
        best_ci: Optional[int] = None
        best_s = -1.0
        for ci, clip_path in enumerate(clips):
            if ci in used_clip:
                continue
            sc = _pair_blended_score(
                clip_path,
                event_name,
                transcript_map=transcript_map,
                classifier_map=classifier_map,
                max_heuristic=max_h,
                classifier_weight=classifier_weight,
                clip_boost=clip_boost,
            )
            if sc > best_s:
                best_s = sc
                best_ci = ci
        if best_ci is not None:
            slot_to_clip[si] = best_ci
            used_clip.add(best_ci)

    # Remaining slots (fewer clips than slots): best semantic match per slot, reuse allowed.
    for si, event_name in enumerate(slots):
        if si in slot_to_clip:
            continue
        best_ci = 0
        best_s = float("-inf")
        for ci, clip_path in enumerate(clips):
            sc = _pair_blended_score(
                clip_path,
                event_name,
                transcript_map=transcript_map,
                classifier_map=classifier_map,
                max_heuristic=max_h,
                classifier_weight=classifier_weight,
                clip_boost=clip_boost,
            )
            if sc > best_s:
                best_s = sc
                best_ci = ci
        slot_to_clip[si] = best_ci

    for si, event_name in enumerate(slots):
        ci = slot_to_clip[si]
        recommendations[event_name].append(clips[ci].name)

    return recommendations


def _similarities_to_event_scores(similarities: "Any") -> Dict[str, float]:
    """Map cosine similarities in [-1, 1] to per-event scores in [0, 1]."""
    import numpy as np

    sims = np.asarray(similarities, dtype=np.float64).reshape(-1)
    mapped = np.clip((sims + 1.0) / 2.0, 0.0, 1.0)
    return {EVENT_ORDER[i]: float(mapped[i]) for i in range(len(EVENT_ORDER))}


def classify_with_sentence_embeddings(
    transcripts: Dict[Path, str],
    *,
    model_name: str = DEFAULT_SENTENCE_EMBEDDING_MODEL,
    classifier_device: Optional[str] = None,
    progress: bool = True,
    progress_context: str = "",
    progress_callback: Optional[Callable[[int, int, Path, str, str], None]] = None,
) -> Dict[Path, Dict[str, float]]:
    """
    Score each clip by cosine similarity of two embeddings: the **transcribed WAV text**
    (see ``_transcript_text_for_embedding_compare``) versus one vector per hook whose text
    states **what kind of utterance fits that hook** (see ``_hook_event_criteria_for_embedding``),
    derived from ``EVENT_LABEL_DESCRIPTIONS``. Higher similarity means the transcript better
    matches the hook type's description.

    Uses a small sentence embedding model (default: MiniLM L6). Unlike zero-shot NLI,
    there is no explicit premise/hypothesis NLI head—only semantic similarity in embedding space.
    """
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception as ex:  # pragma: no cover - env-dependent
        raise RuntimeError(
            "sentence-transformers is not installed. Run `uv sync --project soundpack_builder`."
        ) from ex
    import numpy as np

    t = hf_token()
    items = sorted(transcripts.items(), key=lambda kv: kv[0].name.lower())
    total = len(items)
    out: Dict[Path, Dict[str, float]] = {p: {} for p, _ in items}

    nonempty: List[Tuple[Path, str]] = [(p, tx) for p, tx in items if tx.strip()]
    batch_ok = True
    if nonempty:
        st_dev = resolve_classifier_device(classifier_device or "auto")
        if progress:
            print(
                f"[CLASSIFY] encoding {len(nonempty)} clip(s) + {len(EVENT_ORDER)} hook labels "
                f"(sentence-embedding){' on ' + st_dev if st_dev else ''}…",
                file=sys.stderr,
                flush=True,
            )
        try:
            st_kw: Dict[str, Any] = {"token": t if t else None}
            if st_dev is not None:
                st_kw["device"] = st_dev
            model = SentenceTransformer(model_name, **st_kw)
            label_texts = [_hook_event_criteria_for_embedding(event) for event in EVENT_ORDER]
            label_emb = model.encode(
                label_texts,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            paths_batch = [p for p, _ in nonempty]
            texts_batch = [_transcript_text_for_embedding_compare(tx) for _, tx in nonempty]
            text_emb = model.encode(
                texts_batch,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            sims = np.dot(text_emb, label_emb.T)
            for bi, clip_path in enumerate(paths_batch):
                out[clip_path] = _similarities_to_event_scores(sims[bi])
        except Exception as ex:
            batch_ok = False
            print(
                f"[CLASSIFY] sentence-embedding batch failed ({model_name}): {ex}",
                file=sys.stderr,
                flush=True,
            )
            traceback.print_exc(file=sys.stderr)
            for clip_path, _tx in nonempty:
                out[clip_path] = {}

    if nonempty and batch_ok and progress:
        print(
            f"[CLASSIFY] batch done ({len(nonempty)} scored).",
            file=sys.stderr,
            flush=True,
        )

    for index, (clip_path, transcript) in enumerate(items):
        if progress_callback:
            progress_callback(index + 1, total, clip_path, "classify-start", progress_context)
        if not transcript.strip():
            if progress_callback:
                progress_callback(index + 1, total, clip_path, "classify-skip", progress_context)
            continue
        status = "classify-done" if batch_ok else "classify-error"
        if progress_callback:
            progress_callback(index + 1, total, clip_path, status, progress_context)
    return out


def classify_hook_events(
    transcripts: Dict[Path, str],
    *,
    backend: ClassifierBackend = "zero-shot",
    model_name: Optional[str] = None,
    classifier_device: Optional[str] = None,
    progress: bool = True,
    progress_context: str = "",
    progress_callback: Optional[Callable[[int, int, Path, str, str], None]] = None,
) -> Dict[Path, Dict[str, float]]:
    """Dispatch to zero-shot NLI or sentence-embedding similarity classifiers."""
    if model_name is None:
        if backend == "sentence-embedding":
            model_name = DEFAULT_SENTENCE_EMBEDDING_MODEL
        else:
            model_name = default_zero_shot_model_for_classifier_device(
                classifier_device or "auto"
            )
    if backend == "sentence-embedding":
        return classify_with_sentence_embeddings(
            transcripts,
            model_name=model_name,
            classifier_device=classifier_device,
            progress=progress,
            progress_context=progress_context,
            progress_callback=progress_callback,
        )
    return classify_with_zero_shot(
        transcripts,
        model_name=model_name,
        classifier_device=classifier_device,
        progress=progress,
        progress_context=progress_context,
        progress_callback=progress_callback,
    )


def classify_with_zero_shot(
    transcripts: Dict[Path, str],
    *,
    model_name: str = DEFAULT_ZERO_SHOT_MODEL,
    classifier_device: Optional[str] = None,
    progress: bool = True,
    progress_context: str = "",
    progress_callback: Optional[Callable[[int, int, Path, str, str], None]] = None,
) -> Dict[Path, Dict[str, float]]:
    """
    Classify transcripts into hook events using a small zero-shot NLI model.

    Returns probability-like scores in [0, 1] for each event per clip.
    Raises RuntimeError if transformers/backend is unavailable.
    """
    try:
        from transformers import pipeline  # type: ignore
    except Exception as ex:  # pragma: no cover - env-dependent
        raise RuntimeError(
            "transformers is not installed. Run `uv sync --project soundpack_builder`."
        ) from ex

    gc.collect()

    if sys.platform == "win32":
        # Reduces flaky native crashes (incl. int divide-by-zero in SDPA/BLAS) on Windows CPU.
        os.environ.setdefault("OMP_NUM_THREADS", "1")
        os.environ.setdefault("MKL_NUM_THREADS", "1")
        try:
            import torch

            torch.set_num_threads(1)
        except Exception:
            pass

    t = hf_token()
    resolved = resolve_classifier_device(classifier_device or "auto")
    pd = _transformers_pipeline_device_arg(resolved)
    pipe_extra: Dict[str, Any] = {}
    if pd is not None:
        pipe_extra["device"] = pd
    elif classifier_runs_on_cpu(classifier_device or "auto"):
        pipe_extra["device"] = -1
    try:
        classifier = pipeline(
            "zero-shot-classification",
            model=model_name,
            token=t if t else True,
            model_kwargs=_zero_shot_pipeline_model_kwargs(),
            **pipe_extra,
        )
    except Exception as ex:
        raise RuntimeError(
            f"Failed to load zero-shot classifier pipeline ({model_name!r}): {ex}"
        ) from ex
    if progress:
        dev_note = f"pipeline device index {pd}" if pd is not None else "default device (see log above)"
        print(
            f"[CLASSIFY] zero-shot model loaded ({model_name}); {dev_note}. Starting per-clip inference…",
            file=sys.stderr,
            flush=True,
        )
    label_texts = [EVENT_LABEL_DESCRIPTIONS[event] for event in EVENT_ORDER]
    label_to_event = {EVENT_LABEL_DESCRIPTIONS[event]: event for event in EVENT_ORDER}

    items = sorted(transcripts.items(), key=lambda kv: kv[0].name.lower())
    total = len(items)
    out: Dict[Path, Dict[str, float]] = {}
    for index, (clip_path, transcript) in enumerate(items):
        if progress:
            _print_inference_progress(
                "CLASSIFY", index + 1, total, clip_path.name, "start", progress_context
            )
        if progress_callback:
            progress_callback(index + 1, total, clip_path, "classify-start", progress_context)
        premise = _zero_shot_safe_premise(classifier.tokenizer, transcript)
        if premise is None:
            out[clip_path] = {}
            if progress:
                _print_inference_progress(
                    "CLASSIFY", index + 1, total, clip_path.name, "skip", progress_context
                )
            if progress_callback:
                progress_callback(index + 1, total, clip_path, "classify-skip", progress_context)
            continue
        try:
            result = classifier(premise, label_texts, multi_label=True)
            scores: Dict[str, float] = {}
            labels = result.get("labels", [])
            values = result.get("scores", [])
            for label, score in zip(labels, values):
                event_name = label_to_event.get(str(label))
                if event_name:
                    scores[event_name] = float(score)
            out[clip_path] = scores
            if progress:
                _print_inference_progress(
                    "CLASSIFY", index + 1, total, clip_path.name, "done", progress_context
                )
            if progress_callback:
                progress_callback(index + 1, total, clip_path, "classify-done", progress_context)
        except Exception as ex:
            out[clip_path] = {}
            print(
                f"[CLASSIFY] inference failed for {clip_path.name}: {ex}",
                file=sys.stderr,
                flush=True,
            )
            traceback.print_exc(file=sys.stderr)
            if progress:
                _print_inference_progress(
                    "CLASSIFY", index + 1, total, clip_path.name, "error", progress_context
                )
            if progress_callback:
                progress_callback(index + 1, total, clip_path, "classify-error", progress_context)
    return out


def transcribe_with_whisper(
    audio_paths: Sequence[Path],
    *,
    model_size: str = "tiny",
    language: Optional[str] = "en",
    device: str = "auto",
    compute_type: str = "auto",
    progress: bool = True,
    progress_context: str = "",
    progress_callback: Optional[Callable[[int, int, Path, str, str], None]] = None,
) -> Dict[Path, str]:
    """
    Transcribe audio files using faster-whisper.

    Raises RuntimeError when the dependency is unavailable.
    """
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception as ex:  # pragma: no cover - covered by failure path tests
        raise RuntimeError(
            "faster-whisper is not installed. Run `uv sync --project soundpack_builder`."
        ) from ex

    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    out: Dict[Path, str] = {}
    total = len(audio_paths)
    try:
        for index, audio_path in enumerate(audio_paths):
            if progress:
                _print_inference_progress(
                    "TRANSCRIBE", index + 1, total, audio_path.name, "start", progress_context
                )
            if progress_callback:
                progress_callback(index + 1, total, audio_path, "start", progress_context)
            try:
                segments, _info = model.transcribe(str(audio_path), language=language or None)
                transcript = " ".join((seg.text or "").strip() for seg in segments).strip()
                out[audio_path] = transcript
                if progress:
                    _print_inference_progress(
                        "TRANSCRIBE", index + 1, total, audio_path.name, "done", progress_context
                    )
                if progress_callback:
                    progress_callback(index + 1, total, audio_path, "done", progress_context)
            except Exception:
                out[audio_path] = ""
                if progress:
                    _print_inference_progress(
                        "TRANSCRIBE", index + 1, total, audio_path.name, "error", progress_context
                    )
                if progress_callback:
                    progress_callback(index + 1, total, audio_path, "error", progress_context)
    finally:
        del model
        gc.collect()
    return out


def _print_inference_progress(
    phase: str,
    index: int,
    total: int,
    filename: str,
    status: str,
    context: str,
) -> None:
    width = 24
    done = int((index / max(total, 1)) * width)
    bar = "#" * done + "-" * (width - done)
    prefix = f"{context}/" if context else ""
    print(
        f"[{bar}] {index}/{max(total, 1)} [{phase}] {status}: {prefix}{filename}",
        file=sys.stderr,
        flush=True,
    )


def recommend_event_mapping(
    audio_paths: Iterable[Path],
    *,
    transcripts: Optional[Dict[Path, str]] = None,
    classifier_scores: Optional[Dict[Path, Dict[str, float]]] = None,
    classifier_weight: float = 5.0,
    clip_quality_boost: Optional[Dict[Path, float]] = None,
) -> tuple[Dict[str, List[str]], List[ClipSignal]]:
    """
    Build deterministic event mapping recommendations from transcripts + filenames.

    Assigns each clip to at most one hook slot globally (greedy on blended model/heuristic
    scores). Optional ``clip_quality_boost`` adds weight from manifest ``matchQuality``.
    """
    clips = sorted([p for p in audio_paths if p.suffix.lower() == ".wav"], key=lambda p: p.name.lower())
    transcript_map = transcripts or {}
    classifier_map = classifier_scores or {}
    clip_boost = clip_quality_boost or {}
    recommendations = _global_event_assignment(
        clips, transcript_map, classifier_map, classifier_weight, clip_boost
    )
    signals: List[ClipSignal] = []

    for event_name in HOOK_EVENT_ORDER:
        selected = recommendations.get(event_name, [])
        if not selected:
            continue
        clip_name = selected[0]
        ranked = _merged_ranking_for_event(event_name, clips, transcript_map, classifier_map)
        transcript = next((tx for name, tx in ranked if name == clip_name), "")
        clip_for_first = next((p for p in clips if p.name == clip_name), None)
        if clip_for_first and _clip_uses_model_ranking(
            clip_for_first, transcript_map.get(clip_for_first, ""), classifier_map
        ):
            reason = "model"
        elif transcript:
            reason = "transcript+filename"
        else:
            reason = "filename-only"
        signals.append(
            ClipSignal(
                filename=clip_name,
                transcript=transcript,
                reason=reason,
            )
        )

    return recommendations, signals


def build_mapping_report(
    audio_paths: Iterable[Path],
    *,
    transcripts: Optional[Dict[Path, str]] = None,
    classifier_scores: Optional[Dict[Path, Dict[str, float]]] = None,
    classifier_weight: float = 5.0,
    clip_quality_boost: Optional[Dict[Path, float]] = None,
    speech_verification: Optional[Dict[str, Any]] = None,
    clips_override: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Build a report showing scores and selections used for event recommendations.

    ``speech_verification`` is merged into the top-level payload (e.g. mode, excludedClips).
    ``clips_override`` replaces the default per-clip list when set (e.g. full pack rows with
    speechEligible flags while ``audio_paths`` lists only eligible files used for scoring).
    """
    clips = sorted([p for p in audio_paths if p.suffix.lower() == ".wav"], key=lambda p: p.name.lower())
    transcript_map = transcripts or {}
    classifier_map = classifier_scores or {}
    clip_boost = clip_quality_boost or {}
    report_events: Dict[str, Any] = {}
    recommendations, _signals = recommend_event_mapping(
        clips,
        transcripts=transcript_map,
        classifier_scores=classifier_map,
        classifier_weight=classifier_weight,
        clip_quality_boost=clip_boost,
    )
    max_h = _max_heuristic_by_event(clips, transcript_map)

    for event_name in HOOK_EVENT_ORDER:
        mh = max_h.get(event_name, 0.0)
        candidates = []
        for clip_path in clips:
            transcript = transcript_map.get(clip_path, "")
            heuristic_score = _score_event(event_name, transcript, clip_path.name)
            model_score = classifier_map.get(clip_path, {}).get(event_name, 0.0)
            heuristic_normalized = (heuristic_score / mh) if mh > 0 else 0.0
            use_model_tier = _clip_uses_model_ranking(clip_path, transcript, classifier_map)
            blended = _report_score_for_candidate(
                use_model_tier=use_model_tier,
                model_score=model_score,
                heuristic_normalized=heuristic_normalized,
                classifier_weight=classifier_weight,
            ) + clip_boost.get(clip_path, 0.0)
            candidates.append(
                {
                    "file": clip_path.name,
                    "score": blended,
                    "rankingTier": "model" if use_model_tier else "heuristic_fallback",
                    "heuristicScore": heuristic_score,
                    "heuristicScoreNormalized": heuristic_normalized,
                    "modelScore": model_score,
                    "transcript": transcript,
                }
            )
        merge_order = [name for name, _tx in _merged_ranking_for_event(event_name, clips, transcript_map, classifier_map)]
        order_index = {name: idx for idx, name in enumerate(merge_order)}
        candidates.sort(
            key=lambda item: (order_index.get(str(item["file"]), len(merge_order)), str(item["file"]).lower())
        )
        report_events[event_name] = {
            "selected": recommendations.get(event_name, []),
            "candidates": candidates,
        }

    default_clips = [
        {"file": clip.name, "transcript": transcript_map.get(clip, "")}
        for clip in clips
    ]
    out: Dict[str, Any] = {
        "clips": clips_override if clips_override is not None else default_clips,
        "events": report_events,
    }
    if speech_verification is not None:
        out["speechVerification"] = speech_verification
    return out


TRANSCRIPTS_JSON_NAME = "transcripts.json"
CLASSIFIER_SCORES_JSON_NAME = "classifier-scores.json"
SIDECAR_SCHEMA_VERSION = 1


def load_transcripts_sidecar(pack_dir: Path) -> Optional[Dict[Path, str]]:
    """Load ``transcripts.json`` beside pack WAVs; return ``None`` if missing or invalid."""
    path = pack_dir / TRANSCRIPTS_JSON_NAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    clips = data.get("clips")
    if not isinstance(clips, dict):
        return None
    out: Dict[Path, str] = {}
    for name, text in clips.items():
        if not isinstance(name, str) or not isinstance(text, str):
            continue
        out[pack_dir / name] = text
    return out


def save_transcripts_sidecar(pack_dir: Path, transcripts: Dict[Path, str]) -> Path:
    """Write ``transcripts.json`` with basename keys for each WAV."""
    pack_dir.mkdir(parents=True, exist_ok=True)
    path = pack_dir / TRANSCRIPTS_JSON_NAME
    clips = {p.name: tx for p, tx in sorted(transcripts.items(), key=lambda kv: kv[0].name.lower())}
    payload = {"schemaVersion": SIDECAR_SCHEMA_VERSION, "clips": clips}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def load_classifier_scores_sidecar(pack_dir: Path) -> Optional[Dict[Path, Dict[str, float]]]:
    """Load ``classifier-scores.json``; return ``None`` if missing or invalid."""
    path = pack_dir / CLASSIFIER_SCORES_JSON_NAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    raw = data.get("scores")
    if not isinstance(raw, dict):
        return None
    out: Dict[Path, Dict[str, float]] = {}
    for fname, scores in raw.items():
        if not isinstance(fname, str) or not isinstance(scores, dict):
            continue
        inner: Dict[str, float] = {}
        for ev, val in scores.items():
            if isinstance(ev, str):
                try:
                    inner[ev] = float(val)
                except (TypeError, ValueError):
                    continue
        out[pack_dir / fname] = inner
    return out


def save_classifier_scores_sidecar(
    pack_dir: Path, scores: Dict[Path, Dict[str, float]]
) -> Path:
    """Write per-file classifier scores for hook events."""
    pack_dir.mkdir(parents=True, exist_ok=True)
    path = pack_dir / CLASSIFIER_SCORES_JSON_NAME
    by_name: Dict[str, Dict[str, float]] = {}
    for p, sc in sorted(scores.items(), key=lambda kv: kv[0].name.lower()):
        by_name[p.name] = dict(sc)
    payload = {"schemaVersion": SIDECAR_SCHEMA_VERSION, "scores": by_name}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
