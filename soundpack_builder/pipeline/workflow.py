"""Canonical pipeline order and optional sourcing overview for the soundpack builder.

Primary flow (automated CLIs in order)::

    search_hints → candidates → downloader → templates → validate

Human edits sit *between* search_hints and candidates (curate ``sound-sites.json``,
add ``candidateLinks`` to ``universe-character-hook-candidates.json``), and
*between* candidates and downloader (review ``candidates/review.json``, merge into
``download-manifest.json`` or point ``--manifest`` at ``downloadable-all.json``).

Run ``python -m soundpack_builder.pipeline.workflow`` for the pipeline summary, or
``python -m soundpack_builder.pipeline.workflow --sourcing-report`` to list verified sites
and hook-pack characters.
"""

from __future__ import annotations

import argparse
import json
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from soundpack_builder.core.config import BuilderConfig, add_output_path_args, build_config_from_args
from soundpack_builder.pipeline.templates import HOOK_PACK_CHARACTERS

# (module name, one-line description)
PIPELINE_STEPS: Tuple[Tuple[str, str], ...] = (
    (
        "search_hints",
        "Print DuckDuckGo search URLs (hook-pack x verified sites); no network in the tool.",
    ),
    (
        "candidates",
        "Classify discovery links + game-archive rows -> manifests/candidates/*.json.",
    ),
    (
        "downloader",
        "Download/convert into sounds/<universe>/<character>/ (default manifest: download-manifest.json).",
    ),
    (
        "templates",
        "Generate per-pack sound-config stubs from the downloader manifest.",
    ),
    (
        "validate",
        "Check template shape and WAV duration limits under sounds/.",
    ),
)

HUMAN_STEPS: Tuple[str, ...] = (
    "Before candidates: maintain manifests/sound-sites.json and add per-character candidateLinks in "
    "manifests/universe-character-hook-candidates.json (optionally after search_hints). "
    "Run normalize_manifests if you still have legacy events.*.candidateLinks blocks.",
    "After candidates: review manifests/candidates/review.json; optionally run freesound_resolve "
    "(FREESOUND_API_KEY) for Freesound rows, then curate manifests/download-manifest.json "
    "or pass --manifest manifests/candidates/downloadable-all.json to the downloader.",
)

DEFAULT_SOUND_SITES = "sound-sites.json"

# (module name, description) — not part of the main linear pipeline
OPTIONAL_TOOLS: Tuple[Tuple[str, str], ...] = (
    ("crawl", "Optional site-specific crawler (e.g., Spriters) to seed candidateLinks."),
    ("archive_entries", "Regenerate manifests/generated/archive-entries.json (reference ZIP paths)."),
    ("normalize_manifests", "Rewrite download-manifest + universe JSON (flatten discovery to schema v3)."),
    ("inject_hook_candidate_links", "Bulk-edit universe JSON candidate links (advanced)."),
    (
        "freesound_resolve",
        "Freesound review URLs -> preview MP3 URLs in manifests/candidates/freesound-resolved.json (FREESOUND_API_KEY).",
    ),
    (
        "repair_wavs",
        "Re-encode sounds/**/*.wav that are not PCM RIFF (e.g. MP3 mislabeled .wav); requires ffmpeg.",
    ),
)


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_sourcing_report(
    cfg: BuilderConfig,
    *,
    sound_sites_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Load ``sound-sites.json`` and return verified sites plus hook-pack character list."""
    path = sound_sites_path or (cfg.manifests_dir / DEFAULT_SOUND_SITES)
    data = _load_json(path) if path.is_file() else {"schemaVersion": 1, "sites": [], "description": ""}
    sites: List[Dict[str, Any]] = []
    for item in data.get("sites") or []:
        if isinstance(item, dict) and item.get("id"):
            sites.append(
                {
                    "id": str(item["id"]),
                    "name": item.get("name", item["id"]),
                    "url": item.get("url", ""),
                    "notes": item.get("notes", ""),
                }
            )
    hook_rows = [{"universe": r["universe"], "character": r["character"]} for r in HOOK_PACK_CHARACTERS]
    return {
        "schemaVersion": data.get("schemaVersion", 1),
        "humanDoc": data.get("description") or "docs/sound-sourcing.md",
        "soundSites": sites,
        "hookPackCharacters": hook_rows,
    }


def _print_sourcing_report_text(report: Dict[str, Any]) -> None:
    print("Sound sourcing overview (verified sites + hook-pack roster)")
    print(
        "Build candidate manifests: uv run --project soundpack_builder python -m "
        "soundpack_builder.pipeline.candidates"
    )
    print(
        "Search hints (browser): uv run --project soundpack_builder python -m "
        "soundpack_builder.pipeline.search_hints"
    )
    doc = report.get("humanDoc")
    if doc:
        print(f"Notes: {doc}")
    print()
    print("Verified sample sites:")
    for s in report.get("soundSites") or []:
        url = s.get("url") or ""
        suffix = f" - {url}" if url else ""
        print(f"  - {s.get('name', s.get('id'))} ({s.get('id')}){suffix}")
    print()
    print("Hook-pack characters (from templates):")
    for row in report.get("hookPackCharacters") or []:
        print(f"  - {row['universe']}/{row['character']}")
    print()


def describe_pipeline() -> str:
    """Return a plain-text description of the pipeline (for README embedding or --help)."""
    lines: List[str] = [
        "Primary pipeline (run in order):",
        "",
    ]
    for i, (mod, desc) in enumerate(PIPELINE_STEPS, start=1):
        lines.append(f"  {i}. {mod}")
        lines.append(textwrap.fill(desc, width=76, initial_indent="     ", subsequent_indent="     "))
        lines.append("")
    lines.append("Human steps:")
    for block in HUMAN_STEPS:
        lines.append(textwrap.fill(block, width=76, initial_indent="  * ", subsequent_indent="    "))
    lines.extend(["", "Optional utilities:", ""])
    for mod, desc in OPTIONAL_TOOLS:
        lines.append(f"  * {mod} - {desc}")
    lines.extend(
        [
            "",
            "This module also supports:",
            "  * python -m soundpack_builder.pipeline.workflow --sourcing-report",
            "  * python -m soundpack_builder.pipeline.workflow --sourcing-report --json",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Soundpack builder: print the canonical pipeline, optional sourcing overview "
            "(--sourcing-report), or JSON metadata (--json)."
        ),
    )
    add_output_path_args(parser)
    parser.add_argument(
        "--sourcing-report",
        action="store_true",
        help=f"Print verified sites + hook-pack roster from sound-sites.json (default: <manifests>/{DEFAULT_SOUND_SITES}).",
    )
    parser.add_argument(
        "--sound-sites",
        type=str,
        default=None,
        help=f"With --sourcing-report: path to sound-sites.json (default: <manifests>/{DEFAULT_SOUND_SITES}).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON: pipeline metadata (default mode), or sourcing report (with --sourcing-report).",
    )
    args = parser.parse_args(argv)

    if args.sourcing_report:
        cfg = build_config_from_args(args)
        sites_path = (
            Path(args.sound_sites).expanduser().resolve()
            if args.sound_sites
            else None
        )
        report = build_sourcing_report(cfg, sound_sites_path=sites_path)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            _print_sourcing_report_text(report)
        return 0

    if args.json:
        print(
            json.dumps(
                {
                    "pipeline": [m for m, _ in PIPELINE_STEPS],
                    "humanSteps": list(HUMAN_STEPS),
                    "optional": [m for m, _ in OPTIONAL_TOOLS],
                },
                indent=2,
            )
        )
    else:
        print(describe_pipeline())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
