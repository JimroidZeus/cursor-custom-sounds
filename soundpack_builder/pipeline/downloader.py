"""
Pipeline step 3: download sound clips into ``sounds/<universe>/<character>/``,
or ``sounds/<universe>/<character>/<packLabelSlug>/`` when manifest rows set ``packLabelSlug``.

Default manifest: ``manifests/download-manifest.json`` (or ``--manifest``).

Each manifest entry must provide a direct download URL (or ZIP + ``pathInArchive``);
this module does not crawl sites. Non-WAV sources are converted with ``ffmpeg`` when
available. Multiple manifest rows that share the same ``.zip`` URL (same soundpack)
download that archive **once** and reuse it for each ``pathInArchive`` extraction.

Optionally generates per-pack ``sound-config.json`` and ``mapping-report.json`` via
``transcript_mapper`` (Whisper, transcript classifier, global hook slot assignment).
Optional ``matchQuality`` on an entry boosts mapping scores. See ``--preset`` for
Whisper model shorthand.
"""

from __future__ import annotations

import argparse
import faulthandler
import hashlib
import json
import sys
import shutil
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from soundpack_builder.audio.transcript_mapper import (
    DEFAULT_SENTENCE_EMBEDDING_MODEL,
    DEFAULT_ZERO_SHOT_MODEL,
    DEFAULT_ZERO_SHOT_MODEL_CPU,
    ClassifierBackend,
    default_zero_shot_model_for_classifier_device,
    build_mapping_report,
    classify_hook_events,
    load_classifier_scores_sidecar,
    load_transcripts_sidecar,
    partition_clips_by_speech,
    recommend_event_mapping,
    transcribe_with_whisper,
)
from soundpack_builder.audio.wav_convert import convert_to_wav, is_riff_wave as _is_riff_wave
from soundpack_builder.core.config import BuilderConfig, add_output_path_args, build_config_from_args
from soundpack_builder.core.console_progress import render_bar
from soundpack_builder.core.language_codes import (
    DEFAULT_LANGUAGE_FILTER,
    normalize_language_code,
    parse_language_filter_arg,
    passes_language_filter,
    resolve_language_code,
)
from soundpack_builder.core.media_urls import looks_like_html_file, normalize_absolute_media_url


@dataclass(frozen=True)
class ClipEntry:
    universe: str
    character: str
    url: str
    targetFile: Optional[str] = None  # legacy field; preferred behavior preserves source basename
    # Optional metadata for your own review/debugging
    source_page: Optional[str] = None
    # If the URL is a zip archive, specify which wav file to extract inside it.
    # This should be the path as it appears in the archive (e.g. "Orc/Peon/PeonReady1.wav").
    pathInArchive: Optional[str] = None
    note: Optional[str] = None
    # Optional human rating from discovery manifests; boosts transcript mapping when set.
    matchQuality: Optional[Any] = None
    # Distinct candidateLink labels for the same character become separate folders:
    # sounds/<universe>/<character>/<packLabelSlug>/ when set.
    packLabelSlug: Optional[str] = None
    languageCode: Optional[str] = None

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ClipEntry":
        pls = d.get("packLabelSlug") or d.get("pack_label_slug")
        lc = d.get("languageCode")
        return ClipEntry(
            universe=str(d["universe"]),
            character=str(d["character"]),
            url=str(d["url"]),
            targetFile=str(d["targetFile"]) if d.get("targetFile") else None,
            source_page=d.get("source_page"),
            pathInArchive=d.get("pathInArchive") or d.get("path_in_archive"),
            note=d.get("note"),
            matchQuality=d.get("matchQuality"),
            packLabelSlug=str(pls).strip() if pls else None,
            languageCode=str(lc).strip() if lc else None,
        )


def _match_quality_boost(raw: Any) -> float:
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return min(1.0, max(0.0, float(raw))) * 0.25
    s = str(raw).strip().lower()
    if s in ("high", "good", "best"):
        return 0.25
    if s in ("medium", "mid", "ok"):
        return 0.12
    return 0.0


def _path_name_from_url(url: str) -> str:
    return Path(url.split("?", 1)[0]).name


def _output_filename(entry: ClipEntry) -> str:
    if entry.pathInArchive:
        source_name = Path(entry.pathInArchive).name
    else:
        source_name = _path_name_from_url(entry.url)
    if source_name:
        # Keep original clip basename, normalize extension to .wav for playback.
        stem = Path(source_name).stem
        return f"{stem}.wav"
    if entry.targetFile:
        return entry.targetFile
    raise ValueError("Cannot determine output filename (missing pathInArchive/url basename).")


