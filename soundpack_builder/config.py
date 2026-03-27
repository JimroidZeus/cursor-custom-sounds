"""
Centralized paths for the soundpack builder. Defaults match this repo layout.

Override order (later wins): defaults → environment variables → CLI flags.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace  # noqa: F401 — replace used in build_config_from_args
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

# Environment variable names (optional overrides)
ENV_REPO_ROOT = "SOUNDPACK_BUILDER_REPO_ROOT"
ENV_MANIFESTS_DIR = "SOUNDPACK_BUILDER_MANIFESTS_DIR"
ENV_CONFIGS_DIR = "SOUNDPACK_BUILDER_CONFIGS_DIR"
ENV_SOUNDS_DIR = "SOUNDPACK_BUILDER_SOUNDS_DIR"
ENV_WAV_DURATION_WARN_SECONDS = "SOUNDPACK_BUILDER_WAV_DURATION_WARN_SECONDS"
ENV_WAV_DURATION_MAX_SECONDS = "SOUNDPACK_BUILDER_WAV_DURATION_MAX_SECONDS"
ENV_HF_TOKEN = "HF_TOKEN"


def _load_dotenv_if_present() -> None:
    """Load soundpack_builder/.env into os.environ (does not override existing keys)."""
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)


_load_dotenv_if_present()


def hf_token() -> Optional[str]:
    """Hugging Face Hub token from HF_TOKEN (e.g. set in soundpack_builder/.env)."""
    v = os.environ.get(ENV_HF_TOKEN, "").strip()
    return v or None


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _env_path(key: str) -> Optional[Path]:
    v = os.environ.get(key, "").strip()
    if not v:
        return None
    return Path(v).expanduser().resolve()


def env_float(key: str, default: float) -> float:
    v = os.environ.get(key, "").strip()
    if not v:
        return default
    try:
        return float(v)
    except ValueError:
        return default


@dataclass(frozen=True)
class BuilderConfig:
    """Paths used by tier1 candidates, templates, validate, downloader."""

    repo_root: Path
    manifests_dir: Path
    configs_dir: Path
    sound_dir: Path

    @property
    def sound_config_dir(self) -> Path:
        return self.configs_dir / "sound-config"

    @property
    def downloads_dir(self) -> Path:
        return self.manifests_dir / "_downloads"

    @classmethod
    def defaults(cls, repo_root: Optional[Path] = None) -> "BuilderConfig":
        rr = repo_root or _default_repo_root()
        return cls(
            repo_root=rr.resolve(),
            manifests_dir=rr / "manifests",
            configs_dir=rr / "configs",
            sound_dir=rr / "sounds",
        )

    @classmethod
    def from_env(cls, repo_root: Optional[Path] = None) -> "BuilderConfig":
        base = cls.defaults(repo_root)
        rr = _env_path(ENV_REPO_ROOT) or base.repo_root
        manifests = _env_path(ENV_MANIFESTS_DIR) or (rr / "manifests")
        configs = _env_path(ENV_CONFIGS_DIR) or (rr / "configs")
        sounds = _env_path(ENV_SOUNDS_DIR) or (rr / "sounds")
        return cls(
            repo_root=rr.resolve(),
            manifests_dir=manifests.resolve(),
            configs_dir=configs.resolve(),
            sound_dir=sounds.resolve(),
        )


def add_output_path_args(parser: Any) -> None:
    """Add shared CLI flags for builder output paths."""
    parser.add_argument(
        "--repo-root",
        type=str,
        default=None,
        help="Repository root (default: auto-detected from package location).",
    )
    parser.add_argument(
        "--out-manifests-dir",
        type=str,
        default=None,
        help=f"Override manifests directory (env: {ENV_MANIFESTS_DIR}).",
    )
    parser.add_argument(
        "--out-configs-dir",
        type=str,
        default=None,
        help=f"Override configs directory (env: {ENV_CONFIGS_DIR}).",
    )
    parser.add_argument(
        "--out-sounds-dir",
        type=str,
        default=None,
        help=f"Override sounds output directory (env: {ENV_SOUNDS_DIR}).",
    )


def add_wav_duration_args(
    parser: Any,
    *,
    default_warn_seconds: float = 10.0,
    default_max_seconds: float = 15.0,
) -> None:
    """
    Add shared WAV duration validation args with env-backed defaults.
    """
    warn_default = env_float(ENV_WAV_DURATION_WARN_SECONDS, default_warn_seconds)
    max_default = env_float(ENV_WAV_DURATION_MAX_SECONDS, default_max_seconds)
    parser.add_argument(
        "--skip-wav-duration-check",
        action="store_true",
        help="Skip checking WAV playback duration under sounds/.",
    )
    parser.add_argument(
        "--max-wav-seconds",
        type=float,
        default=max_default,
        help=(
            "Maximum allowed WAV playback duration in seconds "
            f"(default/env: {ENV_WAV_DURATION_MAX_SECONDS} -> {max_default})."
        ),
    )
    parser.add_argument(
        "--warn-wav-seconds",
        type=float,
        default=warn_default,
        help=(
            "Warning threshold for WAV playback duration in seconds "
            f"(default/env: {ENV_WAV_DURATION_WARN_SECONDS} -> {warn_default})."
        ),
    )


def build_config_from_args(args: Any) -> BuilderConfig:
    """Apply CLI overrides on top of env-based config."""
    cfg = BuilderConfig.from_env()
    rr = Path(args.repo_root).expanduser().resolve() if getattr(args, "repo_root", None) else cfg.repo_root
    manifests = (
        Path(args.out_manifests_dir).expanduser().resolve()
        if getattr(args, "out_manifests_dir", None)
        else cfg.manifests_dir
    )
    configs = (
        Path(args.out_configs_dir).expanduser().resolve()
        if getattr(args, "out_configs_dir", None)
        else cfg.configs_dir
    )
    sounds = (
        Path(args.out_sounds_dir).expanduser().resolve()
        if getattr(args, "out_sounds_dir", None)
        else cfg.sound_dir
    )
    if getattr(args, "repo_root", None):
        # If only repo-root changed, rebuild defaults under new root unless other dirs were set.
        if not getattr(args, "out_manifests_dir", None):
            manifests = rr / "manifests"
        if not getattr(args, "out_configs_dir", None):
            configs = rr / "configs"
        if not getattr(args, "out_sounds_dir", None):
            sounds = rr / "sounds"
    return replace(
        cfg,
        repo_root=rr,
        manifests_dir=manifests,
        configs_dir=configs,
        sound_dir=sounds,
    )
