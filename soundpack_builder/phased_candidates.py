"""Build per-phase candidate manifests from phased-sourcing.json + discovery JSON.

Outputs under `manifests/phased/`:
  - phase-{1,2,3}-candidates.json — downloader-ready {entries: [...]} where possible
  - phase-{1,2,3}-review.json — portals, archives without path, sound pages without fetch
  - phased-downloadable-all.json — merged downloadable entries (deduped)

Phase for a candidate link is the minimum phase id whose sourceSiteIds contains that siteId.

URL behavior is driven by the ``discovery`` object in phased-sourcing.json (sound-page
regexes and HTML embedded-audio regexes), not by hard-coded hosts.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Pattern, Sequence, Set, Tuple

from .config import BuilderConfig, add_output_path_args, build_config_from_args
from .templates import EVENT_FILES
from .tier1_candidates import EVENT_ORDER, build as tier1_build

AUDIO_EXT = frozenset({".wav", ".mp3", ".ogg", ".flac", ".m4a"})

DEFAULT_PHASED_MANIFEST = "phased-sourcing.json"
DEFAULT_DISCOVERY_MANIFEST = "universe-character-hook-candidates.json"

URL_KIND_ARCHIVE_ZIP = "archive_zip"
URL_KIND_SOUND_PAGE = "sound_page"
URL_KIND_DIRECT_MEDIA = "direct_media"
URL_KIND_PORTAL = "portal"


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _norm_url(url: str) -> str:
    return url.split("?", 1)[0].strip()


def _compile_regex_list(patterns: Sequence[Any], *, label: str) -> List[Pattern[str]]:
    out: List[Pattern[str]] = []
    for i, p in enumerate(patterns):
        if not isinstance(p, str) or not p.strip():
            continue
        try:
            out.append(re.compile(p))
        except re.error as e:
            raise ValueError(f"Invalid {label} regex at index {i}: {p!r} ({e})") from e
    return out


def _discovery_rules(phased: Dict[str, Any]) -> Dict[str, List[Pattern[str]]]:
    raw = phased.get("discovery") if isinstance(phased.get("discovery"), dict) else {}
    sound_page = _compile_regex_list(raw.get("soundPageUrlRegexes") or [], label="soundPageUrlRegexes")
    html_audio = _compile_regex_list(
        raw.get("htmlEmbeddedAudioRegexes") or [], label="htmlEmbeddedAudioRegexes"
    )
    return {"soundPage": sound_page, "htmlAudio": html_audio}


def classify_url(url: str, rules: Dict[str, List[Pattern[str]]]) -> str:
    """Return URL_KIND_* using structure and patterns from ``rules`` (from phased config)."""
    n = _norm_url(url)
    low = n.lower()
    path = Path(low)
    if path.suffix == ".zip":
        return URL_KIND_ARCHIVE_ZIP
    if path.suffix in AUDIO_EXT:
        return URL_KIND_DIRECT_MEDIA
    for pat in rules.get("soundPage") or []:
        if pat.search(n):
            return URL_KIND_SOUND_PAGE
    return URL_KIND_PORTAL


def fetch_first_embedded_audio_url(
    page_url: str,
    rules: Dict[str, List[Pattern[str]]],
    *,
    timeout: float = 20.0,
    user_agent: str = "cursor-custom-sounds-phased_candidates/1.0",
) -> Optional[str]:
    """GET ``page_url`` and return first match from configured ``htmlAudio`` regexes."""
    req = urllib.request.Request(
        page_url,
        headers={"User-Agent": user_agent},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except (urllib.error.URLError, OSError):
        return None
    for pat in rules.get("htmlAudio") or []:
        m: Optional[Match[str]] = pat.search(html)
        if m:
            return m.group(0)
    return None


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
    """Primary .zip URL per tier-1 pack (all rows share one archive)."""
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


def _slug_for_phase(phase: int) -> str:
    return {1: "video-games", 2: "cartoons-anime", 3: "movies"}.get(phase, "unknown")


def build_phase_manifests(
    cfg: BuilderConfig,
    *,
    phased_path: Path,
    universe_path: Path,
    out_dir: Path,
    fetch_sound_pages: bool,
    event_counters: Optional[Dict[Tuple[str, str, str], int]] = None,
) -> Dict[str, Any]:
    phased = _load_json(phased_path)
    phases_config = list(phased.get("phases") or [])
    url_rules = _discovery_rules(phased)

    out_dir.mkdir(parents=True, exist_ok=True)
    aliases = _universe_aliases(phased)
    zip_index = _tier1_zip_paths_index()
    tier1_keys = _tier1_entry_keys()
    tier1_zip_url = _tier1_primary_zip_by_character()

    counters: Dict[Tuple[str, str, str], int] = event_counters or {}

    downloadable_by_phase: Dict[int, List[Dict[str, Any]]] = {1: [], 2: [], 3: []}
    review_by_phase: Dict[int, List[Dict[str, Any]]] = {1: [], 2: [], 3: []}

    for row in tier1_build():
        entry = dict(row)
        entry["sourcingPhase"] = 1
        entry["sourcingSlug"] = _slug_for_phase(1)
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
        kind = classify_url(url, url_rules)

        counter_key = (u_raw, c, ev)

        review_base = {
            **item,
            "sourcingPhase": phase,
            "urlKind": kind,
        }

        if kind == URL_KIND_PORTAL:
            idx = counters.get(counter_key, 0)
            review_by_phase[phase].append(
                {
                    **review_base,
                    "proposedTargetFile": _nth_target_for_event(ev, idx),
                    "reason": "portal_or_search_page",
                }
            )
            counters[counter_key] = idx + 1
            continue

        if kind == URL_KIND_ARCHIVE_ZIP:
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
                        "reason": "archive_zip_missing_pathInArchive",
                        "hint": "Add pathInArchive after inspecting the archive listing, or reuse paths from an existing pack manifest.",
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
                        "source_page": _infer_source_page(url),
                        "note": f"Discovery + tier1 archive paths (phase {phase}); label={item.get('label')}",
                        "sourcingPhase": phase,
                        "sourcingSlug": _slug_for_phase(phase),
                    }
                )
            continue

        if kind == URL_KIND_SOUND_PAGE:
            idx = counters.get(counter_key, 0)
            target_file = _nth_target_for_event(ev, idx)
            direct: Optional[str] = None
            if fetch_sound_pages:
                direct = fetch_first_embedded_audio_url(url, url_rules)
            if not direct:
                review_by_phase[phase].append(
                    {
                        **review_base,
                        "proposedTargetFile": target_file,
                        "reason": "sound_page_needs_direct_url",
                        "hint": "Re-run with --fetch-sound-pages or replace the link with a direct media URL.",
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
                    "note": f"Embedded audio resolved from page {url}; label={item.get('label')}",
                    "sourcingPhase": phase,
                    "sourcingSlug": _slug_for_phase(phase),
                }
            )
            counters[counter_key] = idx + 1
            continue

        if kind == URL_KIND_DIRECT_MEDIA:
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
                    "note": f"Direct media; label={item.get('label')}",
                    "sourcingPhase": phase,
                    "sourcingSlug": _slug_for_phase(phase),
                }
            )
            counters[counter_key] = idx + 1

    meta = {
        "schemaVersion": 1,
        "phasedConfig": str(phased_path),
        "universeManifest": str(universe_path) if universe_path.is_file() else None,
        "fetchSoundPages": fetch_sound_pages,
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


def _infer_source_page(url: str) -> str:
    """Derive a listing page URL from a typical archive asset URL without host-specific logic."""
    n = url.rstrip("/")
    if "/asset/" in n:
        return n.rsplit("/", 1)[0] + "/"
    return url


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build phased candidate manifests for sourcing.")
    add_output_path_args(parser)
    parser.add_argument(
        "--phased-manifest",
        type=str,
        default=None,
        help=f"Path to phased config JSON (default: <manifests>/{DEFAULT_PHASED_MANIFEST}).",
    )
    parser.add_argument(
        "--universe-manifest",
        type=str,
        default=None,
        help=f"Path to character discovery JSON (default: <manifests>/{DEFAULT_DISCOVERY_MANIFEST}).",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default=None,
        help="Output directory (default: <manifests>/phased).",
    )
    parser.add_argument(
        "--fetch-sound-pages",
        action="store_true",
        help="HTTP-fetch sound detail pages and extract direct media URLs via patterns in phased config (network).",
    )
    args = parser.parse_args(argv)
    cfg = build_config_from_args(args)
    phased_path = (
        Path(args.phased_manifest).expanduser().resolve()
        if args.phased_manifest
        else (cfg.manifests_dir / DEFAULT_PHASED_MANIFEST)
    )
    universe_path = (
        Path(args.universe_manifest).expanduser().resolve()
        if args.universe_manifest
        else (cfg.manifests_dir / DEFAULT_DISCOVERY_MANIFEST)
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
        fetch_sound_pages=bool(args.fetch_sound_pages),
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
