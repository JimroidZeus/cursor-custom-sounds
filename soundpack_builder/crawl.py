"""Crawler CLI: site-specific discovery into manifest-friendly rows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from soundpack_builder.core.config import add_output_path_args, build_config_from_args
from soundpack_builder.core.manifest_io import read_json
from soundpack_builder.crawlers.models import CrawlQuery
from soundpack_builder.crawlers.registry import list_crawlers
from soundpack_builder.crawlers.runner import (
    apply_links_to_universe_manifest,
    run_crawler,
    write_generated_output,
)

# Register built-in crawlers on import.
from soundpack_builder.crawlers import sites as _sites  # noqa: F401


def _verified_site_ids(path: Path) -> set[str]:
    data = read_json(path) if path.is_file() else {"sites": []}
    out: set[str] = set()
    for row in data.get("sites") or []:
        if isinstance(row, dict) and row.get("id"):
            out.add(str(row["id"]).strip())
    return out


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run a site-specific crawler and output discovery rows.")
    add_output_path_args(parser)
    parser.add_argument("--site-id", required=True, help=f"Site id to crawl (known: {', '.join(list_crawlers())}).")
    parser.add_argument("--universe", required=True, help="Universe slug.")
    parser.add_argument("--character", required=True, help="Character slug.")
    parser.add_argument("--max-results", type=int, default=5, help="Max links to emit (default: 5).")
    parser.add_argument(
        "--sourcing-config",
        type=str,
        default=None,
        help="Path to sourcing-config.json (default: <manifests>/sourcing-config.json).",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Generated output path (default: <manifests>/candidates/<site-id>-crawl.json).",
    )
    parser.add_argument("--json", action="store_true", help="Print run result JSON summary.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Append discovered links into universe-character-hook-candidates.json (dedup by URL).",
    )
    parser.add_argument(
        "--universe-manifest",
        type=str,
        default=None,
        help="Path to universe-character-hook-candidates.json for --apply.",
    )
    args = parser.parse_args(argv)
    cfg = build_config_from_args(args)
    sourcing_path = (
        Path(args.sourcing_config).expanduser().resolve()
        if args.sourcing_config
        else (cfg.manifests_dir / "sourcing-config.json")
    )
    sound_sites_path = cfg.manifests_dir / "sound-sites.json"
    out_path = (
        Path(args.out).expanduser().resolve()
        if args.out
        else (cfg.manifests_dir / "candidates" / f"{args.site_id}-crawl.json")
    )
    universe_manifest_path = (
        Path(args.universe_manifest).expanduser().resolve()
        if args.universe_manifest
        else (cfg.manifests_dir / "universe-character-hook-candidates.json")
    )
    sourcing = read_json(sourcing_path)
    approved_site_ids = _verified_site_ids(sound_sites_path)
    if args.site_id.strip() not in approved_site_ids:
        known = ", ".join(sorted(approved_site_ids)) or "<none>"
        raise ValueError(f"site-id {args.site_id!r} is not in sound-sites.json. Known: {known}")
    result = run_crawler(
        query=CrawlQuery(
            universe=args.universe.strip(),
            character=args.character.strip(),
            site_id=args.site_id.strip(),
            max_results=max(1, int(args.max_results)),
        ),
        sourcing_config=sourcing if isinstance(sourcing, dict) else {},
    )
    write_generated_output(out_path, result)
    apply_stats = {"applied": 0, "skipped": 0}
    if args.apply:
        apply_stats = apply_links_to_universe_manifest(manifest_path=universe_manifest_path, links=result.links)
    summary = {
        "ok": True,
        "siteId": result.site_id,
        "out": str(out_path),
        "links": len(result.links),
        "review": len(result.review),
        "apply": apply_stats,
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"[crawl] site={result.site_id} links={len(result.links)} review={len(result.review)}")
        print(f"[crawl] wrote: {out_path}")
        if args.apply:
            print(f"[crawl] apply: +{apply_stats['applied']} links, skipped={apply_stats['skipped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
