"""
Classify transcripts for hook events and write ``classifier-scores.json`` in a pack directory.

Expects ``transcripts.json`` from the transcriber step (or compatible shape). Run::

    uv run --project soundpack_builder python -m soundpack_builder.pipeline.classifier --pack-dir sounds/u/c
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from soundpack_builder.audio.transcript_mapper import (
    DEFAULT_SENTENCE_EMBEDDING_MODEL,
    ClassifierBackend,
    default_classifier_backend_for_environment,
    default_zero_shot_model_for_classifier_device,
    classify_hook_events,
    load_transcripts_sidecar,
    save_classifier_scores_sidecar,
)
from soundpack_builder.core.config import add_output_path_args, build_config_from_args


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run transcript classifier for a pack and write classifier-scores.json.",
    )
    add_output_path_args(parser)
    parser.add_argument(
        "--pack-dir",
        type=str,
        required=True,
        help="Pack folder containing transcripts.json and WAV files.",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable stderr progress lines.",
    )
    parser.add_argument(
        "--classifier-backend",
        choices=("auto", "zero-shot", "sentence-embedding"),
        default="auto",
        help=(
            "Classifier backend. auto: sentence-embedding on Windows CPU, else zero-shot "
            "(matches downloader defaults)."
        ),
    )
    parser.add_argument(
        "--classifier-model",
        type=str,
        default=None,
        help="Hugging Face model id (defaults per backend).",
    )
    parser.add_argument(
        "--classifier-device",
        type=str,
        default="auto",
        help="Device for classifier models (auto/cpu/cuda/cuda:N); default: auto.",
    )
    args = parser.parse_args(argv)
    _ = build_config_from_args(args)
    resolved_backend: ClassifierBackend = (
        default_classifier_backend_for_environment(args.classifier_device)
        if args.classifier_backend == "auto"
        else args.classifier_backend
    )
    pack_dir = Path(args.pack_dir).expanduser().resolve()
    if not pack_dir.is_dir():
        print(json.dumps({"ok": False, "error": f"Not a directory: {pack_dir}"}))
        return 1
    transcripts = load_transcripts_sidecar(pack_dir)
    if transcripts is None:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"Missing or invalid transcripts sidecar in {pack_dir}",
                }
            )
        )
        return 1
    resolved_model = args.classifier_model
    if not resolved_model:
        resolved_model = (
            DEFAULT_SENTENCE_EMBEDDING_MODEL
            if resolved_backend == "sentence-embedding"
            else default_zero_shot_model_for_classifier_device(args.classifier_device)
        )
    scores = classify_hook_events(
        transcripts,
        backend=resolved_backend,
        model_name=resolved_model,
        progress=not args.no_progress,
        classifier_device=args.classifier_device,
    )
    out_path = save_classifier_scores_sidecar(pack_dir, scores)
    print(
        json.dumps(
            {
                "ok": True,
                "packDir": str(pack_dir),
                "written": str(out_path),
                "backend": resolved_backend,
                "model": resolved_model,
                "clipCount": len(scores),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
