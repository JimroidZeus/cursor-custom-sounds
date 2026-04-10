"""Canonical layout under ``sounds/``: ``<universe>/<character>[/packLabelSlug]``."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple


def sound_subdir_for_pack(character: str, pack_slug: str) -> str:
    """
    Relative path segment under ``soundPack`` for hook configs.

    Matches on-disk layout: ``character`` only, or ``character/packLabelSlug`` when slug is set.
    """
    c = (character or "").strip()
    ps = (pack_slug or "").strip()
    if ps:
        return f"{c}/{ps}"
    return c


def pack_dir_under_sound_root(
    sound_dir: Path,
    universe: str,
    character: str,
    pack_slug: str = "",
) -> Path:
    """Absolute pack directory containing WAVs and per-pack sidecars."""
    u = (universe or "").strip()
    c = (character or "").strip()
    base = sound_dir / u / c
    ps = (pack_slug or "").strip()
    if ps:
        return base / ps
    return base


def parse_pack_key(raw: str) -> Tuple[str, str, Optional[str]]:
    """
    Parse ``--pack-key`` ``UNIVERSE/CHARACTER`` or ``UNIVERSE/CHARACTER/PACK_LABEL_SLUG``.

    Returns ``(universe, character, pack_label_slug)`` where the third element is ``None``
    when the key selects all packs for that character (any ``packLabelSlug``).
    """
    s = (raw or "").strip()
    if not s:
        raise ValueError("Pack key is empty.")
    parts = [p.strip() for p in s.split("/") if p.strip()]
    if len(parts) == 2:
        return parts[0], parts[1], None
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    raise ValueError(
        "Pack key must be UNIVERSE/CHARACTER or UNIVERSE/CHARACTER/PACK_LABEL_SLUG "
        f"(got {len(parts)} segment(s))."
    )


def entry_matches_pack_key(
    universe: str,
    character: str,
    pack_label_slug: Optional[str],
    *,
    key_universe: str,
    key_character: str,
    key_slug: Optional[str],
) -> bool:
    """Whether a manifest row's pack identity matches a parsed pack key."""
    if universe != key_universe or character != key_character:
        return False
    if key_slug is None:
        return True
    row_slug = (pack_label_slug or "").strip()
    return row_slug == key_slug
