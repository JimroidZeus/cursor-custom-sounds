"""Shared helpers for resolving and validating sound download URLs."""

from __future__ import annotations

from pathlib import Path


def normalize_absolute_media_url(url: str) -> str:
    """
    Fix malformed URLs produced when a page base is concatenated with an absolute CDN URL
    (e.g. ``https://freesound.orghttps://cdn.freesound.org/...`` or
    ``https://freesound.org/https://cdn...`` from ``urllib.parse.urljoin`` with a bad path).
    When multiple ``http(s)://`` segments appear, keep the last absolute URL (usually the asset).
    """
    u = url.strip()
    if not u:
        return u
    lower = u.lower()
    # Prefer last https:// or http:// occurrence when the string accidentally contains two origins.
    for scheme in ("https://", "http://"):
        if lower.count(scheme) > 1:
            idx = u.rfind(scheme)
            if idx >= 0:
                u = u[idx:]
                lower = u.lower()
    return u.split("?", 1)[0] if "?" in u else u


def looks_like_html_file(path: Path, *, max_read: int = 2048) -> bool:
    """True if the file starts like HTML (e.g. login page saved instead of audio)."""
    try:
        head = path.read_bytes()[:max_read]
    except OSError:
        return False
    if not head:
        return True
    stripped = head.lstrip()
    low = stripped.lower()
    # HTML5 uses <!doctype html> (lowercase); older pages used <!DOCTYPE ...>.
    if low.startswith(b"<!doctype") or low.startswith(b"<html"):
        return True
    if stripped.startswith(b"<?xml"):
        # Some error pages; audio never starts with <
        if b"<html" in stripped[:200].lower():
            return True
    return False
