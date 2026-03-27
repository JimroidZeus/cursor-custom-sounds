"""
Helpers for checking WAV playback duration constraints.
"""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Dict, List, Tuple


def read_wav_duration_seconds(path: Path) -> float:
    """
    Return WAV duration in seconds.

    Raises wave.Error / OSError for unreadable or invalid WAV files.
    """
    with wave.open(str(path), "rb") as wav_file:
        frame_rate = wav_file.getframerate()
        frame_count = wav_file.getnframes()
    if frame_rate <= 0:
        raise ValueError(f"Invalid WAV frame rate in {path}: {frame_rate}")
    return frame_count / float(frame_rate)


def validate_wav_durations(
    sound_dir: Path,
    *,
    max_seconds: float,
    warn_seconds: float,
) -> Tuple[bool, Dict[str, object]]:
    """
    Validate all WAV files under sound_dir against duration limits.

    Returns (ok, payload). payload contains:
    - wavFilesChecked
    - warnings: list of warning dicts
    - failures: list of failure dicts
    """
    wav_files = sorted(sound_dir.rglob("*.wav"))
    warnings: List[Dict[str, object]] = []
    failures: List[Dict[str, object]] = []

    for wav_path in wav_files:
        try:
            seconds = read_wav_duration_seconds(wav_path)
        except Exception as ex:
            failures.append(
                {
                    "path": str(wav_path),
                    "error": f"Could not read WAV duration: {ex}",
                }
            )
            continue

        if seconds > max_seconds:
            failures.append(
                {
                    "path": str(wav_path),
                    "seconds": round(seconds, 3),
                    "maxSeconds": max_seconds,
                    "error": "Playback duration exceeds max limit.",
                }
            )
        elif warn_seconds > 0 and seconds > warn_seconds:
            warnings.append(
                {
                    "path": str(wav_path),
                    "seconds": round(seconds, 3),
                    "warnSeconds": warn_seconds,
                    "message": "Playback duration is above warning threshold.",
                }
            )

    payload: Dict[str, object] = {
        "wavFilesChecked": len(wav_files),
        "warnings": warnings,
        "failures": failures,
        "maxSeconds": max_seconds,
        "warnSeconds": warn_seconds,
    }
    return len(failures) == 0, payload
