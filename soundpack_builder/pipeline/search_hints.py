"""Pipeline step 1: DuckDuckGo search URLs for each hook-pack character × verified site.

Open the URLs in a browser, add ``candidateLinks`` to
``universe-character-hook-candidates.json``, then run ``candidates`` (step 2).
This module does not perform HTTP requests itself."""

from __future__ import annotations

import argparse
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional

from soundpack_builder.core.config import BuilderConfig, add_output_path_args, build_config_from_args
from soundpack_builder.core.manifest_io import read_json
from soundpack_builder.pipeline.templates import HOOK_PACK_CHARACTERS

DEFAULT_SOUND_SITES = "sound-sites.json"


def _hints(cfg: BuilderConfig, approved_path: Path) -> List[Dict[str, str]]:
    data = read_json(approved_path) if approved_path.is_file() else {"sites": []}
    sites = [s for s in data.get("sites") or [] if isinstance(s, dict) and s.get("id")]
    rows: List[Dict[str, str]] = []
    for ch in HOOK_PACK_CHARACTERS:
        u, c = ch["universe"], ch["character"]
        label = f"{u.replace('-', ' ')} {c.replace('-', ' ')} voice sound clip"
        for site in sites:
            netloc = ""
            url = str(site.get("url") or "")
            if "://" in url:
                try:
                    rest = url.split("://", 1)[1]
                    netloc = rest.split("/")[0]
                except IndexError:
                    netloc = ""
            q = f"site:{netloc} {label}" if netloc else label
            ddg = "https://duckduckgo.com/?q=" + urllib.parse.quote_plus(q)
            rows.append(
                {
                    "universe": u,
                    "character": c,
                    "siteId": str(site["id"]),
                    "siteName": str(site.get("name", site["id"])),
                    "searchUrl": ddg,
                }
            )
    return rows


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print DuckDuckGo search URLs for hook-pack characters × verified sites (no network).",
    )
    add_output_path_args(parser)
    parser.add_argument(
        "--sound-sites",
        type=str,
        default=None,
        help=f"Path to sound-sites.json (default: <manifests>/{DEFAULT_SOUND_SITES}).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON array instead of text lines.",
    )
    args = parser.parse_args(argv)
    cfg = build_config_from_args(args)
    path = (
        Path(args.sound_sites).expanduser().resolve()
        if args.sound_sites
        else (cfg.manifests_dir / DEFAULT_SOUND_SITES)
    )
    rows = _hints(cfg, path)
    if args.json:
        import json as _json

        print(_json.dumps(rows, indent=2))
    else:
        for r in rows:
            print(f"# {r['universe']}/{r['character']} @ {r['siteId']}")
            print(r["searchUrl"])
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
