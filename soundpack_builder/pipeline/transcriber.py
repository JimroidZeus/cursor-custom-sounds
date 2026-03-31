"""
Transcribe all ``*.wav`` in a pack directory and write ``transcript_mapper.TRANSCRIPTS_JSON_NAME``.

Run::

    uv run --project soundpack_builder python -m soundpack_builder.pipeline.transcriber --pack-dir sounds/u/c
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from soundpack_builder.audio.transcript_mapper import (
    save_transcripts_sidecar,
    transcribe_with_whisper,
)
from soundpack_builder.core.config import add_output_path_args, build_config_from_args


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Transcribe WAVs in a pack folder and write transcripts.json sidecar.",
    )
    add_output_path_args(parser)
    parser.add_argument(
        "--pack-dir",
        type=str,
        required=True,
        help="Folder containing WAV files (e.g. sounds/<universe>/<character> or .../<packSlug>).",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable stderr progress lines.",
    )
    parser.add_argument(
        "--whisper-model",
        type=str,
        default="tiny",
        help="faster-whisper model size (default: tiny).",
    )
    parser.add_argument(
        "--whisper-language",
        type=str,
        default="en",
        help="Language code or 'auto' for autodetect.",
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
    args = parser.parse_args(argv)
    _ = build_config_from_args(args)
    pack_dir = Path(args.pack_dir).expanduser().resolve()
    if not pack_dir.is_dir():
        print(json.dumps({"ok": False, "error": f"Not a directory: {pack_dir}"}))
        return 1
    audio_paths = sorted(pack_dir.glob("*.wav"))
    if not audio_paths:
        print(json.dumps({"ok": False, "error": f"No WAV files in {pack_dir}"}))
        return 1
    transcripts = transcribe_with_whisper(
        audio_paths,
        model_size=args.whisper_model,
        language=None if args.whisper_language == "auto" else args.whisper_language,
        device=args.whisper_device,
        compute_type=args.whisper_compute_type,
        progress=not args.no_progress,
    )
    out_path = save_transcripts_sidecar(pack_dir, transcripts)
    print(
        json.dumps(
            {
                "ok": True,
                "packDir": str(pack_dir),
                "written": str(out_path),
                "clipCount": len(transcripts),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
