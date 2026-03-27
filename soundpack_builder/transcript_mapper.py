"""
Transcript-driven event recommendation for character sound packs.

This module is intentionally conservative: if transcription is unavailable or weak,
it falls back to filename-based signals and deterministic ordering.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Any

from .config import hf_token

EVENT_ORDER = [
    "beforeSubmitPrompt",
    "afterAgentThought",
    "afterAgentResponse",
    "preToolUse",
    "postToolUse",
    "postToolUseFailure",
    "stop",
]

EVENT_LABEL_DESCRIPTIONS = {
    "beforeSubmitPrompt": "A short confirmation or ready-to-start prompt before taking action.",
    "afterAgentThought": "A reflective or thinking-style utterance after internal reasoning.",
    "afterAgentResponse": "A completion or response-style utterance after delivering an answer.",
    "preToolUse": "A short action-start cue before running a tool.",
    "postToolUse": "A success or completion cue after a tool finishes successfully.",
    "postToolUseFailure": "A failure or error cue after a tool run fails.",
    "stop": "A stop, halt, cancel, or interruption cue.",
}

EVENT_TARGET_COUNTS = {
    "beforeSubmitPrompt": 2,
    "afterAgentThought": 2,
    "afterAgentResponse": 2,
    "preToolUse": 1,
    "postToolUse": 1,
    "postToolUseFailure": 1,
    "stop": 1,
}

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


def classify_with_zero_shot(
    transcripts: Dict[Path, str],
    *,
    model_name: str = "valhalla/distilbart-mnli-12-1",
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

    t = hf_token()
    classifier = pipeline(
        "zero-shot-classification",
        model=model_name,
        token=t if t else True,
    )
    label_texts = [EVENT_LABEL_DESCRIPTIONS[event] for event in EVENT_ORDER]
    label_to_event = {EVENT_LABEL_DESCRIPTIONS[event]: event for event in EVENT_ORDER}

    items = sorted(transcripts.items(), key=lambda kv: kv[0].name.lower())
    total = len(items)
    out: Dict[Path, Dict[str, float]] = {}
    for index, (clip_path, transcript) in enumerate(items):
        if progress:
            _print_transcribe_progress(index + 1, total, clip_path.name, "classify-start", progress_context)
        if progress_callback:
            progress_callback(index + 1, total, clip_path, "classify-start", progress_context)
        if not transcript.strip():
            out[clip_path] = {}
            if progress:
                _print_transcribe_progress(index + 1, total, clip_path.name, "classify-skip", progress_context)
            if progress_callback:
                progress_callback(index + 1, total, clip_path, "classify-skip", progress_context)
            continue
        try:
            result = classifier(transcript, label_texts, multi_label=True)
            scores: Dict[str, float] = {}
            labels = result.get("labels", [])
            values = result.get("scores", [])
            for label, score in zip(labels, values):
                event_name = label_to_event.get(str(label))
                if event_name:
                    scores[event_name] = float(score)
            out[clip_path] = scores
            if progress:
                _print_transcribe_progress(index + 1, total, clip_path.name, "classify-done", progress_context)
            if progress_callback:
                progress_callback(index + 1, total, clip_path, "classify-done", progress_context)
        except Exception:
            out[clip_path] = {}
            if progress:
                _print_transcribe_progress(index + 1, total, clip_path.name, "classify-error", progress_context)
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
    for index, audio_path in enumerate(audio_paths):
        if progress:
            _print_transcribe_progress(index + 1, total, audio_path.name, "start", progress_context)
        if progress_callback:
            progress_callback(index + 1, total, audio_path, "start", progress_context)
        try:
            segments, _info = model.transcribe(str(audio_path), language=language or None)
            transcript = " ".join((seg.text or "").strip() for seg in segments).strip()
            out[audio_path] = transcript
            if progress:
                _print_transcribe_progress(index + 1, total, audio_path.name, "done", progress_context)
            if progress_callback:
                progress_callback(index + 1, total, audio_path, "done", progress_context)
        except Exception:
            out[audio_path] = ""
            if progress:
                _print_transcribe_progress(index + 1, total, audio_path.name, "error", progress_context)
            if progress_callback:
                progress_callback(index + 1, total, audio_path, "error", progress_context)
    return out


def _print_transcribe_progress(
    index: int, total: int, filename: str, status: str, context: str
) -> None:
    width = 24
    done = int((index / max(total, 1)) * width)
    bar = "#" * done + "-" * (width - done)
    prefix = f"{context}/" if context else ""
    print(
        f"[{bar}] {index}/{max(total, 1)} transcribe-{status}: {prefix}{filename}",
        file=sys.stderr,
        flush=True,
    )


def recommend_event_mapping(
    audio_paths: Iterable[Path],
    *,
    transcripts: Optional[Dict[Path, str]] = None,
    classifier_scores: Optional[Dict[Path, Dict[str, float]]] = None,
    classifier_weight: float = 5.0,
) -> tuple[Dict[str, List[str]], List[ClipSignal]]:
    """
    Build deterministic event mapping recommendations from transcripts + filenames.

    Uses tiered ranking per event: model scores when transcript and classifier data
    exist for a clip; otherwise normalized heuristics. See `_merged_ranking_for_event`.
    """
    clips = sorted([p for p in audio_paths if p.suffix.lower() == ".wav"], key=lambda p: p.name.lower())
    transcript_map = transcripts or {}
    classifier_map = classifier_scores or {}
    recommendations: Dict[str, List[str]] = {}
    signals: List[ClipSignal] = []

    for event_name in EVENT_ORDER:
        ranked = _merged_ranking_for_event(
            event_name, clips, transcript_map, classifier_map
        )
        take = EVENT_TARGET_COUNTS[event_name]
        selected = [name for name, _tx in ranked[:take]]
        if not selected and clips:
            selected = [clips[0].name]
        recommendations[event_name] = selected

        if selected:
            clip_name = selected[0]
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
) -> Dict[str, Any]:
    """
    Build a report showing scores and selections used for event recommendations.
    """
    clips = sorted([p for p in audio_paths if p.suffix.lower() == ".wav"], key=lambda p: p.name.lower())
    transcript_map = transcripts or {}
    classifier_map = classifier_scores or {}
    report_events: Dict[str, Any] = {}
    recommendations, _signals = recommend_event_mapping(
        clips,
        transcripts=transcript_map,
        classifier_scores=classifier_map,
        classifier_weight=classifier_weight,
    )

    for event_name in EVENT_ORDER:
        max_heuristic = max(
            (_score_event(event_name, transcript_map.get(clip_path, ""), clip_path.name) for clip_path in clips),
            default=0.0,
        )
        candidates = []
        for clip_path in clips:
            transcript = transcript_map.get(clip_path, "")
            heuristic_score = _score_event(event_name, transcript, clip_path.name)
            model_score = classifier_map.get(clip_path, {}).get(event_name, 0.0)
            heuristic_normalized = (heuristic_score / max_heuristic) if max_heuristic > 0 else 0.0
            use_model_tier = _clip_uses_model_ranking(clip_path, transcript, classifier_map)
            blended = _report_score_for_candidate(
                use_model_tier=use_model_tier,
                model_score=model_score,
                heuristic_normalized=heuristic_normalized,
                classifier_weight=classifier_weight,
            )
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

    return {
        "clips": [
            {"file": clip.name, "transcript": transcript_map.get(clip, "")}
            for clip in clips
        ],
        "events": report_events,
    }
