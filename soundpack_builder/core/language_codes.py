"""Language codes for discovery/download filtering (2+ letter abbreviations, e.g. ENG, JP, GER).

Resolved code is explicit metadata or inferred from path/URL tokens. When no code is known,
filtering passes the row through (unknown does not imply English).
"""

from __future__ import annotations

import re
from typing import FrozenSet, Optional, Set

# Default filter when the CLI omits --no-language-filter.
DEFAULT_LANGUAGE_FILTER: FrozenSet[str] = frozenset({"ENG"})

# Map path/filename tokens (lowercase) to canonical uppercase codes.
_KNOWN_TOKEN_TO_CODE: dict[str, str] = {
    "jp": "JP",
    "jpn": "JP",
    "ja": "JP",
    "en": "ENG",
    "eng": "ENG",
    "us": "ENG",
    "uk": "ENG",
    "de": "GER",
    "ger": "GER",
    "deu": "GER",
    "da": "DAN",
    "dan": "DAN",
    "fr": "FRE",
    "fre": "FRE",
    "fra": "FRE",
}

# Suffix before audio extension: foo_jp.wav, bar_eng.mp3
_SUFFIX_LANG = re.compile(
    r"[_\-](?P<code>[A-Za-z]{2,4})\.(?:wav|mp3|ogg|flac|m4a)(?:\?.*)?$",
    re.IGNORECASE,
)

# Region markers often used for English dialogue packs
_REGION_ENG = re.compile(r"\(\s*US\s*\)|\(\s*UK\s*\)|\bEN[\-_]US\b|\bEN[\-_]GB\b", re.IGNORECASE)


def normalize_language_code(raw: Optional[str]) -> Optional[str]:
    """Return uppercase A-Z code with length >= 2, or None."""
    if raw is None:
        return None
    s = str(raw).strip().upper()
    if len(s) < 2 or not s.isalpha():
        return None
    return s


def infer_language_from_text(*parts: str) -> Optional[str]:
    """Infer a language code from path segments, basenames, labels, or URLs."""
    combined = " ".join(p for p in parts if p)
    if not combined:
        return None
    text = combined.replace("\\", "/")

    if _REGION_ENG.search(text):
        return "ENG"

    # Prefer ``*_LANG.ext`` at end of basename (game rips) before token scan, so e.g.
    # ``CLIP_ENG_DAN.wav`` resolves to DAN, not ENG from the ``eng`` token.
    base = text.rsplit("/", 1)[-1]
    m = _SUFFIX_LANG.search(base)
    if m:
        code = normalize_language_code(m.group("code"))
        if code:
            return code

    low = text.lower()
    for tok in re.split(r"[/\\_\-().\[\]\s]+", low):
        if not tok:
            continue
        if tok in _KNOWN_TOKEN_TO_CODE:
            return _KNOWN_TOKEN_TO_CODE[tok]

    return None


def resolve_language_code(explicit: Optional[str], *hints: str) -> Optional[str]:
    """Prefer explicit normalized code; else first inference from hints."""
    n = normalize_language_code(explicit)
    if n:
        return n
    for h in hints:
        inf = infer_language_from_text(h)
        if inf:
            return inf
    return None


def parse_language_filter_arg(raw: Optional[str], *, no_filter: bool) -> Optional[Set[str]]:
    """CLI: None means no filtering; otherwise uppercase code set."""
    if no_filter:
        return set()
    if raw is None:
        return set(DEFAULT_LANGUAGE_FILTER)
    s = raw.strip()
    if not s:
        return set()
    return {x.strip().upper() for x in s.split(",") if x.strip()}


def passes_language_filter(resolved: Optional[str], allowed: Optional[Set[str]]) -> bool:
    """If allowed is None/empty, all pass. Unknown resolved (None) always passes."""
    if not allowed:
        return True
    if resolved is None:
        return True
    return resolved.upper() in {a.upper() for a in allowed}
