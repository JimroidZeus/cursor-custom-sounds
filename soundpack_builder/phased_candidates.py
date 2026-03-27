"""Build per-phase candidate manifests from phased-sourcing.json + discovery JSON.

Outputs under `manifests/phased/`:
  - phase-{1,2,3}-candidates.json — downloader-ready {entries: [...]} where possible
  - phase-{1,2,3}-review.json — portals / ZIPs without path / unresolved Freesound
  - phased-downloadable-all.json — merged downloadable entries (deduped)

Phase for a candidate link is the minimum phase id whose sourceSiteIds contains that siteId.

Does not scrape Voicy or movie sites; direct audio URLs and Spriters ZIP + tier1 path
hints are supported. Optional: --resolve-freesound fetches Freesound /s/{id}/ HTML for
cdn.freesound.org preview links (best-effort).
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .config import BuilderConfig, add_output_path_args, build_config_from_args
from .templates import EVENT_FILES
from .tier1_candidates import EVENT_ORDER, build as tier1_build

AUDIO_EXT = frozenset({".wav", ".mp3", ".ogg", ".flac", ".m4a"})


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _norm_url(url: str) -> str:
    return url.split("?", 1)[0].strip()


def _url_kind(url: str) -> str:
    u = _norm_url(url).lower()
    if "spriters-resource.com" in u and u.endswith(".zip"):
        return "spriters_zip"
    if "/s/" in u and "freesound.org" in u:
        return "freesound_page"
    path = Path(u)
    if path.suffix in AUDIO_EXT:
        return "direct_audio"
    return "portal"


def _site_min_phase(phases: List[Dict[str, Any]], site_id: str) -> Optional[int]:
    found: List[int] = []
    for p in phases:
        pid = p.get("id")
        ids = p.get("sourceSiteIds") or []
        if pid is not None and site_id in ids:
            found.append(int(pid))
    return min(found) if found else None


def _tier1_zip_paths_index() -> Dict[Tuple[str, str, str], List[str]]:
    """(universe, character, norm_zip_url) -> ordered pathInArchive list from tier1."""
    out: Dict[Tuple[str, str, str], List[str]] = {}
    for row in tier1_build():
        u = str(row["universe"])
        c = str(row["character"])
        z = _norm_url(str(row["url"]))
        p = str(row.get("pathInArchive") or "")
        if not p or not z.endswith(".zip"):
            continue
        key = (u, c, z)
        out.setdefault(key, []).append(p)
    return out


def _tier1_entry_keys() -> Set[Tuple[str, str, str, str]]:
    keys: Set[Tuple[str, str, str, str]] = set()
    for row in tier1_build():
        z = _norm_url(str(row["url"]))
        p = str(row.get("pathInArchive") or "")
        keys.add((str(row["universe"]), str(row["character"]), z, p))
    return keys


def _tier1_primary_zip_by_character() -> Dict[Tuple[str, str], str]:
    """Canonical Spriters ZIP URL per tier-1 pack (all rows share one ZIP)."""
    out: Dict[Tuple[str, str], str] = {}
    for row in tier1_build():
        z = _norm_url(str(row["url"]))
        if z.endswith(".zip"):
            out[(str(row["universe"]), str(row["character"]))] = z
    return out


def _universe_aliases(phased: Dict[str, Any]) -> Dict[str, str]:
    raw = phased.get("tier1UniverseAliases") or {}
    return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}


def _resolve_universe(u: str, aliases: Dict[str, str]) -> str:
    return aliases.get(u, u)


def try_freesound_preview_url(page_url: str, *, timeout: float = 20.0) -> Optional[str]:
    if _url_kind(page_url) != "freesound_page":
        return None
    req = urllib.request.Request(
        page_url,
        headers={"User-Agent": "cursor-custom-sounds-phased_candidates/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except (urllib.error.URLError, OSError):
        return None
    m = re.search(r'https://cdn\.freesound\.org/previews/[^"\'\s<>]+\.(?:mp3|ogg|wav)', html)
    if m:
        return m.group(0)
    m = re.search(r"https://freesound\.org/data/previews/[^\"'\s<>]+\.(?:mp3|ogg|wav)", html)
    return m.group(0) if m else None


def _nth_target_for_event(event: str, idx: int) -> str:
    files = EVENT_FILES.get(event) or []
    if not files:
        return f"hook_{event}_{idx + 1}.wav"
    return files[idx % len(files)]


def _iter_discovery_links(
    universe_data: Dict[str, Any],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for ch in universe_data.get("characters") or []:
        if not isinstance(ch, dict):
            continue
        universe = str(ch.get("universe", "")).strip()
        character = str(ch.get("character", "")).strip()
        events = ch.get("events") or {}
        if not isinstance(events, dict):
            continue
        for event_name, block in events.items():
            if not isinstance(block, dict):
                continue
            for link in block.get("candidateLinks") or []:
                if not isinstance(link, dict):
                    continue
                site_id = str(link.get("siteId") or "").strip()
                url = str(link.get("url") or "").strip()
                if not url or not site_id:
                    continue
                rows.append(
                    {
                        "universe": universe,
                        "character": character,
                        "hookEvent": str(event_name),
                        "siteId": site_id,
                        "url": url,
                        "label": link.get("label"),
                        "matchQuality": link.get("matchQuality"),
                    }
                )
    return rows


def build_phase_manifests(
    cfg: BuilderConfig,
    *,
    phased_path: Path,
    universe_path: Path,
    out_dir: Path,
    resolve_freesound: bool,
    event_counters: Optional[Dict[Tuple[str, str, str], int]] = None,
) -> Dict[str, Any]:
    phased = _load_json(phased_path)
    phases_config = list(phased.get("phases") or [])

    out_dir.mkdir(parents=True, exist_ok=True)
    aliases = _universe_aliases(phased)
    zip_index = _tier1_zip_paths_index()
    tier1_keys = _tier1_entry_keys()
    tier1_zip_url = _tier1_primary_zip_by_character()

    # Per (universe, character, hookEvent) → next index for target slot
    counters: Dict[Tuple[str, str, str], int] = event_counters or {}

    downloadable_by_phase: Dict[int, List[Dict[str, Any]]] = {1: [], 2: [], 3: []}
    review_by_phase: Dict[int, List[Dict[str, Any]]] = {1: [], 2: [], 3: []}

    # Phase 1: tier1 packs (video-game primary)
    for row in tier1_build():
        entry = dict(row)
        entry["sourcingPhase"] = 1
        entry["sourcingSlug"] = "video-games"
        downloadable_by_phase[1].append(entry)

    universe_rows: List[Dict[str, Any]] = []
    if universe_path.is_file():
        universe_rows = _iter_discovery_links(_load_json(universe_path))

    seen: Set[Tuple[str, str, str, str]] = set()

    for item in universe_rows:
        site_id = item["siteId"]
        phase = _site_min_phase(phases_config, site_id)
        if phase is None:
            continue

        url = item["url"]
        u_raw = item["universe"]
        c = item["character"]
        u_res = _resolve_universe(u_raw, aliases)
        ev = item["hookEvent"]
        kind = _url_kind(url)

        counter_key = (u_raw, c, ev)

        review_base = {
            **item,
            "sourcingPhase": phase,
            "urlKind": kind,
        }

        if kind == "portal":
            idx = counters.get(counter_key, 0)
            review_by_phase[phase].append(
                {**review_base, "proposedTargetFile": _nth_target_for_event(ev, idx), "reason": "portal_or_search_page"}
            )
            counters[counter_key] = idx + 1
            continue

        if kind == "spriters_zip":
            z = _norm_url(url)
            t1_zip = tier1_zip_url.get((u_res, c))
            if t1_zip and z == t1_zip:
                continue
            paths = zip_index.get((u_res, c, z))
            if not paths:
                paths = zip_index.get((u_raw, c, z))
            if not paths:
                idx = counters.get(counter_key, 0)
                review_by_phase[phase].append(
                    {
                        **review_base,
                        "proposedTargetFile": _nth_target_for_event(ev, idx),
                        "reason": "spriters_zip_needs_pathInArchive",
                        "hint": "Add pathInArchive from ZIP listing or copy from tier1_candidates for this pack.",
                    }
                )
                counters[counter_key] = idx + 1
                continue
            for i, p in enumerate(paths):
                key = (u_raw, c, z, p)
                if key in tier1_keys:
                    continue
                if key in seen:
                    continue
                seen.add(key)
                slot_target = EVENT_ORDER[i % len(EVENT_ORDER)]
                downloadable_by_phase[phase].append(
                    {
                        "universe": u_raw,
                        "character": c,
                        "targetFile": slot_target,
                        "event": ev,
                        "url": url,
                        "pathInArchive": p,
                        "source_page": url.rsplit("/", 1)[0] + "/"
                        if "/asset/" in url
                        else url,
                        "note": f"Discovery + tier1 ZIP paths (phase {phase}); label={item.get('label')}",
                        "sourcingPhase": phase,
                        "sourcingSlug": {1: "video-games", 2: "cartoons-anime", 3: "movies"}.get(
                            phase, "unknown"
                        ),
                    }
                )
            continue

        if kind == "freesound_page":
            idx = counters.get(counter_key, 0)
            target_file = _nth_target_for_event(ev, idx)
            direct: Optional[str] = None
            if resolve_freesound:
                direct = try_freesound_preview_url(url)
            if not direct:
                review_by_phase[phase].append(
                    {
                        **review_base,
                        "proposedTargetFile": target_file,
                        "reason": "freesound_needs_direct_url",
                        "hint": "Re-run with --resolve-freesound or set a direct preview/file URL from freesound.org.",
                    }
                )
                counters[counter_key] = idx + 1
                continue
            dkey = (u_raw, c, _norm_url(direct), "")
            if dkey in seen:
                continue
            seen.add(dkey)
            downloadable_by_phase[phase].append(
                {
                    "universe": u_raw,
                    "character": c,
                    "targetFile": target_file,
                    "event": ev,
                    "url": direct,
                    "source_page": url,
                    "note": f"Freesound preview resolved from {url}; label={item.get('label')}",
                    "sourcingPhase": phase,
                    "sourcingSlug": {1: "video-games", 2: "cartoons-anime", 3: "movies"}.get(
                        phase, "unknown"
                    ),
                }
            )
            counters[counter_key] = idx + 1
            continue

        if kind == "direct_audio":
            idx = counters.get(counter_key, 0)
            target_file = _nth_target_for_event(ev, idx)
            dk = (u_raw, c, _norm_url(url), "")
            if dk in seen:
                counters[counter_key] = idx + 1
                continue
            seen.add(dk)
            downloadable_by_phase[phase].append(
                {
                    "universe": u_raw,
                    "character": c,
                    "targetFile": target_file,
                    "event": ev,
                    "url": url,
                    "source_page": url,
                    "note": f"Direct audio; label={item.get('label')}",
                    "sourcingPhase": phase,
                    "sourcingSlug": {1: "video-games", 2: "cartoons-anime", 3: "movies"}.get(
                        phase, "unknown"
                    ),
                }
            )
            counters[counter_key] = idx + 1

    # Write per-phase files
    meta = {
        "schemaVersion": 1,
        "phasedConfig": str(phased_path),
        "universeManifest": str(universe_path) if universe_path.is_file() else None,
        "resolveFreesound": resolve_freesound,
    }

    for pid in (1, 2, 3):
        dl = downloadable_by_phase[pid]
        rv = review_by_phase[pid]
        (out_dir / f"phase-{pid}-candidates.json").write_text(
            json.dumps({"meta": {**meta, "sourcingPhase": pid}, "entries": dl}, indent=2) + "\n",
            encoding="utf-8",
        )
        (out_dir / f"phase-{pid}-review.json").write_text(
            json.dumps({"meta": {**meta, "sourcingPhase": pid}, "items": rv}, indent=2) + "\n",
            encoding="utf-8",
        )

    # Merge downloadable (dedupe by universe/character/targetFile/ url norm)
    all_entries: List[Dict[str, Any]] = []
    merge_seen: Set[Tuple[str, str, str, str, str]] = set()
    for pid in (1, 2, 3):
        for e in downloadable_by_phase[pid]:
            u = str(e.get("universe", ""))
            c = str(e.get("character", ""))
            tf = str(e.get("targetFile", ""))
            ur = _norm_url(str(e.get("url", "")))
            pia = str(e.get("pathInArchive") or "")
            key = (u, c, tf, ur, pia)
            if key in merge_seen:
                continue
            merge_seen.add(key)
            all_entries.append(e)

    (out_dir / "phased-downloadable-all.json").write_text(
        json.dumps({"meta": meta, "entries": all_entries}, indent=2) + "\n",
        encoding="utf-8",
    )

    return {
        "ok": True,
        "outDir": str(out_dir),
        "counts": {
            "downloadable": {str(k): len(v) for k, v in downloadable_by_phase.items()},
            "review": {str(k): len(v) for k, v in review_by_phase.items()},
            "merged": len(all_entries),
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build phased candidate manifests for sourcing.")
    add_output_path_args(parser)
    parser.add_argument(
        "--phased-manifest",
        type=str,
        default=None,
        help="Path to phased-sourcing.json (default: <manifests>/phased-sourcing.json).",
    )
    parser.add_argument(
        "--universe-manifest",
        type=str,
        default=None,
        help="Path to universe-character-hook-candidates.json (default: <manifests>/...).",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default=None,
        help="Output directory (default: <manifests>/phased).",
    )
    parser.add_argument(
        "--resolve-freesound",
        action="store_true",
        help="Fetch Freesound /s/id/ pages to find cdn.freesound.org preview URLs (network).",
    )
    args = parser.parse_args(argv)
    cfg = build_config_from_args(args)
    phased_path = (
        Path(args.phased_manifest).expanduser().resolve()
        if args.phased_manifest
        else (cfg.manifests_dir / "phased-sourcing.json")
    )
    universe_path = (
        Path(args.universe_manifest).expanduser().resolve()
        if args.universe_manifest
        else (cfg.manifests_dir / "universe-character-hook-candidates.json")
    )
    out_dir = (
        Path(args.out_dir).expanduser().resolve()
        if args.out_dir
        else (cfg.manifests_dir / "phased")
    )

    report = build_phase_manifests(
        cfg,
        phased_path=phased_path,
        universe_path=universe_path,
        out_dir=out_dir,
        resolve_freesound=bool(args.resolve_freesound),
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
