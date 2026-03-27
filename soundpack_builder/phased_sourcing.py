"""CLI: print phased sourcing plan merged with optional discovery manifest.

Usage (repo root, with uv):
  uv run --project soundpack_builder python -m soundpack_builder.phased_sourcing
  uv run --project soundpack_builder python -m soundpack_builder.phased_sourcing --phase 2
  uv run --project soundpack_builder python -m soundpack_builder.phased_sourcing --json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import BuilderConfig, add_output_path_args, build_config_from_args
from .templates import TIER1_CHARACTERS


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _site_index(
    phased: Dict[str, Any],
    universe_path: Optional[Path],
) -> Dict[str, Dict[str, Any]]:
    sites: Dict[str, Dict[str, Any]] = {}
    for item in phased.get("extraSourceSites") or []:
        if isinstance(item, dict) and item.get("id"):
            sites[str(item["id"])] = dict(item)
    if universe_path and universe_path.is_file():
        data = _load_json(universe_path)
        for item in data.get("sourceSites") or []:
            if isinstance(item, dict) and item.get("id"):
                sid = str(item["id"])
                if sid not in sites:
                    sites[sid] = dict(item)
    return sites


def _resolve_phase(phased: Dict[str, Any], sites: Dict[str, Dict[str, Any]], phase: Dict[str, Any]) -> Dict[str, Any]:
    ids: List[str] = []
    for raw in phase.get("sourceSiteIds") or []:
        ids.append(str(raw))
    resolved = []
    for sid in ids:
        meta = sites.get(sid)
        if meta:
            resolved.append(
                {
                    "id": sid,
                    "name": meta.get("name", sid),
                    "url": meta.get("url", ""),
                    "kind": meta.get("kind", ""),
                    "notes": meta.get("notes", ""),
                }
            )
        else:
            resolved.append({"id": sid, "name": sid, "url": "", "kind": "", "notes": "(unknown id — add to universe manifest or extraSourceSites)"})
    out = {**phase, "resolvedSourceSites": resolved}
    return out


def build_report(cfg: BuilderConfig, *, phased_path: Optional[Path] = None) -> Dict[str, Any]:
    path = phased_path or (cfg.manifests_dir / "phased-sourcing.json")
    phased = _load_json(path)
    universe_path = cfg.manifests_dir / "universe-character-hook-candidates.json"
    sites = _site_index(phased, universe_path)
    phases_out = []
    for phase in phased.get("phases") or []:
        if not isinstance(phase, dict):
            continue
        phases_out.append(_resolve_phase(phased, sites, phase))
    tier1_primary = int((phased.get("tier1") or {}).get("primaryPhase", 1))
    tier1_rows = []
    for row in TIER1_CHARACTERS:
        tier1_rows.append(
            {
                "universe": row["universe"],
                "character": row["character"],
                "primaryPhase": tier1_primary,
            }
        )
    return {
        "schemaVersion": phased.get("schemaVersion"),
        "humanDoc": phased.get("humanDoc"),
        "tier1": phased.get("tier1"),
        "tier1Characters": tier1_rows,
        "phases": phases_out,
    }


def _print_text(report: Dict[str, Any], *, phase_filter: Optional[int]) -> None:
    print("Phased sourcing (approved resources only)")
    doc = report.get("humanDoc")
    if doc:
        print(f"Doc: {doc}")
    print()
    t1 = report.get("tier1") or {}
    print(f"Tier-1 default phase: {t1.get('primaryPhase', 1)} - {t1.get('note', '')}")
    print("Tier-1 packs:")
    for row in report.get("tier1Characters") or []:
        print(f"  - {row['universe']}/{row['character']} (phase {row['primaryPhase']})")
    print()
    for phase in report.get("phases") or []:
        pid = phase.get("id")
        if phase_filter is not None and pid != phase_filter:
            continue
        print(f"{phase.get('title', pid)}")
        print(f"  Goal: {phase.get('goal', '')}")
        for p in phase.get("portals") or []:
            print(f"  Portal: {p.get('label')} - {p.get('url')}")
        print("  Source sites (resolved):")
        for s in phase.get("resolvedSourceSites") or []:
            url = s.get("url") or ""
            suffix = f" - {url}" if url else ""
            print(f"    - {s.get('name', s.get('id'))}{suffix}")
        print()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Print phased sourcing plan for hook sound discovery.")
    add_output_path_args(parser)
    parser.add_argument(
        "--phased-manifest",
        type=str,
        default=None,
        help="Path to phased-sourcing.json (default: <manifests>/phased-sourcing.json).",
    )
    parser.add_argument(
        "--phase",
        type=int,
        choices=(1, 2, 3),
        default=None,
        help="Show only this phase (1–3). Default: all phases.",
    )
    parser.add_argument("--json", action="store_true", help="Print full report as JSON.")
    args = parser.parse_args(argv)
    cfg = build_config_from_args(args)
    phased_path = Path(args.phased_manifest).expanduser().resolve() if args.phased_manifest else None
    report = build_report(cfg, phased_path=phased_path)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_text(report, phase_filter=args.phase)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