def download_url(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = normalize_absolute_media_url(url)

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "cursor-custom-sounds-downloader/1.0",
        },
    )

    with urllib.request.urlopen(req) as resp:
        # Stream to disk to avoid memory blowups
        with dest.open("wb") as f:
            shutil.copyfileobj(resp, f)
    if looks_like_html_file(dest):
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass
        raise RuntimeError(
            "Download looks like HTML (often a login or error page), not audio. "
            "For Freesound, set FREESOUND_API_KEY and run "
            "`python -m soundpack_builder.tools.freesound_resolve`, or use preview CDN URLs from the API."
        )


def _zip_url_cache_key(url: str) -> Optional[str]:
    """Normalized URL (no query) if it points at a ``.zip``; else ``None`` (no ZIP reuse)."""
    n = url.split("?", 1)[0].strip()
    if n.lower().endswith(".zip"):
        return n
    return None


def _cached_zip_path(downloaded_dir: Path, cache_key: str) -> Path:
    """Stable on-disk path for a given ZIP URL (content-addressed by key hash)."""
    digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()[:28]
    return downloaded_dir / "_zip_cache" / f"{digest}.zip"


def _normalize_archive_path(path: str) -> str:
    return path.replace("\\", "/").strip("/").lower()


def _pick_zip_audio_member(
    audio_members: List[str],
    *,
    preferred_stem: Optional[str],
) -> Optional[str]:
    """
    When multiple audio files exist in a zip, prefer a member whose basename/stem matches
    the intended output (e.g. manifest derived from ``403989.wav`` → ``403989``).
    """
    if not audio_members:
        return None
    if len(audio_members) == 1:
        return audio_members[0]
    if not preferred_stem:
        return None
    stem_l = preferred_stem.strip().lower()
    if not stem_l:
        return None
    exact = [m for m in audio_members if Path(m).stem.lower() == stem_l]
    if len(exact) == 1:
        return exact[0]
    by_name = [m for m in audio_members if stem_l in Path(m).name.lower()]
    if len(by_name) == 1:
        return by_name[0]
    wav_exact = [m for m in audio_members if Path(m).name.lower() == f"{stem_l}.wav"]
    if len(wav_exact) == 1:
        return wav_exact[0]
    return None


def extract_from_zip(
    zip_path: Path,
    *,
    path_in_archive: Optional[str],
    temp_dir: Path,
    preferred_stem: Optional[str] = None,
) -> Path:
    import zipfile

    temp_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(zip_path), "r") as zf:
        members = [m for m in zf.namelist() if not m.endswith("/")]
        norm_to_member = {_normalize_archive_path(m): m for m in members}

        selected_member: Optional[str] = None
        if path_in_archive:
            wanted = _normalize_archive_path(path_in_archive)
            selected_member = norm_to_member.get(wanted)
            if not selected_member:
                basename = Path(wanted).name
                basename_matches = [
                    m for m in members if Path(_normalize_archive_path(m)).name == basename
                ]
                if len(basename_matches) == 1:
                    selected_member = basename_matches[0]
            if not selected_member:
                raise FileNotFoundError(f"File not found in archive: {path_in_archive}")
        else:
            audio_members = [
                m
                for m in members
                if Path(m).suffix.lower() in {".wav", ".mp3", ".ogg", ".flac", ".m4a"}
            ]
            wavs = [m for m in audio_members if Path(m).suffix.lower() == ".wav"]
            if len(wavs) == 1:
                selected_member = wavs[0]
            elif len(audio_members) == 1:
                selected_member = audio_members[0]
            else:
                picked = _pick_zip_audio_member(audio_members, preferred_stem=preferred_stem)
                if picked:
                    selected_member = picked
                else:
                    raise RuntimeError(
                        "Zip archive contains multiple audio files. Provide `pathInArchive` to pick one, "
                        "or ensure the output filename stem matches a file inside the archive."
                    )

        assert selected_member is not None
        suffix = Path(selected_member).suffix or ".bin"
        with zf.open(selected_member, "r") as src, tempfile.NamedTemporaryFile(
            dir=temp_dir,
            suffix=suffix,
            delete=False,
        ) as dst:
            shutil.copyfileobj(src, dst)
            return Path(dst.name)


def load_manifest(path: Path) -> List[ClipEntry]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "entries" in payload:
        payload = payload["entries"]
    if not isinstance(payload, list):
        raise ValueError("Manifest must be a list (or {entries:[...]}).")
    return [ClipEntry.from_dict(x) for x in payload]


def _print_progress(
    *,
    index: int,
    total: int,
    entry: ClipEntry,
    status: str,
    enabled: bool,
) -> None:
    if not enabled:
        return
    bar = render_bar(index, total)
    label_name = _output_filename(entry)
    sub = entry.character
    if entry.packLabelSlug:
        sub = f"{entry.character}/{entry.packLabelSlug}"
    label = f"{entry.universe}/{sub}/{label_name}"
    print(f"[{bar}] {index}/{total} {status}: {label}", file=sys.stderr, flush=True)


