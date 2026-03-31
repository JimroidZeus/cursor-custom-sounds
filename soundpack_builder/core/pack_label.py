"""Normalize candidate link labels into stable pack keys and filesystem slugs."""

from __future__ import annotations

import hashlib
import re
import zlib
from typing import Any, Optional, Tuple

from soundpack_builder.core.hook_events import HOOK_EVENT_ORDER

# Keep path segments short so ``repo/sounds/u/c/<slug>/very-long-freesound-name.wav``
# stays under Windows MAX_PATH (~260) with typical project paths.
_MAX_PLAIN_SLUG_LEN = 32
_MAX_PREFIX = 24
_MAX_TOTAL_SLUG = 40

# Strip only known Cursor hook names so labels like "[special edition] Foo" stay distinct.
_LEADING_HOOK_TAG_RE = re.compile(
    "^\\[(" + "|".join(re.escape(e) for e in HOOK_EVENT_ORDER) + ")\\]\\s*"
)


def _strip_leading_cursor_hook_tag(text: str) -> str:
    """Remove a single leading ``[<hookEvent>]`` tag (normalize_manifests / authoring)."""
    return _LEADING_HOOK_TAG_RE.sub("", text, count=1)


def pack_label_key_and_slug(raw_label: Any) -> Tuple[str, Optional[str]]:
    """
    Map a candidate link ``label`` to (counter_key_suffix, path_slug).

    Missing or blank labels use ("", None) — the default soundpack folder
    (``sounds/<universe>/<character>/``) with no extra subdirectory.

    Distinct non-blank labels yield distinct slugs so discovery indices and
    download targets stay per-pack.

    Long human-readable labels are shortened to a safe path segment (≤40 chars):
    a readable prefix plus a hash of the full label text so different long
    labels never collide when truncated.
    """
    if raw_label is None:
        return "", None
    text = raw_label if isinstance(raw_label, str) else str(raw_label)
    stripped = text.strip()
    if not stripped:
        return "", None
    effective = _strip_leading_cursor_hook_tag(stripped).strip()
    if not effective:
        return "", None
    slug = _slugify(effective)
    if not slug:
        h = zlib.crc32(effective.encode("utf-8")) & 0xFFFFFFFF
        dig = f"{h:08x}"
        return f"p{dig}", f"p{dig}"
    if len(slug) <= _MAX_PLAIN_SLUG_LEN:
        return slug, slug
    digest = hashlib.sha256(effective.encode("utf-8")).hexdigest()[:8]
    prefix = slug[:_MAX_PREFIX].rstrip("-")
    if not prefix:
        return f"p{digest}", f"p{digest}"
    combined = f"{prefix}-{digest}"
    if len(combined) > _MAX_TOTAL_SLUG:
        combined = combined[:_MAX_TOTAL_SLUG].rstrip("-")
    return combined, combined


def _slugify(stripped: str) -> str:
    s = stripped.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s[:96]
