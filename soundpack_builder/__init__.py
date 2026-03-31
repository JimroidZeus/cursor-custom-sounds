"""
Soundpack builder: manifests, downloads, templates, and validation.

**Canonical pipeline** (see `soundpack_builder.pipeline.workflow`):

1. ``search_hints`` — browser research helpers (DuckDuckGo URLs).
2. ``candidates`` — classify links → ``manifests/candidates/``.
3. ``downloader`` — fetch audio into ``sounds/``.
4. ``templates`` — per-pack hook config stubs.
5. ``validate`` — template + WAV checks.

Run: ``python -m soundpack_builder.pipeline.workflow`` for a printable summary;
``--sourcing-report`` lists verified sites and hook-pack characters.
Optional: ``python -m soundpack_builder.tools.freesound_resolve`` (``FREESOUND_API_KEY``)
for Freesound URLs in ``candidates/review.json`` — see ``docs/sound-sourcing.md``.

This package is separate from Cursor hook runtime (``.cursor/hooks/``).

``workflow`` is not imported at package load time so ``python -m soundpack_builder.pipeline.workflow``
does not trigger a duplicate-import RuntimeWarning.
"""

from __future__ import annotations

from typing import Any

from soundpack_builder.core.config import BuilderConfig, add_output_path_args, build_config_from_args

__all__ = [
    "BuilderConfig",
    "PIPELINE_STEPS",
    "add_output_path_args",
    "build_config_from_args",
    "build_sourcing_report",
    "describe_pipeline",
]


def __getattr__(name: str) -> Any:
    if name == "PIPELINE_STEPS":
        from soundpack_builder.pipeline.workflow import PIPELINE_STEPS

        return PIPELINE_STEPS
    if name == "build_sourcing_report":
        from soundpack_builder.pipeline.workflow import build_sourcing_report

        return build_sourcing_report
    if name == "describe_pipeline":
        from soundpack_builder.pipeline.workflow import describe_pipeline

        return describe_pipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

