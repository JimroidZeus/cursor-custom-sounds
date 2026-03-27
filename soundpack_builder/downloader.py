"""
Download approved sound clips into `sounds/<universe>/<character>/`.

This does not scrape sites. It expects each manifest entry to provide a direct
download URL for the audio file.

If the URL is not a WAV, the script will attempt to convert it to WAV using
`ffmpeg` (if available).
"""

from __future__ import annotations

import argparse
import json
import sys
import shutil
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .config import BuilderConfig, add_output_path_args, build_config_from_args
from .transcript_mapper import (
    build_mapping_report,
    classify_with_zero_shot,
    recommend_event_mapping,
    transcribe_with_whisper,
)


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

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ClipEntry":
        return ClipEntry(
            universe=str(d["universe"]),
            character=str(d["character"]),
            url=str(d["url"]),
            targetFile=str(d["targetFile"]) if d.get("targetFile") else None,
            source_page=d.get("source_page"),
            pathInArchive=d.get("pathInArchive") or d.get("path_in_archive"),
            note=d.get("note"),
        )


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


def convert_to_wav(input_path: Path, output_path: Path, *, sample_rate: int = 44100) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(
            "ffmpeg not found. Install ffmpeg or provide direct .wav URLs."
        )

    # Convert to mono 16-bit PCM WAV, which Cursor's player supports.
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(input_path),
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "wav",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        details = stderr or stdout or "ffmpeg failed without output"
        raise RuntimeError(f"ffmpeg failed ({proc.returncode}): {details}")


def _normalize_archive_path(path: str) -> str:
    return path.replace("\\", "/").strip("/").lower()


def extract_from_zip(zip_path: Path, *, path_in_archive: Optional[str], temp_dir: Path) -> Path:
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
                raise RuntimeError(
                    "Zip archive contains multiple audio files. Provide `pathInArchive` to pick one."
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
    width = 24
    done = int((index / max(total, 1)) * width)
    bar = "#" * done + "-" * (width - done)
    label_name = _output_filename(entry)
    label = f"{entry.universe}/{entry.character}/{label_name}"
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
    classifier_model: str,
    classifier_weight: float,
) -> int:
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest does not exist: {manifest_path}")

    entries = load_manifest(manifest_path)
    if limit and limit > 0:
        entries = entries[:limit]

    if not entries:
        print(json.dumps({"ok": True, "message": "No manifest entries to download."}))
        return 0

    downloaded_dir = cfg.downloads_dir
    downloaded_dir.mkdir(parents=True, exist_ok=True)

    results: List[Dict[str, Any]] = []
    packs_seen: Set[Tuple[str, str]] = set()

    total = len(entries)
    for idx, e in enumerate(entries):
        current = idx + 1
        _print_progress(index=current, total=total, entry=e, status="start", enabled=progress)
        target_dir = cfg.sound_dir / e.universe / e.character
        target_path = target_dir / _output_filename(e)
        packs_seen.add((e.universe, e.character))

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
        input_path = downloaded_dir / f"{e.universe}__{e.character}__{idx}{input_ext}"

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
            _print_progress(index=current, total=total, entry=e, status="downloading", enabled=progress)
            download_url(e.url, input_path)

            target_path.parent.mkdir(parents=True, exist_ok=True)

            lower_url = e.url.lower()
            if input_path.suffix.lower() == ".zip" or lower_url.endswith(".zip"):
                _print_progress(index=current, total=total, entry=e, status="extracting", enabled=progress)
                extracted = extract_from_zip(
                    input_path,
                    path_in_archive=e.pathInArchive,
                    temp_dir=downloaded_dir,
                )
                # extracted is expected to be audio; keep basename but normalize to wav format.
                if extracted.suffix.lower() == ".wav":
                    extracted.replace(target_path)
                else:
                    _print_progress(index=current, total=total, entry=e, status="converting", enabled=progress)
                    convert_to_wav(extracted, target_path)
            else:
                if input_path.suffix.lower() == ".wav":
                    input_path.replace(target_path)
                else:
                    _print_progress(index=current, total=total, entry=e, status="converting", enabled=progress)
                    convert_to_wav(input_path, target_path)

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

    print(json.dumps({"ok": True, "results": results}, indent=2))
    if recommend_config and not dry_run:
        recommended = _write_recommended_configs(
            cfg,
            packs_seen,
            skip_transcript=skip_transcript,
            whisper_model=whisper_model,
            whisper_language=whisper_language,
            whisper_device=whisper_device,
            whisper_compute_type=whisper_compute_type,
            overwrite=overwrite_recommended_config,
            progress=progress,
            use_llm_classifier=use_llm_classifier,
            classifier_model=classifier_model,
            classifier_weight=classifier_weight,
        )
        print(json.dumps({"ok": True, "recommendedConfigs": recommended}, indent=2))
    return 0


