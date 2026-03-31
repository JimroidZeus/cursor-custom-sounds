"""Shared stderr progress lines so stdout can stay JSON-only for tooling."""

from __future__ import annotations

import sys
from typing import TextIO


def render_bar(done: int, total: int, *, width: int = 24) -> str:
    """ASCII progress bar (same style as downloader)."""
    if total <= 0:
        return "-" * width
    done = min(max(done, 0), total)
    n = int((done / total) * width)
    return "#" * n + "-" * (width - n)


def print_progress_line(
    *,
    index: int,
    total: int,
    label: str,
    detail: str = "",
    file: TextIO = sys.stderr,
    width: int = 24,
) -> None:
    """One line: ``[bar] i/total label detail``."""
    bar = render_bar(index, total, width=width)
    extra = f" {detail}" if detail else ""
    print(f"[{bar}] {index}/{total} {label}{extra}", file=file, flush=True)


def print_status(message: str, *, file: TextIO = sys.stderr) -> None:
    print(message, file=file, flush=True)
