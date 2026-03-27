"""
Soundpack builder pipeline: manifests, templates, validation, downloads,
and phased sourcing (`python -m soundpack_builder.phased_sourcing`).

This package is intentionally separate from Cursor hook runtime (`.cursor/hooks/`).
"""

from .config import BuilderConfig, add_output_path_args, build_config_from_args

__all__ = ["BuilderConfig", "add_output_path_args", "build_config_from_args"]
