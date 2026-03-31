"""RIFF WAV detection and ffmpeg conversion to mono PCM WAV (shared by downloader and repair_wavs)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from soundpack_builder.core.media_urls import looks_like_html_file


def is_riff_wave(path: Path) -> bool:
    """True if file looks like a PCM WAV (RIFF…WAVE) suitable for ``wave`` / Cursor playback."""
    try:
        with path.open("rb") as f:
            head = f.read(12)
    except OSError:
        return False
    return len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WAVE"


def convert_to_wav(input_path: Path, output_path: Path, *, sample_rate: int = 44100) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if looks_like_html_file(input_path):
        raise RuntimeError(
            "Input looks like HTML, not audio (often a login or error page). "
            "Fix the download URL or use Freesound API preview URLs."
        )

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(
            "ffmpeg not found. Install ffmpeg or provide direct .wav URLs."
        )

    # Mono 16-bit PCM WAV for Cursor. Keep flags minimal; muxer follows output suffix.
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(input_path),
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        details = stderr or stdout or "ffmpeg failed without output"
        raise RuntimeError(f"ffmpeg failed ({proc.returncode}): {details}")