def download_clips(
    cfg: BuilderConfig,
    *,
    manifest_path: Path,
    dry_run: bool,
    limit: int,
    overwrite: bool,
    progress: bool,
    recommend_config: bool,
    skip_transcript: bool,
    whisper_model: str,
    whisper_language: Optional[str],
    whisper_device: str,
    whisper_compute_type: str,
    overwrite_recommended_config: bool,
    use_llm_classifier: bool,
    classifier_backend: ClassifierBackend,
    classifier_model: str,
    classifier_weight: float,
    speech_verification_enabled: bool = True,
    use_existing_transcripts: bool = False,
    use_existing_classifier_scores: bool = False,
    classifier_device: str = "auto",
    language_filter_codes: Optional[Set[str]] = None,
) -> int:
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest does not exist: {manifest_path}")

    entries = load_manifest(manifest_path)

    if language_filter_codes is None:
        lang_allowed: Optional[Set[str]] = set(DEFAULT_LANGUAGE_FILTER)
    elif len(language_filter_codes) == 0:
        lang_allowed = None
    else:
        lang_allowed = {x.upper() for x in language_filter_codes}

    def _entry_lang_ok(e: ClipEntry) -> bool:
        resolved = resolve_language_code(
            normalize_language_code(e.languageCode),
            e.pathInArchive or "",
            e.url,
        )
        return passes_language_filter(resolved, lang_allowed)

    entries = [e for e in entries if _entry_lang_ok(e)]
    if limit and limit > 0:
        entries = entries[:limit]

    if not entries:
        print(json.dumps({"ok": True, "message": "No manifest entries to download."}))
        return 0

    downloaded_dir = cfg.downloads_dir
    downloaded_dir.mkdir(parents=True, exist_ok=True)

    results: List[Dict[str, Any]] = []
    packs_seen: Set[Tuple[str, str, str]] = set()
    boosts_by_pack: Dict[Tuple[str, str, str], Dict[Path, float]] = {}
    zip_cache: Dict[str, Path] = {}

    total = len(entries)
    if progress and total:
        print(
            f"Downloading {total} manifest entr{'y' if total == 1 else 'ies'}...",
            file=sys.stderr,
            flush=True,
        )
    for idx, e in enumerate(entries):
        current = idx + 1
        _print_progress(index=current, total=total, entry=e, status="start", enabled=progress)
        target_dir = cfg.sound_dir / e.universe / e.character
        if e.packLabelSlug:
            target_dir = target_dir / e.packLabelSlug
        target_path = target_dir / _output_filename(e)
        pack_key = (e.universe, e.character, e.packLabelSlug or "")
        packs_seen.add(pack_key)
        b = _match_quality_boost(e.matchQuality)
        pk = boosts_by_pack.setdefault(pack_key, {})
        pk[target_path] = max(pk.get(target_path, 0.0), b)

        if target_path.exists() and not overwrite:
            results.append(
                {
                    "ok": True,
                    "skipped": True,
                    "target": str(target_path),
                    "reason": "target exists (use --overwrite to replace)",
                }
            )
            _print_progress(index=current, total=total, entry=e, status="skipped", enabled=progress)
            continue

        # Preserve extension if possible for conversion inputs.
        input_ext = Path(e.url.split("?")[0]).suffix or ".bin"
        pls = e.packLabelSlug or ""
        per_entry_input = downloaded_dir / f"{e.universe}__{e.character}__{pls}__{idx}{input_ext}"
        zk = _zip_url_cache_key(e.url)

        if dry_run:
            results.append(
                {
                    "ok": True,
                    "skipped": False,
                    "target": str(target_path),
                    "url": e.url,
                    "wouldDownload": True,
                }
            )
            _print_progress(index=current, total=total, entry=e, status="dry-run", enabled=progress)
            continue

        try:
            if zk:
                if zk not in zip_cache:
                    _print_progress(index=current, total=total, entry=e, status="downloading", enabled=progress)
                    zip_local = _cached_zip_path(downloaded_dir, zk)
                    zip_local.parent.mkdir(parents=True, exist_ok=True)
                    download_url(e.url, zip_local)
                    zip_cache[zk] = zip_local
                input_path = zip_cache[zk]
            else:
                _print_progress(index=current, total=total, entry=e, status="downloading", enabled=progress)
                input_path = per_entry_input
                download_url(e.url, input_path)

            target_path.parent.mkdir(parents=True, exist_ok=True)

            lower_url = e.url.lower()
            if input_path.suffix.lower() == ".zip" or lower_url.endswith(".zip"):
                _print_progress(index=current, total=total, entry=e, status="extracting", enabled=progress)
                out_stem = Path(_output_filename(e)).stem
                extracted = extract_from_zip(
                    input_path,
                    path_in_archive=e.pathInArchive,
                    temp_dir=downloaded_dir,
                    preferred_stem=out_stem,
                )
                # extracted is expected to be audio; keep basename but normalize to wav format.
                if extracted.suffix.lower() == ".wav" and _is_riff_wave(extracted):
                    extracted.replace(target_path)
                else:
                    _print_progress(index=current, total=total, entry=e, status="converting", enabled=progress)
                    convert_to_wav(extracted, target_path)
                    try:
                        extracted.unlink(missing_ok=True)
                    except OSError:
                        pass
            else:
                # URLs often end in .wav but serve MP3/OGG; only skip conversion for real RIFF WAV.
                if input_path.suffix.lower() == ".wav" and _is_riff_wave(input_path):
                    input_path.replace(target_path)
                else:
                    _print_progress(index=current, total=total, entry=e, status="converting", enabled=progress)
                    convert_to_wav(input_path, target_path)
                    try:
                        input_path.unlink(missing_ok=True)
                    except OSError:
                        pass

            results.append({"ok": True, "target": str(target_path), "url": e.url})
            _print_progress(index=current, total=total, entry=e, status="done", enabled=progress)
        except Exception as ex:
            results.append(
                {
                    "ok": False,
                    "target": str(target_path),
                    "url": e.url,
                    "error": str(ex),
                }
            )
            _print_progress(index=current, total=total, entry=e, status="error", enabled=progress)

    for zp in set(zip_cache.values()):
        try:
            zp.unlink(missing_ok=True)
        except OSError:
            pass

    print(json.dumps({"ok": True, "results": results}, indent=2))
    if recommend_config and not dry_run:
        recommended = _write_recommended_configs(
            cfg,
            packs_seen,
            clip_boost_by_pack=boosts_by_pack,
            skip_transcript=skip_transcript,
            whisper_model=whisper_model,
            whisper_language=whisper_language,
            whisper_device=whisper_device,
            whisper_compute_type=whisper_compute_type,
            overwrite=overwrite_recommended_config,
            progress=progress,
            use_llm_classifier=use_llm_classifier,
            classifier_backend=classifier_backend,
            classifier_model=classifier_model,
            classifier_weight=classifier_weight,
            speech_verification_enabled=speech_verification_enabled,
            use_existing_transcripts=use_existing_transcripts,
            use_existing_classifier_scores=use_existing_classifier_scores,
            classifier_device=classifier_device,
            language_filter_codes=language_filter_codes,
        )
        print(json.dumps({"ok": True, "recommendedConfigs": recommended}, indent=2))
    return 0


