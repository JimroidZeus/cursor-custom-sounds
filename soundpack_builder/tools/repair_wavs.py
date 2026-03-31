"""
Re-encode ``sounds/**/*.wav`` that are not standard PCM RIFF WAV.

Use when ``validate`` reports ``file does not start with RIFF id`` — often MP3/OGG
saved with a ``.wav`` name from older downloads. Matches ``downloader`` output:
mono 16-bit PCM via ffmpeg.

Requires ffmpeg on PATH. Run::

    python -m soundpack_builder.tools.repair_wavs
    python -m soundpack_builder.tools.repair_wavs --dry-run

Files that are HTML (e.g. Freesound error pages saved as ``.wav``) are listed under
``htmlPlaceholders`` in the JSON output and are not sent to ffmpeg.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple

from soundpack_builder.audio.audio_duration import read_wav_duration_seconds
from soundpack_builder.audio.wav_convert import convert_to_wav, is_riff_wave
from soundpack_builder.core.config import BuilderConfig, add_output_path_args, build_config_from_args
from soundpack_builder.core.console_progress import print_progress_line, print_status
from soundpack_builder.core.media_urls import looks_like_html_file

_HTML_NOT_REPAIRABLE = (
    "File content is HTML (e.g. Freesound login or error page saved as .wav), not audio. "
    "Re-download with a direct preview URL or run freesound_resolve with FREESOUND_API_KEY."
)


def needs_repair(path: Path) -> bool:
    """True if file is missing, empty, not RIFF WAVE, or ``wave`` cannot read duration."""
    try:
        if not path.is_file():
            return True
        if path.stat().st_size == 0:
            return True
        if not is_riff_wave(path):
            return True
        read_wav_duration_seconds(path)
        return False
    except OSError:
        return True
    except Exception:
        return True


def repair_one(path: Path) -> None:
    """Re-encode in place to mono 16-bit PCM WAV (same path)."""
    fd, tmp_name = tempfile.mkstemp(suffix=".repairing.wav", dir=path.parent)
    os.close(fd)
    out = Path(tmp_name)
    try:
        convert_to_wav(path, out)
        os.replace(out, path)
    except Exception:
        if out.exists():
            try:
                out.unlink()
            except OSError:
                pass
        raise


def scan_and_repair(
    sound_dir: Path,
    *,
    dry_run: bool,
    progress: bool,
) -> Tuple[int, int, List[str], List[str]]:
    """
    Returns (repaired_count, skipped_ok_count, html_placeholder_messages, other_errors).

    HTML placeholders are reported separately: ffmpeg is not run for them (not repairable in-place).
    """
    wavs = sorted(sound_dir.rglob("*.wav"))
    repaired = 0
    skipped_ok = 0
    html_placeholders: List[str] = []
    errors: List[str] = []

    total = len(wavs)
    if progress and total:
        print_status(f"Scanning {total} WAV file(s) under {sound_dir}...", file=sys.stderr)

    for i, path in enumerate(wavs, start=1):
        if progress:
            rel = str(path)
            if len(rel) > 56:
                rel = "..." + rel[-53:]
            print_progress_line(
                index=i,
                total=total,
                label="repair-wav",
                detail=rel,
                file=sys.stderr,
            )

        if not needs_repair(path):
            skipped_ok += 1
            continue

        if looks_like_html_file(path):
            html_placeholders.append(f"{path}: {_HTML_NOT_REPAIRABLE}")
            continue

        if dry_run:
            repaired += 1
            continue

        try:
            repair_one(path)
            repaired += 1
        except Exception as ex:
            errors.append(f"{path}: {ex}")

    return repaired, skipped_ok, html_placeholders, errors


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Re-encode WAVs that are not valid PCM RIFF (e.g. MP3 with .wav extension). "
            "Requires ffmpeg."
        ),
    )
    add_output_path_args(parser)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files that would be re-encoded without writing.",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable stderr progress lines.",
    )
    args = parser.parse_args(argv)
    cfg = build_config_from_args(args)

    repaired, skipped_ok, html_placeholders, errors = scan_and_repair(
        cfg.sound_dir,
        dry_run=args.dry_run,
        progress=not args.no_progress,
    )

    payload = {
        "ok": len(html_placeholders) == 0 and len(errors) == 0,
        "dryRun": args.dry_run,
        "repaired": repaired,
        "alreadyOk": skipped_ok,
        "htmlPlaceholders": [{"message": e} for e in html_placeholders],
        "errors": [{"message": e} for e in errors],
    }
    print(json.dumps(payload, indent=2))

    for h in html_placeholders:
        print(f"[HTML] {h}", file=sys.stderr)
    for e in errors:
        print(f"[FAIL] {e}", file=sys.stderr)
    if html_placeholders or errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