def _normalize_event_shape(files: List[str]) -> Any:
    if len(files) == 1:
        return files[0]
    return files


def _write_recommended_configs(
    cfg: BuilderConfig,
    packs_seen: Set[Tuple[str, str]],
    *,
    skip_transcript: bool,
    whisper_model: str,
    whisper_language: Optional[str],
    whisper_device: str,
    whisper_compute_type: str,
    overwrite: bool,
    progress: bool = True,
    use_llm_classifier: bool = True,
    classifier_model: str = "valhalla/distilbart-mnli-12-1",
    classifier_weight: float = 5.0,
) -> List[Dict[str, Any]]:
    recommendations: List[Dict[str, Any]] = []
    sorted_packs = sorted(packs_seen)
    pack_audio_counts: Dict[Tuple[str, str], int] = {}
    total_audio = 0
    universe_pack_totals: Dict[str, int] = {}
    universe_audio_totals: Dict[str, int] = {}
    for universe, character in sorted_packs:
        audio_count = len(list((cfg.sound_dir / universe / character).glob("*.wav")))
        pack_audio_counts[(universe, character)] = audio_count
        total_audio += audio_count
        universe_pack_totals[universe] = universe_pack_totals.get(universe, 0) + 1
        universe_audio_totals[universe] = universe_audio_totals.get(universe, 0) + audio_count

    if progress:
        print(
            json.dumps(
                {
                    "phase": "recommend-config-start",
                    "packsTotal": len(sorted_packs),
                    "audioTotal": total_audio,
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
    universe_transcribed_done: Dict[str, int] = {}
    universe_classified_done: Dict[str, int] = {}

    def _render_counter_bar(done: int, total: int, width: int = 24) -> str:
        bar_done = int((done / max(total, 1)) * width)
        return "#" * bar_done + "-" * (width - bar_done)

    def _print_rollup_progress(*, label: str, done: int, total: int) -> None:
        if not progress:
            return
        print(
            f"[{_render_counter_bar(done, total)}] {done}/{max(total, 1)} {label}",
            file=sys.stderr,
            flush=True,
        )

    for universe, character in sorted_packs:
        packs_done += 1
        if progress:
            _print_rollup_progress(
                label=f"packs: {universe}/{character}",
                done=packs_done,
                total=len(sorted_packs),
            )

        pack_dir = cfg.sound_dir / universe / character
        config_path = pack_dir / "sound-config.json"
        if config_path.exists() and not overwrite:
            recommendations.append(
                {
                    "ok": True,
                    "skipped": True,
                    "pack": f"{universe}/{character}",
                    "target": str(config_path),
                    "reason": "recommended config exists (use --overwrite-recommended-config)",
                }
            )
            continue

        audio_paths = sorted(pack_dir.glob("*.wav"))
        if not audio_paths:
            recommendations.append(
                {
                    "ok": False,
                    "pack": f"{universe}/{character}",
                    "target": str(config_path),
                    "error": "No WAV files found for pack.",
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
                universe_transcribed_done[universe] = universe_transcribed_done.get(universe, 0) + 1
                _print_rollup_progress(
                    label=f"transcribe(all files): {universe}/{character}",
                    done=transcribed_done,
                    total=total_audio,
                )
                _print_rollup_progress(
                    label=f"transcribe({universe})",
                    done=universe_transcribed_done[universe],
                    total=universe_audio_totals.get(universe, 0),
                )

            def _on_classifier_progress(
                _index: int, _total: int, _clip_path: Path, status: str, _context: str
            ) -> None:
                nonlocal classified_done
                if status not in {"classify-done", "classify-error", "classify-skip"}:
                    return
                classified_done += 1
                universe_classified_done[universe] = universe_classified_done.get(universe, 0) + 1
                _print_rollup_progress(
                    label=f"classify(all files): {universe}/{character}",
                    done=classified_done,
                    total=total_audio,
                )
                _print_rollup_progress(
                    label=f"classify({universe})",
                    done=universe_classified_done[universe],
                    total=universe_audio_totals.get(universe, 0),
                )

            try:
                transcripts = transcribe_with_whisper(
                    audio_paths,
                    model_size=whisper_model,
                    language=whisper_language,
                    device=whisper_device,
                    compute_type=whisper_compute_type,
                    progress=progress,
                    progress_context=f"{universe}/{character}",
                    progress_callback=_on_transcript_progress,
                )
                transcript_status = "ok"
                if use_llm_classifier:
                    try:
                        classifier_scores = classify_with_zero_shot(
                            transcripts,
                            model_name=classifier_model,
                            progress=progress,
                            progress_context=f"{universe}/{character}",
                            progress_callback=_on_classifier_progress,
                        )
                        classifier_status = f"ok ({classifier_model})"
                    except Exception as ex:
                        classifier_status = f"fallback: {ex}"
                        classifier_scores = {}
                else:
                    classifier_status = "disabled"
            except Exception as ex:
                transcript_status = f"fallback: {ex}"
                transcripts = {}
                classifier_status = "transcript-unavailable"

        event_map, _signals = recommend_event_mapping(
            audio_paths,
            transcripts=transcripts,
            classifier_scores=classifier_scores,
            classifier_weight=classifier_weight,
        )
        report_payload = build_mapping_report(
            audio_paths,
            transcripts=transcripts,
            classifier_scores=classifier_scores,
            classifier_weight=classifier_weight,
        )
        payload = {
            "enabled": True,
            "soundRoot": "sounds",
            "soundPack": universe,
            "soundSubdir": character,
            "events": {event: _normalize_event_shape(files) for event, files in event_map.items()},
        }
        mapping_report_path = pack_dir / "mapping-report.json"
        report_payload["transcription"] = transcript_status
        report_payload["classifier"] = {
            "status": classifier_status,
            "model": classifier_model if use_llm_classifier else "",
            "weight": classifier_weight,
        }
        report_payload["pack"] = {"universe": universe, "character": character}
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        mapping_report_path.write_text(json.dumps(report_payload, indent=2) + "\n", encoding="utf-8")
        recommendations.append(
            {
                "ok": True,
                "pack": f"{universe}/{character}",
                "target": str(config_path),
                "mappingReport": str(mapping_report_path),
                "transcription": transcript_status,
                "classifier": classifier_status,
            }
        )
    return recommendations


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Download approved sound clips from manifest.")
    add_output_path_args(parser)
    parser.add_argument(
        "--manifest",
        type=str,
        default=None,
        help="Manifest path (default: <manifests-dir>/tier1-approved.json).",
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
        help="Disable zero-shot classifier scoring; use heuristics only.",
    )
    parser.add_argument(
        "--classifier-model",
        type=str,
        default="valhalla/distilbart-mnli-12-1",
        help="Hugging Face zero-shot model for event inference.",
    )
    parser.add_argument(
        "--classifier-weight",
        type=float,
        default=5.0,
        help="Weight applied to classifier score when blending rankings.",
    )
    args = parser.parse_args(argv)
    cfg = build_config_from_args(args)
    manifest_path = (
        Path(args.manifest) if args.manifest else (cfg.manifests_dir / "tier1-approved.json")
    )
    if not manifest_path.is_absolute():
        manifest_path = (Path.cwd() / manifest_path).resolve()
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
        classifier_model=args.classifier_model,
        classifier_weight=args.classifier_weight,
    )


if __name__ == "__main__":
    raise SystemExit(main())