def _normalize_event_shape(files: List[str]) -> Any:
    if len(files) == 1:
        return files[0]
    return files


def _lang_allowed_for_recommend(language_filter_codes: Optional[Set[str]]) -> Optional[Set[str]]:
    """Same semantics as manifest filtering in ``download_clips``."""
    if language_filter_codes is None:
        return set(DEFAULT_LANGUAGE_FILTER)
    if len(language_filter_codes) == 0:
        return None
    return {x.upper() for x in language_filter_codes}


def _wav_passes_language_filter(path: Path, lang_allowed: Optional[Set[str]]) -> bool:
    """Infer language from filename (e.g. ``*_ENG.wav``) and apply ``--language-codes`` rules."""
    resolved = resolve_language_code(None, path.name)
    return passes_language_filter(resolved, lang_allowed)


def _filter_wav_paths_by_language(paths: List[Path], lang_allowed: Optional[Set[str]]) -> List[Path]:
    ordered = sorted(paths, key=lambda p: p.name.lower())
    return [p for p in ordered if _wav_passes_language_filter(p, lang_allowed)]


def _write_recommended_configs(
    cfg: BuilderConfig,
    packs_seen: Set[Tuple[str, str, str]],
    *,
    clip_boost_by_pack: Optional[Dict[Tuple[str, str, str], Dict[Path, float]]] = None,
    skip_transcript: bool,
    whisper_model: str,
    whisper_language: Optional[str],
    whisper_device: str,
    whisper_compute_type: str,
    overwrite: bool,
    progress: bool = True,
    use_llm_classifier: bool = True,
    classifier_backend: ClassifierBackend = "zero-shot",
    classifier_model: str = DEFAULT_ZERO_SHOT_MODEL,
    classifier_weight: float = 5.0,
    speech_verification_enabled: bool = True,
    use_existing_transcripts: bool = False,
    use_existing_classifier_scores: bool = False,
    classifier_device: str = "auto",
    language_filter_codes: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    recommendations: List[Dict[str, Any]] = []
    lang_allowed = _lang_allowed_for_recommend(language_filter_codes)
    sorted_packs = sorted(packs_seen)
    pack_audio_counts: Dict[Tuple[str, str, str], int] = {}
    raw_paths_by_pack: Dict[Tuple[str, str, str], List[Path]] = {}
    filtered_paths_by_pack: Dict[Tuple[str, str, str], List[Path]] = {}
    total_audio = 0
    universe_pack_totals: Dict[str, int] = {}
    universe_audio_totals: Dict[str, int] = {}
    for universe, character, pack_slug in sorted_packs:
        pack_dir = cfg.sound_dir / universe / character
        if pack_slug:
            pack_dir = pack_dir / pack_slug
        pk = (universe, character, pack_slug)
        raw_wavs = list(pack_dir.glob("*.wav"))
        raw_paths_by_pack[pk] = raw_wavs
        filtered_wavs = _filter_wav_paths_by_language(raw_wavs, lang_allowed)
        filtered_paths_by_pack[pk] = filtered_wavs
        audio_count = len(filtered_wavs)
        pack_audio_counts[pk] = audio_count
        total_audio += audio_count
        universe_pack_totals[universe] = universe_pack_totals.get(universe, 0) + 1
        universe_audio_totals[universe] = universe_audio_totals.get(universe, 0) + audio_count

    if progress:
        lf_meta: Any
        if lang_allowed is None:
            lf_meta = None
        else:
            lf_meta = sorted(lang_allowed)
        print(
            json.dumps(
                {
                    "phase": "recommend-config-start",
                    "packsTotal": len(sorted_packs),
                    "audioTotal": total_audio,
                    "languageFilter": lf_meta,
                    "universes": [
                        {
                            "universe": universe,
                            "packs": universe_pack_totals.get(universe, 0),
                            "audio": universe_audio_totals.get(universe, 0),
                        }
                        for universe in sorted(universe_pack_totals)
                    ],
                }
            ),
            file=sys.stderr,
            flush=True,
        )

    packs_done = 0
    transcribed_done = 0
    classified_done = 0

    def _print_rollup_progress(*, label: str, done: int, total: int) -> None:
        if not progress:
            return
        print(
            f"[{render_bar(done, total)}] {done}/{max(total, 1)} {label}",
            file=sys.stderr,
            flush=True,
        )

    for universe, character, pack_slug in sorted_packs:
        packs_done += 1
        sub = f"{character}/{pack_slug}" if pack_slug else character
        pack_ctx = f"{universe}/{sub}"
        if progress:
            _print_rollup_progress(
                label=f"packs: {pack_ctx}",
                done=packs_done,
                total=len(sorted_packs),
            )

        pack_dir = cfg.sound_dir / universe / character
        if pack_slug:
            pack_dir = pack_dir / pack_slug
        config_path = pack_dir / "sound-config.json"
        if config_path.exists() and not overwrite:
            recommendations.append(
                {
                    "ok": True,
                    "skipped": True,
                    "pack": f"{universe}/{character}/{pack_slug}" if pack_slug else f"{universe}/{character}",
                    "target": str(config_path),
                    "reason": "recommended config exists (use --overwrite-recommended-config)",
                }
            )
            continue

        pk = (universe, character, pack_slug)
        raw_glob = raw_paths_by_pack[pk]
        audio_paths = filtered_paths_by_pack[pk]
        if progress and lang_allowed is not None and len(lang_allowed) > 0:
            n_raw, n_keep = len(raw_glob), len(audio_paths)
            if n_raw != n_keep:
                print(
                    f"[language-filter] {pack_ctx}: {n_keep}/{n_raw} wav(s) match "
                    f"{sorted(lang_allowed)} (others skipped for transcribe/classify)",
                    file=sys.stderr,
                    flush=True,
                )
        raw_boost = (clip_boost_by_pack or {}).get((universe, character, pack_slug), {})
        clip_quality_boost = {p: float(raw_boost.get(p, 0.0)) for p in audio_paths}
        if not audio_paths:
            if raw_glob and lang_allowed is not None and len(lang_allowed) > 0:
                err = (
                    "No WAV files match --language-codes for this pack "
                    f"(had {len(raw_glob)} file(s); try --no-language-filter or add codes)."
                )
            else:
                err = "No WAV files found for pack."
            recommendations.append(
                {
                    "ok": False,
                    "pack": f"{universe}/{character}/{pack_slug}" if pack_slug else f"{universe}/{character}",
                    "target": str(config_path),
                    "error": err,
                }
            )
            continue

        transcripts: Dict[Path, str] = {}
        transcript_status = "filename-only"
        classifier_scores: Dict[Path, Dict[str, float]] = {}
        classifier_status = "disabled"
        if not skip_transcript:
            def _on_transcript_progress(
                _index: int, _total: int, _clip_path: Path, status: str, _context: str
            ) -> None:
                nonlocal transcribed_done
                if status not in {"done", "error"}:
                    return
                transcribed_done += 1
                _print_rollup_progress(
                    label="transcribe (all packs)",
                    done=transcribed_done,
                    total=total_audio,
                )

            def _on_classifier_progress(
                _index: int, _total: int, _clip_path: Path, status: str, _context: str
            ) -> None:
                nonlocal classified_done
                if status not in {"classify-done", "classify-error", "classify-skip"}:
                    return
                classified_done += 1
                _print_rollup_progress(
                    label="classify (all packs)",
                    done=classified_done,
                    total=total_audio,
                )

            loaded_tx = load_transcripts_sidecar(pack_dir) if use_existing_transcripts else None
            if loaded_tx is not None:
                transcripts = {p: loaded_tx.get(p, "") for p in audio_paths}
                transcript_status = "ok"
            else:
                try:
                    transcripts = transcribe_with_whisper(
                        audio_paths,
                        model_size=whisper_model,
                        language=whisper_language,
                        device=whisper_device,
                        compute_type=whisper_compute_type,
                        progress=progress,
                        progress_context=pack_ctx,
                        progress_callback=_on_transcript_progress,
                    )
                    transcript_status = "ok"
                except Exception as ex:
                    transcript_status = f"fallback: {ex}"
                    transcripts = {}

            if transcript_status == "ok":
                if use_llm_classifier:
                    loaded_cl = (
                        load_classifier_scores_sidecar(pack_dir)
                        if use_existing_classifier_scores
                        else None
                    )
                    if loaded_cl is not None:
                        classifier_scores = {p: dict(loaded_cl.get(p, {})) for p in audio_paths}
                        classifier_status = f"sidecar ({classifier_backend}: {classifier_model})"
                    else:
                        try:
                            classifier_scores = classify_hook_events(
                                transcripts,
                                backend=classifier_backend,
                                model_name=classifier_model,
                                classifier_device=classifier_device,
                                progress=progress,
                                progress_context=pack_ctx,
                                progress_callback=_on_classifier_progress,
                            )
                            classifier_status = f"ok ({classifier_backend}: {classifier_model})"
                        except Exception as ex:
                            classifier_status = f"fallback: {ex}"
                            classifier_scores = {}
                else:
                    classifier_status = "disabled"
            else:
                classifier_status = "transcript-unavailable"

        sorted_paths = sorted(audio_paths, key=lambda p: p.name.lower())
        eligible_paths = sorted_paths
        excluded: List[Dict[str, Any]] = []
        speech_verification_payload: Dict[str, Any] = {}
        clip_rows: List[Dict[str, Any]] = []
        map_transcripts = transcripts
        map_classifier = classifier_scores
        map_boost = clip_quality_boost

        if skip_transcript:
            speech_verification_payload = {
                "mode": "skipped",
                "notAssessed": [{"file": p.name} for p in sorted_paths],
            }
            clip_rows = [
                {"file": p.name, "transcript": "", "speechStatus": "notAssessed"}
                for p in sorted_paths
            ]
        elif transcript_status != "ok":
            speech_verification_payload = {
                "mode": "transcript_unavailable",
                "detail": transcript_status,
            }
            clip_rows = [
                {
                    "file": p.name,
                    "transcript": transcripts.get(p, ""),
                    "speechStatus": "notAssessed",
                }
                for p in sorted_paths
            ]
        elif speech_verification_enabled:
            eligible_paths, excluded = partition_clips_by_speech(sorted_paths, transcripts)
            speech_verification_payload = {
                "mode": "whisper",
                "filter": "applied",
                "eligibleCount": len(eligible_paths),
                "excludedClips": excluded,
            }
            ex_reason = {row["file"]: row["reason"] for row in excluded}
            clip_rows = []
            eligible_set = set(eligible_paths)
            for p in sorted_paths:
                tx = transcripts.get(p, "")
                if p in eligible_set:
                    clip_rows.append(
                        {"file": p.name, "transcript": tx, "speechEligible": True}
                    )
                else:
                    clip_rows.append(
                        {
                            "file": p.name,
                            "transcript": tx,
                            "speechEligible": False,
                            "exclusionReason": ex_reason.get(p.name, "unknown"),
                        }
                    )
            map_transcripts = {p: transcripts[p] for p in eligible_paths if p in transcripts}
            map_classifier = {p: classifier_scores[p] for p in eligible_paths if p in classifier_scores}
            map_boost = {p: clip_quality_boost[p] for p in eligible_paths if p in clip_quality_boost}
        else:
            speech_verification_payload = {
                "mode": "whisper",
                "filter": "disabled",
            }
            clip_rows = [
                {
                    "file": p.name,
                    "transcript": transcripts.get(p, ""),
                    "speechEligible": True,
                    "speechNote": "filter_disabled",
                }
                for p in sorted_paths
            ]

        zero_speech_eligible = (
            speech_verification_enabled
            and not skip_transcript
            and transcript_status == "ok"
            and len(eligible_paths) == 0
        )

        if zero_speech_eligible:
            report_payload = build_mapping_report(
                [],
                transcripts={},
                classifier_scores={},
                classifier_weight=classifier_weight,
                clip_quality_boost={},
                speech_verification=speech_verification_payload,
                clips_override=clip_rows,
            )
            report_payload["transcription"] = transcript_status
            report_payload["classifier"] = {
                "status": classifier_status,
                "backend": classifier_backend if use_llm_classifier else "",
                "model": classifier_model if use_llm_classifier else "",
                "weight": classifier_weight,
            }
            report_payload["pack"] = {
                "universe": universe,
                "character": character,
                "packLabelSlug": pack_slug or None,
            }
            mapping_report_path = pack_dir / "mapping-report.json"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            mapping_report_path.write_text(json.dumps(report_payload, indent=2) + "\n", encoding="utf-8")
            recommendations.append(
                {
                    "ok": False,
                    "pack": pack_ctx,
                    "target": str(config_path),
                    "mappingReport": str(mapping_report_path),
                    "transcription": transcript_status,
                    "classifier": classifier_status,
                    "error": "No speech-eligible clips after verification.",
                    "speechVerification": speech_verification_payload,
                }
            )
            continue

        event_map, _signals = recommend_event_mapping(
            eligible_paths,
            transcripts=map_transcripts,
            classifier_scores=map_classifier,
            classifier_weight=classifier_weight,
            clip_quality_boost=map_boost,
        )
        report_payload = build_mapping_report(
            eligible_paths,
            transcripts=map_transcripts,
            classifier_scores=map_classifier,
            classifier_weight=classifier_weight,
            clip_quality_boost=map_boost,
            speech_verification=speech_verification_payload,
            clips_override=clip_rows,
        )
        payload = {
            "enabled": True,
            "soundRoot": "sounds",
            "soundPack": universe,
            "soundSubdir": sub,
            "events": {event: _normalize_event_shape(files) for event, files in event_map.items()},
        }
        mapping_report_path = pack_dir / "mapping-report.json"
        report_payload["transcription"] = transcript_status
        report_payload["classifier"] = {
            "status": classifier_status,
            "backend": classifier_backend if use_llm_classifier else "",
            "model": classifier_model if use_llm_classifier else "",
            "weight": classifier_weight,
        }
        report_payload["pack"] = {
            "universe": universe,
            "character": character,
            "packLabelSlug": pack_slug or None,
        }
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        mapping_report_path.write_text(json.dumps(report_payload, indent=2) + "\n", encoding="utf-8")
        rec_out: Dict[str, Any] = {
            "ok": True,
            "pack": pack_ctx,
            "target": str(config_path),
            "mappingReport": str(mapping_report_path),
            "transcription": transcript_status,
            "classifier": classifier_status,
            "speechVerification": speech_verification_payload,
        }
        recommendations.append(rec_out)
    return recommendations


def main(argv: Optional[list[str]] = None) -> int:
    faulthandler.enable(all_threads=True)
    parser = argparse.ArgumentParser(description="Download approved sound clips from manifest.")
    add_output_path_args(parser)
    parser.add_argument(
        "--manifest",
        type=str,
        default=None,
        help="Manifest path (default: <manifests-dir>/download-manifest.json).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Parse manifest and show actions only.")
    parser.add_argument("--limit", type=int, default=0, help="Max entries to download (0 = all).")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing target WAVs.")
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable progress output on stderr.",
    )
    parser.add_argument(
        "--no-recommended-config",
        action="store_true",
        help="Skip generating sounds/<universe>/<character>/sound-config.json recommendations.",
    )
    parser.add_argument(
        "--skip-transcript-analysis",
        action="store_true",
        help="Build recommendations using filename heuristics only (no Whisper transcription).",
    )
    parser.add_argument(
        "--no-speech-verification",
        action="store_true",
        help=(
            "When Whisper runs, include all WAVs in recommended config without excluding "
            "non-lexical/empty transcripts (for debugging; matches pre-filter behavior)."
        ),
    )
    parser.add_argument(
        "--whisper-model",
        type=str,
        default="tiny",
        help="faster-whisper model size to use (default: tiny).",
    )
    parser.add_argument(
        "--whisper-language",
        type=str,
        default="en",
        help="Preferred transcription language code (default: en). Use 'auto' for autodetect.",
    )
    parser.add_argument(
        "--whisper-device",
        type=str,
        default="auto",
        help="Whisper device (auto/cpu/cuda).",
    )
    parser.add_argument(
        "--whisper-compute-type",
        type=str,
        default="auto",
        help="Whisper compute type (auto/int8/float16/etc).",
    )
    parser.add_argument(
        "--overwrite-recommended-config",
        action="store_true",
        help="Overwrite existing recommended pack config files.",
    )
    parser.add_argument(
        "--disable-llm-classifier",
        action="store_true",
        help="Disable transcript classifier scoring; use heuristics only.",
    )
    parser.add_argument(
        "--classifier-backend",
        choices=("zero-shot", "sentence-embedding"),
        default="zero-shot",
        help=(
            "How to score transcripts vs hook types: NLI zero-shot (transformers) or "
            "cosine similarity of sentence embeddings vs hook descriptions (sentence-transformers)."
        ),
    )
    parser.add_argument(
        "--classifier-model",
        type=str,
        default=None,
        help=(
            "Hugging Face model id for the chosen backend. "
            f"Omitted: {DEFAULT_ZERO_SHOT_MODEL_CPU} (zero-shot on CPU), "
            f"{DEFAULT_ZERO_SHOT_MODEL} (zero-shot when CUDA is used), or "
            f"{DEFAULT_SENTENCE_EMBEDDING_MODEL} (sentence-embedding)."
        ),
    )
    parser.add_argument(
        "--classifier-weight",
        type=float,
        default=5.0,
        help="Weight applied to classifier score when blending rankings.",
    )
    parser.add_argument(
        "--use-existing-transcripts",
        action="store_true",
        help=(
            "When generating recommended configs, load per-pack transcripts.json if present "
            "instead of running Whisper (falls back to Whisper if missing)."
        ),
    )
    parser.add_argument(
        "--use-existing-classifier-scores",
        action="store_true",
        help=(
            "When generating recommended configs, load classifier-scores.json if present "
            "instead of running the classifier (falls back if missing)."
        ),
    )
    parser.add_argument(
        "--classifier-device",
        type=str,
        default="auto",
        help="Classifier models: auto/cpu/cuda/cuda:N (default: auto). Use a second GPU with e.g. cuda:1.",
    )
    parser.add_argument(
        "--preset",
        choices=("fast", "quality"),
        default=None,
        help="Shorthand: fast sets whisper tiny; quality sets whisper small (overrides --whisper-model).",
    )
    parser.add_argument(
        "--language-codes",
        type=str,
        default="ENG",
        help=(
            "Comma-separated language codes for manifest rows and for per-pack recommend-config "
            "(transcribe/classify): WAVs whose filename implies another language (e.g. *_DAN.wav) are skipped. "
            "Entries with no resolvable language pass through. Default: ENG."
        ),
    )
    parser.add_argument(
        "--no-language-filter",
        action="store_true",
        help="Do not filter manifest entries by languageCode / inferred path language.",
    )
    args = parser.parse_args(argv)
    if args.preset == "quality":
        args.whisper_model = "small"
    elif args.preset == "fast":
        args.whisper_model = "tiny"
    resolved_classifier_model = args.classifier_model
    if not resolved_classifier_model:
        resolved_classifier_model = (
            DEFAULT_SENTENCE_EMBEDDING_MODEL
            if args.classifier_backend == "sentence-embedding"
            else default_zero_shot_model_for_classifier_device(args.classifier_device)
        )
    cfg = build_config_from_args(args)
    manifest_path = (
        Path(args.manifest) if args.manifest else (cfg.manifests_dir / "download-manifest.json")
    )
    if not manifest_path.is_absolute():
        manifest_path = (Path.cwd() / manifest_path).resolve()
    lang_codes = parse_language_filter_arg(
        args.language_codes,
        no_filter=bool(args.no_language_filter),
    )

    return download_clips(
        cfg,
        manifest_path=manifest_path,
        dry_run=args.dry_run,
        limit=args.limit,
        overwrite=args.overwrite,
        progress=not args.no_progress,
        recommend_config=not args.no_recommended_config,
        skip_transcript=args.skip_transcript_analysis,
        whisper_model=args.whisper_model,
        whisper_language=None if args.whisper_language == "auto" else args.whisper_language,
        whisper_device=args.whisper_device,
        whisper_compute_type=args.whisper_compute_type,
        overwrite_recommended_config=args.overwrite_recommended_config,
        use_llm_classifier=not args.disable_llm_classifier,
        classifier_backend=args.classifier_backend,
        classifier_model=resolved_classifier_model,
        classifier_weight=args.classifier_weight,
        speech_verification_enabled=not args.no_speech_verification,
        use_existing_transcripts=args.use_existing_transcripts,
        use_existing_classifier_scores=args.use_existing_classifier_scores,
        classifier_device=args.classifier_device,
        language_filter_codes=lang_codes,
    )


if __name__ == "__main__":
    raise SystemExit(main())
