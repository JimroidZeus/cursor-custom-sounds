"""Pipeline step 2: build downloader candidate manifests from game-archive rows + discovery links.

Reads:
  - manifests/sourcing-config.json — global URL classification (discovery.*Regexes) as fallback when a site
    omits patterns; optional universeAliases; optional fetch (retries, delay for --fetch-sound-pages)
  - manifests/sound-sites.json — verified site ids (must match candidateLinks.siteId); optional per-site
    discovery.soundPageUrlRegexes / htmlEmbeddedAudioRegexes override sourcing-config per field
  - manifests/universe-character-hook-candidates.json — ``characters[].candidateLinks`` and
    ``crossFranchiseOneVoicePacks[]`` (same fields), plus optional legacy ``events.*.candidateLinks``;
    optional matchQuality on links is forwarded to discovery rows. Distinct non-empty ``label``
    values on links for the same character become separate packs (``packLabelSlug`` on downloader
    rows; separate ``discovery_NNN`` counters per label). Link objects must use ``siteId``
    (``siteID`` is accepted as an alias). Optional ``languageCode`` on a link is normalized;
    paths and URLs may infer language (e.g. ``_jp.wav``). Default ``--language-codes ENG`` filters discovery
    rows; rows with no resolvable language pass through.
    Discovery outputs use neutral ``discovery_NNN.wav`` names — hook assignment happens after download
    (e.g. transcript mapping), not from the universe manifest.

Writes under manifests/candidates/ (default):
  - candidates.json — downloader-ready entries
  - review.json — portals, missing ZIP paths, sound pages needing URLs
  - downloadable-all.json — deduplicated merge (same entries shape as candidates)

With --fetch-sound-pages, sound pages are fetched and parsed for embedded audio URLs
(HTML src/href resolution plus regex fallback).

For sounds.spriters-resource.com ZIPs not covered by the game-archive index, use
``--inventory-spriters-zips`` (default: on): HTTP-fetch each ZIP once, list audio
members, and emit one downloader row per file with ``pathInArchive`` set (full
soundpack expansion). Disable with ``--no-inventory-spriters-zips`` if you need
offline or faster runs without listing multi-file archives.

If sound-sites.json is missing or uses an older embedded ``phases`` layout, site ids
are merged from that structure or from ``sourcing_config`` (see ``_verified_site_ids``).
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
import zipfile
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Pattern, Sequence, Set, Tuple

from soundpack_builder.core.config import BuilderConfig, add_output_path_args, build_config_from_args
from soundpack_builder.core.console_progress import print_progress_line, print_status
from soundpack_builder.core.hook_events import discovery_target_filename
from soundpack_builder.core.language_codes import (
    DEFAULT_LANGUAGE_FILTER,
    normalize_language_code,
    parse_language_filter_arg,
    passes_language_filter,
    resolve_language_code,
)
from soundpack_builder.core.manifest_io import read_json
from soundpack_builder.core.media_urls import normalize_absolute_media_url
from soundpack_builder.core.pack_label import pack_label_key_and_slug
from soundpack_builder.crawlers.models import CrawlQuery
from soundpack_builder.crawlers.runner import run_crawler, write_generated_output
from soundpack_builder.crawlers.registry import list_crawlers
from soundpack_builder.tools.archive_entries import build as archive_build

# Register built-in crawler implementations.
from soundpack_builder.crawlers import sites as _crawler_sites  # noqa: F401

AUDIO_EXT = frozenset({".wav", ".mp3", ".ogg", ".flac", ".m4a"})

DEFAULT_SOURCING_CONFIG = "sourcing-config.json"
DEFAULT_SOUND_SITES = "sound-sites.json"
DEFAULT_DISCOVERY_MANIFEST = "universe-character-hook-candidates.json"

URL_KIND_ARCHIVE_ZIP = "archive_zip"
URL_KIND_SOUND_PAGE = "sound_page"
URL_KIND_DIRECT_MEDIA = "direct_media"
URL_KIND_PORTAL = "portal"


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


def _discovery_rules(sourcing: Dict[str, Any]) -> Dict[str, List[Pattern[str]]]:
    raw = sourcing.get("discovery") if isinstance(sourcing.get("discovery"), dict) else {}
    sound_page = _compile_regex_list(raw.get("soundPageUrlRegexes") or [], label="soundPageUrlRegexes")
    html_audio = _compile_regex_list(
        raw.get("htmlEmbeddedAudioRegexes") or [], label="htmlEmbeddedAudioRegexes"
    )
    return {"soundPage": sound_page, "htmlAudio": html_audio}


def _site_discovery_maps(sound_sites_path: Path) -> Dict[str, Dict[str, List[Pattern[str]]]]:
    """Per-site compiled discovery regexes from sound-sites.json (may be empty per key)."""
    out: Dict[str, Dict[str, List[Pattern[str]]]] = {}
    if not sound_sites_path.is_file():
        return out
    data = read_json(sound_sites_path)
    for s in data.get("sites") or []:
        if not isinstance(s, dict) or not s.get("id"):
            continue
        sid = str(s["id"]).strip()
        disc = s.get("discovery") if isinstance(s.get("discovery"), dict) else {}
        out[sid] = {
            "soundPage": _compile_regex_list(
                disc.get("soundPageUrlRegexes") or [],
                label=f"site:{sid}.soundPageUrlRegexes",
            ),
            "htmlAudio": _compile_regex_list(
                disc.get("htmlEmbeddedAudioRegexes") or [],
                label=f"site:{sid}.htmlEmbeddedAudioRegexes",
            ),
        }
    return out


def _effective_discovery_rules(
    site_id: str,
    global_rules: Dict[str, List[Pattern[str]]],
    site_maps: Dict[str, Dict[str, List[Pattern[str]]]],
) -> Dict[str, List[Pattern[str]]]:
    """Site-specific regex lists override sourcing-config per field; empty uses global fallback."""
    block = site_maps.get(site_id.strip()) or {"soundPage": [], "htmlAudio": []}
    sp = block.get("soundPage") or []
    ha = block.get("htmlAudio") or []
    return {
        "soundPage": sp if sp else (global_rules.get("soundPage") or []),
        "htmlAudio": ha if ha else (global_rules.get("htmlAudio") or []),
    }


class _HrefSrcCollector(HTMLParser):
    """Collect src/href/data-src for audio URL resolution."""

    def __init__(self) -> None:
        super().__init__()
        self.raw: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        ad = {k.lower(): (v or "").strip() for k, v in attrs}
        for key in ("src", "href", "data-src"):
            val = ad.get(key, "")
            if val:
                self.raw.append(val)


_AUDIO_EXT_LOWER = (".wav", ".mp3", ".ogg", ".flac", ".m4a")
_AUDIO_ABS_RE = re.compile(
    r"https?://[^\s\"'<>]+\.(?:wav|mp3|ogg|flac|m4a)(?:\?[^\s\"'<>]*)?",
    re.IGNORECASE,
)


def extract_audio_urls_from_html(html: str, page_url: str) -> List[str]:
    """Parse HTML for audio links and absolute media URLs; resolve relative paths."""
    collector = _HrefSrcCollector()
    try:
        collector.feed(html)
        collector.close()
    except Exception:
        pass
    out: List[str] = []
    seen: Set[str] = set()
    for raw in collector.raw:
        u = raw.strip()
        if not u or u.lower().startswith(("javascript:", "data:", "#")):
            continue
        if u.lower().startswith(("http://", "https://")):
            joined = normalize_absolute_media_url(u)
        else:
            joined = normalize_absolute_media_url(urllib.parse.urljoin(page_url, u))
        low = joined.split("?", 1)[0].lower()
        if any(low.endswith(ext) for ext in _AUDIO_EXT_LOWER):
            key = joined.split("?", 1)[0]
            if key not in seen:
                seen.add(key)
                out.append(joined)
    for m in _AUDIO_ABS_RE.finditer(html):
        raw_hit = m.group(0)
        if raw_hit.lower().startswith(("http://", "https://")):
            joined = normalize_absolute_media_url(raw_hit)
        else:
            joined = normalize_absolute_media_url(urllib.parse.urljoin(page_url, raw_hit))
        key = joined.split("?", 1)[0]
        if key not in seen:
            seen.add(key)
            out.append(joined)
    return out


def _regex_first_audio_match(html: str, rules: Dict[str, List[Pattern[str]]]) -> Optional[str]:
    """Fallback: first regex match; prefer capturing groups over full match."""
    for pat in rules.get("htmlAudio") or []:
        m = pat.search(html)
        if not m:
            continue
        if m.lastindex:
            for gi in range(1, m.lastindex + 1):
                cand = m.group(gi)
                if cand and cand.strip():
                    return cand.strip()
        return m.group(0).strip()
    return None


def http_get_bytes(
    url: str,
    *,
    timeout: float = 20.0,
    user_agent: str = "cursor-custom-sounds-candidates/1.0",
    max_retries: int = 2,
    retry_delay_sec: float = 0.5,
) -> Optional[bytes]:
    last: Optional[BaseException] = None
    for attempt in range(max_retries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": user_agent})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, OSError) as e:
            last = e
            if attempt < max_retries:
                time.sleep(retry_delay_sec * (2**attempt))
    return None


SPRITERS_RESOURCE_SITE_ID = "spriters-resource-sounds"


def _is_spriters_zip_candidate(site_id: str, url: str) -> bool:
    """True when the link is a Spriters Resource sound-pack ZIP (inventory expansion applies)."""
    sid = site_id.strip().lower()
    if sid == SPRITERS_RESOURCE_SITE_ID:
        return True
    low = url.lower()
    return "sounds.spriters-resource.com" in low and ".zip" in low


def list_zip_audio_members(zip_bytes: bytes) -> List[str]:
    """Return sorted audio member paths inside a ZIP (``.wav``, ``.mp3``, etc.)."""
    if not zip_bytes:
        return []
    out: List[str] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        for m in zf.namelist():
            if m.endswith("/"):
                continue
            if Path(m).suffix.lower() in AUDIO_EXT:
                out.append(m)
    return sorted(out, key=lambda x: x.replace("\\", "/").lower())


def fetch_first_embedded_audio_url(
    page_url: str,
    rules: Dict[str, List[Pattern[str]]],
    *,
    timeout: float = 20.0,
    user_agent: str = "cursor-custom-sounds-candidates/1.0",
    max_retries: int = 2,
    fetch_delay_sec: float = 0.0,
) -> Optional[str]:
    if fetch_delay_sec > 0:
        time.sleep(fetch_delay_sec)
    raw = http_get_bytes(
        page_url,
        timeout=timeout,
        user_agent=user_agent,
        max_retries=max_retries,
    )
    if raw is None:
        return None
    html = raw.decode("utf-8", errors="ignore")
    candidates = extract_audio_urls_from_html(html, page_url)
    if candidates:
        return candidates[0]
    fallback = _regex_first_audio_match(html, rules)
    if not fallback:
        return None
    if fallback.strip().lower().startswith(("http://", "https://")):
        return normalize_absolute_media_url(fallback)
    return normalize_absolute_media_url(urllib.parse.urljoin(page_url, fallback))


def classify_url(url: str, rules: Dict[str, List[Pattern[str]]]) -> str:
    """Return URL_KIND_* using structure and patterns from ``rules``."""
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


def _site_ids_from_phases_layout(sourcing: Dict[str, Any]) -> Set[str]:
    """Merge ids from JSON that embeds ``phases`` / ``extraSourceSites`` (older layout)."""
    ids: Set[str] = set()
    for ph in sourcing.get("phases") or []:
        if not isinstance(ph, dict):
            continue
        for x in ph.get("sourceSiteIds") or []:
            ids.add(str(x).strip())
    for ex in sourcing.get("extraSourceSites") or []:
        if isinstance(ex, dict) and ex.get("id"):
            ids.add(str(ex["id"]).strip())
    return ids


def _verified_site_ids(sound_sites_path: Path, sourcing_config: Dict[str, Any]) -> Set[str]:
    """Load ids from sound-sites.json, or older JSON with embedded ``phases`` in the same file."""
    if sound_sites_path.is_file():
        data = read_json(sound_sites_path)
        sites = data.get("sites")
        if isinstance(sites, list) and sites:
            return {
                str(s["id"]).strip()
                for s in sites
                if isinstance(s, dict) and s.get("id")
            }
        if data.get("phases"):
            return _site_ids_from_phases_layout(data)
    extra = sourcing_config.get("approvedSourceSiteIds")
    if isinstance(extra, list) and extra:
        return {str(x).strip() for x in extra}
    return _site_ids_from_phases_layout(sourcing_config)


def _site_allowed(site_id: str, approved: Set[str]) -> bool:
    return site_id.strip() in approved


def _game_archive_zip_paths_index() -> Dict[Tuple[str, str, str], List[str]]:
    out: Dict[Tuple[str, str, str], List[str]] = {}
    for row in archive_build():
        u = str(row["universe"])
        c = str(row["character"])
        z = _norm_url(str(row["url"]))
        p = str(row.get("pathInArchive") or "")
        if not p or not z.endswith(".zip"):
            continue
        key = (u, c, z)
        out.setdefault(key, []).append(p)
    return out


def _game_archive_entry_keys() -> Set[Tuple[str, str, str, str]]:
    keys: Set[Tuple[str, str, str, str]] = set()
    for row in archive_build():
        z = _norm_url(str(row["url"]))
        p = str(row.get("pathInArchive") or "")
        keys.add((str(row["universe"]), str(row["character"]), z, p))
    return keys


def _game_archive_primary_zip_by_character() -> Dict[Tuple[str, str], str]:
    out: Dict[Tuple[str, str], str] = {}
    for row in archive_build():
        z = _norm_url(str(row["url"]))
        if z.endswith(".zip"):
            out[(str(row["universe"]), str(row["character"]))] = z
    return out


def _universe_aliases(sourcing: Dict[str, Any]) -> Dict[str, str]:
    raw = sourcing.get("universeAliases") or sourcing.get("tier1UniverseAliases") or {}
    return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}


def _resolve_universe(u: str, aliases: Dict[str, str]) -> str:
    return aliases.get(u, u)


def _pack_manifest_fields(item: Dict[str, Any]) -> Dict[str, Any]:
    """Optional packLabelSlug / packLabel for downloader output rows."""
    slug = item.get("packLabelSlug")
    if not slug:
        return {}
    out: Dict[str, Any] = {"packLabelSlug": str(slug).strip()}
    if item.get("label") is not None:
        out["packLabel"] = item.get("label")
    return out


def _append_discovery_link_rows(
    rows: List[Dict[str, Any]],
    *,
    universe: str,
    character: str,
    links: Any,
) -> None:
    if not isinstance(links, list):
        return
    for link in links:
        if not isinstance(link, dict):
            continue
        site_id = str(link.get("siteId") or link.get("siteID") or "").strip()
        url = str(link.get("url") or "").strip()
        if not url or not site_id:
            continue
        _, slug = pack_label_key_and_slug(link.get("label"))
        row: Dict[str, Any] = {
            "universe": universe,
            "character": character,
            "siteId": site_id,
            "url": url,
            "label": link.get("label"),
            "matchQuality": link.get("matchQuality"),
        }
        if slug:
            row["packLabelSlug"] = slug
        lc = normalize_language_code(link.get("languageCode"))
        if lc:
            row["languageCode"] = lc
        rows.append(row)


def _iter_discovery_links_for_character_like(
    rows: List[Dict[str, Any]], ch: Dict[str, Any]
) -> None:
    universe = str(ch.get("universe", "")).strip()
    character = str(ch.get("character", "")).strip()
    _append_discovery_link_rows(rows, universe=universe, character=character, links=ch.get("candidateLinks"))
    events = ch.get("events") or {}
    if isinstance(events, dict):
        for _event_name in sorted(events.keys()):
            block = events[_event_name]
            if not isinstance(block, dict):
                continue
            _append_discovery_link_rows(
                rows, universe=universe, character=character, links=block.get("candidateLinks")
            )


def _iter_discovery_links(universe_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten character-level and legacy per-event candidate links (no hook preclassification).

    Also walks ``crossFranchiseOneVoicePacks`` (same shape as ``characters[]``) so bundle rows
    are not dropped.
    """
    rows: List[Dict[str, Any]] = []
    for ch in universe_data.get("characters") or []:
        if not isinstance(ch, dict):
            continue
        _iter_discovery_links_for_character_like(rows, ch)
    for ch in universe_data.get("crossFranchiseOneVoicePacks") or []:
        if not isinstance(ch, dict):
            continue
        _iter_discovery_links_for_character_like(rows, ch)
    return rows


def _crawler_queries_from_universe(
    universe_data: Dict[str, Any],
    *,
    supported_site_ids: Set[str],
    max_results: int,
) -> List[CrawlQuery]:
    """Build crawler query list from discoveryHints.suggestedSourceSiteIds."""
    out: List[CrawlQuery] = []
    seen: Set[Tuple[str, str, str]] = set()

    def _has_direct_download_link(ch: Dict[str, Any]) -> bool:
        links = ch.get("candidateLinks")
        if not isinstance(links, list):
            return False
        for link in links:
            if not isinstance(link, dict):
                continue
            url = str(link.get("url", "")).strip()
            if not url:
                continue
            kind = classify_url(url, {"soundPage": [], "htmlAudio": []})
            if kind in (URL_KIND_ARCHIVE_ZIP, URL_KIND_DIRECT_MEDIA):
                return True
        return False

    def _append_from_rows(rows: Any) -> None:
        if not isinstance(rows, list):
            return
        for ch in rows:
            if not isinstance(ch, dict):
                continue
            universe = str(ch.get("universe", "")).strip()
            character = str(ch.get("character", "")).strip()
            if not universe or not character:
                continue
            if _has_direct_download_link(ch):
                continue
            hints = ch.get("discoveryHints") if isinstance(ch.get("discoveryHints"), dict) else {}
            site_ids = hints.get("suggestedSourceSiteIds")
            if not isinstance(site_ids, list):
                continue
            for site_id in site_ids:
                sid = str(site_id or "").strip()
                if not sid or sid not in supported_site_ids:
                    continue
                key = (universe, character, sid)
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    CrawlQuery(
                        universe=universe,
                        character=character,
                        site_id=sid,
                        max_results=max(1, int(max_results)),
                    )
                )

    _append_from_rows(universe_data.get("characters"))
    _append_from_rows(universe_data.get("crossFranchiseOneVoicePacks"))
    return out


def _rows_from_crawler_result_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return rows
    for row in entries:
        if not isinstance(row, dict):
            continue
        universe = str(row.get("universe", "")).strip()
        character = str(row.get("character", "")).strip()
        site_id = str(row.get("siteId", "")).strip()
        url = str(row.get("url", "")).strip()
        if not universe or not character or not site_id or not url:
            continue
        entry: Dict[str, Any] = {
            "universe": universe,
            "character": character,
            "siteId": site_id,
            "url": url,
        }
        if row.get("label"):
            entry["label"] = row.get("label")
        if row.get("matchQuality"):
            entry["matchQuality"] = row.get("matchQuality")
        rows.append(entry)
    return rows


def _load_crawler_output_rows(out_dir: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for p in sorted(out_dir.glob("*-crawl.json")):
        try:
            payload = read_json(p)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.extend(_rows_from_crawler_result_payload(payload))
    return rows


def _infer_source_page(url: str) -> str:
    n = url.rstrip("/")
    if "/asset/" in n:
        return n.rsplit("/", 1)[0] + "/"
    return url


def _fetch_options(sourcing: Dict[str, Any]) -> Tuple[int, float]:
    raw = sourcing.get("fetch")
    if not isinstance(raw, dict):
        return 2, 0.0
    try:
        retries = int(raw.get("maxRetries", 2))
    except (TypeError, ValueError):
        retries = 2
    try:
        delay = float(raw.get("delayBetweenRequestsSec", 0.0))
    except (TypeError, ValueError):
        delay = 0.0
    return max(0, retries), max(0.0, delay)




def _attach_language_metadata(
    row: Dict[str, Any],
    item: Dict[str, Any],
    *,
    url: str,
    path_in_archive: Optional[str] = None,
) -> None:
    """Set languageCode when explicit or inferred from path/URL (discovery rows)."""
    explicit = normalize_language_code(item.get("languageCode"))
    resolved = resolve_language_code(explicit, path_in_archive or "", url, str(item.get("label") or ""))
    if resolved:
        row["languageCode"] = resolved


def build_candidate_manifests(
    cfg: BuilderConfig,
    *,
    sourcing_config_path: Path,
    sound_sites_path: Path,
    universe_path: Path,
    out_dir: Path,
    fetch_sound_pages: bool,
    progress: bool = True,
    discovery_counters: Optional[Dict[Tuple[str, str, str], int]] = None,
    inventory_spriters_zips: bool = True,
    language_filter_codes: Optional[Set[str]] = None,
    consume_crawler_outputs: bool = False,
    auto_run_crawlers: bool = False,
    auto_crawl_max_results: int = 5,
    auto_crawl_write_outputs: bool = False,
) -> Dict[str, Any]:
    sourcing = read_json(sourcing_config_path)
    url_rules = _discovery_rules(sourcing)
    max_retries, fetch_delay_sec = _fetch_options(sourcing)
    approved_ids = _verified_site_ids(sound_sites_path, sourcing)
    site_discovery_maps = _site_discovery_maps(sound_sites_path)

    if language_filter_codes is None:
        lang_allowed: Optional[Set[str]] = set(DEFAULT_LANGUAGE_FILTER)
    elif len(language_filter_codes) == 0:
        lang_allowed = None
    else:
        lang_allowed = {x.upper() for x in language_filter_codes}

    def _discovery_passes(item: Dict[str, Any], url: str, path_in_archive: Optional[str]) -> bool:
        explicit = str(item.get("languageCode") or "").strip() or None
        resolved = resolve_language_code(
            explicit,
            path_in_archive or "",
            url,
            str(item.get("label") or ""),
        )
        return passes_language_filter(resolved, lang_allowed)

    out_dir.mkdir(parents=True, exist_ok=True)
    aliases = _universe_aliases(sourcing)
    zip_index = _game_archive_zip_paths_index()
    archive_keys = _game_archive_entry_keys()
    archive_zip_url = _game_archive_primary_zip_by_character()

    counters: Dict[Tuple[str, str, str], int] = discovery_counters or {}

    downloadable: List[Dict[str, Any]] = []
    review: List[Dict[str, Any]] = []

    if progress:
        print_status("Staging game-archive pack rows...", file=sys.stderr)

    for row in archive_build():
        entry = dict(row)
        entry["source"] = "archive"
        downloadable.append(entry)

    if progress:
        print_status(
            f"Game-archive downloadable rows: {len(downloadable)}.",
            file=sys.stderr,
        )

    universe_rows: List[Dict[str, Any]] = []
    crawler_generated_rows: List[Dict[str, Any]] = []
    crawler_query_count = 0
    crawler_link_count = 0
    crawler_review_count = 0
    if universe_path.is_file():
        universe_data = read_json(universe_path)
        universe_rows = _iter_discovery_links(universe_data)
        supported_crawler_site_ids = set(list_crawlers())
        if auto_run_crawlers:
            queries = _crawler_queries_from_universe(
                universe_data if isinstance(universe_data, dict) else {},
                supported_site_ids=supported_crawler_site_ids,
                max_results=auto_crawl_max_results,
            )
            crawler_query_count = len(queries)
            for query in queries:
                try:
                    crawl_result = run_crawler(query=query, sourcing_config=sourcing)
                except Exception:
                    continue
                crawler_link_count += len(crawl_result.links)
                crawler_review_count += len(crawl_result.review)
                crawler_payload = {
                    "schemaVersion": 1,
                    "siteId": crawl_result.site_id,
                    "metadata": crawl_result.metadata,
                    "entries": [row.as_generated_row() for row in crawl_result.links],
                    "review": crawl_result.review,
                }
                crawler_generated_rows.extend(_rows_from_crawler_result_payload(crawler_payload))
                if auto_crawl_write_outputs:
                    crawl_path = out_dir / f"{query.site_id}-crawl.json"
                    write_generated_output(crawl_path, crawl_result)

        if consume_crawler_outputs:
            crawler_generated_rows.extend(_load_crawler_output_rows(out_dir))
        if crawler_generated_rows:
            universe_rows.extend(crawler_generated_rows)

    if progress:
        if universe_rows:
            print_status(
                f"Processing {len(universe_rows)} discovery link(s) (approved site ids: {len(approved_ids)})...",
                file=sys.stderr,
            )
        else:
            print_status(
                "No discovery links (missing or empty manifest); game-archive rows only.",
                file=sys.stderr,
            )

    seen: Set[Tuple[str, str, str, str, str]] = set()

    for i, item in enumerate(universe_rows, start=1):
        site_id = item["siteId"]
        if not _site_allowed(site_id, approved_ids):
            continue

        url = item["url"]
        u_raw = item["universe"]
        c = item["character"]
        label_slug = str(item.get("packLabelSlug") or "").strip()
        u_res = _resolve_universe(u_raw, aliases)
        site_rules = _effective_discovery_rules(site_id, url_rules, site_discovery_maps)
        if not _discovery_passes(item, url, None):
            continue
        kind = classify_url(url, site_rules)

        if progress:
            detail = kind
            if kind == URL_KIND_SOUND_PAGE and fetch_sound_pages:
                detail = f"{kind} (HTTP)"
            print_progress_line(
                index=i,
                total=len(universe_rows),
                label="discovery",
                detail=(detail[:44] + "...") if len(detail) > 45 else detail,
                file=sys.stderr,
            )

        counter_key = (u_raw, c, label_slug)

        review_base = {
            **item,
            "urlKind": kind,
            "source": "discovery",
        }

        if kind == URL_KIND_PORTAL:
            idx = counters.get(counter_key, 0)
            review.append(
                {
                    **review_base,
                    "proposedTargetFile": discovery_target_filename(idx),
                    "reason": "portal_or_search_page",
                }
            )
            counters[counter_key] = idx + 1
            continue

        if kind == URL_KIND_ARCHIVE_ZIP:
            z = _norm_url(url)
            primary_zip = archive_zip_url.get((u_res, c))
            if primary_zip and z == primary_zip and not label_slug:
                continue
            paths = zip_index.get((u_res, c, z))
            if not paths:
                paths = zip_index.get((u_raw, c, z))
            if not paths:
                zkey = (u_raw, c, label_slug, z, "")
                if zkey in seen:
                    continue
                if inventory_spriters_zips and _is_spriters_zip_candidate(site_id, url):
                    if fetch_delay_sec > 0:
                        time.sleep(fetch_delay_sec)
                    raw_zip = http_get_bytes(
                        url,
                        max_retries=max_retries,
                        retry_delay_sec=max(fetch_delay_sec, 0.25) if fetch_delay_sec > 0 else 0.5,
                    )
                    members: List[str] = []
                    if raw_zip:
                        try:
                            members = list_zip_audio_members(raw_zip)
                        except (zipfile.BadZipFile, OSError):
                            members = []
                    if members:
                        seen.add(zkey)
                        label_note = item.get("label")
                        for p in members:
                            idx = counters.get(counter_key, 0)
                            slot_target = discovery_target_filename(idx)
                            row_spr: Dict[str, Any] = {
                                "universe": u_raw,
                                "character": c,
                                "targetFile": slot_target,
                                "url": url,
                                "pathInArchive": p,
                                "source_page": _infer_source_page(url),
                                "note": (
                                    f"Spriters soundpack ZIP ({len(members)} audio file(s) inventoried); "
                                    f"label={label_note}"
                                ),
                                "source": "discovery",
                                **_pack_manifest_fields(item),
                            }
                            if item.get("matchQuality") is not None:
                                row_spr["matchQuality"] = item.get("matchQuality")
                            _attach_language_metadata(row_spr, item, url=url, path_in_archive=p)
                            if not _discovery_passes(item, url, p):
                                continue
                            downloadable.append(row_spr)
                            counters[counter_key] = idx + 1
                        continue
                    idx_fail = counters.get(counter_key, 0)
                    review.append(
                        {
                            **review_base,
                            "proposedTargetFile": discovery_target_filename(idx_fail),
                            "reason": "spriters_zip_inventory_failed",
                            "hint": (
                                "Could not fetch the ZIP, parse it, or it contains no audio files. "
                                "Verify the URL and network, or add explicit pathInArchive rows by hand."
                            ),
                        }
                    )
                    counters[counter_key] = idx_fail + 1
                    continue
                # ZIP not in game-archive index (non-Spriters): single row; downloader may still
                # disambiguate when exactly one audio file exists inside the archive.
                seen.add(zkey)
                idx = counters.get(counter_key, 0)
                slot_target = discovery_target_filename(idx)
                row_unknown_zip: Dict[str, Any] = {
                    "universe": u_raw,
                    "character": c,
                    "targetFile": slot_target,
                    "url": url,
                    "source_page": _infer_source_page(url),
                    "note": (
                        f"Discovery ZIP not in archive_entries index; no pathInArchive — "
                        f"downloader uses single audio in zip if unique; label={item.get('label')}"
                    ),
                    "source": "discovery",
                    **_pack_manifest_fields(item),
                }
                if item.get("matchQuality") is not None:
                    row_unknown_zip["matchQuality"] = item.get("matchQuality")
                _attach_language_metadata(row_unknown_zip, item, url=url, path_in_archive=None)
                if not _discovery_passes(item, url, None):
                    counters[counter_key] = idx + 1
                    continue
                downloadable.append(row_unknown_zip)
                counters[counter_key] = idx + 1
                continue
            for p in paths:
                key = (u_raw, c, label_slug, z, p)
                if key in archive_keys:
                    continue
                if key in seen:
                    continue
                seen.add(key)
                idx = counters.get(counter_key, 0)
                slot_target = discovery_target_filename(idx)
                row_zip: Dict[str, Any] = {
                    "universe": u_raw,
                    "character": c,
                    "targetFile": slot_target,
                    "url": url,
                    "pathInArchive": p,
                    "source_page": _infer_source_page(url),
                    "note": f"Discovery + game-archive paths; label={item.get('label')}",
                    "source": "discovery",
                    **_pack_manifest_fields(item),
                }
                if item.get("matchQuality") is not None:
                    row_zip["matchQuality"] = item.get("matchQuality")
                _attach_language_metadata(row_zip, item, url=url, path_in_archive=p)
                if not _discovery_passes(item, url, p):
                    continue
                downloadable.append(row_zip)
                counters[counter_key] = idx + 1
            continue

        if kind == URL_KIND_SOUND_PAGE:
            idx = counters.get(counter_key, 0)
            target_file = discovery_target_filename(idx)
            direct: Optional[str] = None
            if fetch_sound_pages:
                direct = fetch_first_embedded_audio_url(
                    url,
                    site_rules,
                    max_retries=max_retries,
                    fetch_delay_sec=fetch_delay_sec,
                )
            if not direct:
                review.append(
                    {
                        **review_base,
                        "proposedTargetFile": target_file,
                        "reason": "sound_page_needs_direct_url",
                        "hint": "Re-run with --fetch-sound-pages or replace the link with a direct media URL.",
                    }
                )
                counters[counter_key] = idx + 1
                continue
            dkey = (u_raw, c, label_slug, _norm_url(direct), "")
            if dkey in seen:
                continue
            seen.add(dkey)
            row_page: Dict[str, Any] = {
                "universe": u_raw,
                "character": c,
                "targetFile": target_file,
                "url": direct,
                "source_page": url,
                "note": f"Embedded audio resolved from page {url}; label={item.get('label')}",
                "source": "discovery",
                **_pack_manifest_fields(item),
            }
            if item.get("matchQuality") is not None:
                row_page["matchQuality"] = item.get("matchQuality")
            _attach_language_metadata(row_page, item, url=direct, path_in_archive=None)
            if not _discovery_passes(item, direct, None):
                counters[counter_key] = idx + 1
                continue
            downloadable.append(row_page)
            counters[counter_key] = idx + 1
            continue

        if kind == URL_KIND_DIRECT_MEDIA:
            idx = counters.get(counter_key, 0)
            target_file = discovery_target_filename(idx)
            dk = (u_raw, c, label_slug, _norm_url(url), "")
            if dk in seen:
                continue
            seen.add(dk)
            row_direct: Dict[str, Any] = {
                "universe": u_raw,
                "character": c,
                "targetFile": target_file,
                "url": url,
                "source_page": url,
                "note": f"Direct media; label={item.get('label')}",
                "source": "discovery",
                **_pack_manifest_fields(item),
            }
            if item.get("matchQuality") is not None:
                row_direct["matchQuality"] = item.get("matchQuality")
            _attach_language_metadata(row_direct, item, url=url, path_in_archive=None)
            if not _discovery_passes(item, url, None):
                counters[counter_key] = idx + 1
                continue
            downloadable.append(row_direct)
            counters[counter_key] = idx + 1

    meta = {
        "schemaVersion": 1,
        "sourcingConfig": str(sourcing_config_path),
        "soundSitesManifest": str(sound_sites_path)
        if sound_sites_path.is_file()
        else None,
        "universeManifest": str(universe_path) if universe_path.is_file() else None,
        "fetchSoundPages": fetch_sound_pages,
        "inventorySpritersZips": inventory_spriters_zips,
        "fetch": {"maxRetries": max_retries, "delayBetweenRequestsSec": fetch_delay_sec},
        "languageFilter": sorted(lang_allowed) if lang_allowed else None,
    }

    if progress:
        print(file=sys.stderr)
        print_status("Writing candidates.json, review.json, downloadable-all.json...", file=sys.stderr)

    (out_dir / "candidates.json").write_text(
        json.dumps({"meta": meta, "entries": downloadable}, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "review.json").write_text(
        json.dumps({"meta": meta, "items": review}, indent=2) + "\n",
        encoding="utf-8",
    )

    all_entries: List[Dict[str, Any]] = []
    merge_seen: Set[Tuple[str, str, str, str, str, str]] = set()
    for e in downloadable:
        u = str(e.get("universe", ""))
        c = str(e.get("character", ""))
        tf = str(e.get("targetFile", ""))
        ur = _norm_url(str(e.get("url", "")))
        pia = str(e.get("pathInArchive") or "")
        pls = str(e.get("packLabelSlug") or "")
        key = (u, c, tf, ur, pia, pls)
        if key in merge_seen:
            continue
        merge_seen.add(key)
        all_entries.append(e)

    (out_dir / "downloadable-all.json").write_text(
        json.dumps({"meta": meta, "entries": all_entries}, indent=2) + "\n",
        encoding="utf-8",
    )

    if progress:
        print_status("Done.", file=sys.stderr)

    return {
        "ok": True,
        "outDir": str(out_dir),
        "crawler": {
            "queries": crawler_query_count,
            "links": crawler_link_count,
            "review": crawler_review_count,
            "generatedRowsMerged": len(crawler_generated_rows),
        },
        "counts": {
            "downloadable": len(downloadable),
            "review": len(review),
            "merged": len(all_entries),
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build candidate downloader manifests from game-archive rows + discovery links (verified sites).",
    )
    add_output_path_args(parser)
    parser.add_argument(
        "--sourcing-config",
        type=str,
        default=None,
        help=f"Path to sourcing config JSON (default: <manifests>/{DEFAULT_SOURCING_CONFIG}).",
    )
    parser.add_argument(
        "--sound-sites",
        type=str,
        default=None,
        help=f"Verified site list JSON (default: <manifests>/{DEFAULT_SOUND_SITES}).",
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
        help="Output directory (default: <manifests>/candidates).",
    )
    parser.add_argument(
        "--fetch-sound-pages",
        action="store_true",
        help="HTTP-fetch sound detail pages and extract direct media URLs via patterns in sourcing config (network).",
    )
    parser.add_argument(
        "--no-inventory-spriters-zips",
        action="store_true",
        help=(
            "Skip HTTP-fetching Spriters Resource ZIPs to list audio members (no pathInArchive expansion). "
            "Default is to inventory multi-file soundpack ZIPs."
        ),
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable stderr progress (JSON summary still on stdout).",
    )
    parser.add_argument(
        "--consume-crawler-outputs",
        action="store_true",
        help=(
            "Merge discovery rows from manifests/candidates/*-crawl.json into this run "
            "(in addition to universe manifest candidateLinks)."
        ),
    )
    parser.add_argument(
        "--auto-run-crawlers",
        action="store_true",
        help=(
            "Run supported site crawlers automatically using discoveryHints.suggestedSourceSiteIds "
            "from universe manifest, then merge discovered rows into this run."
        ),
    )
    parser.add_argument(
        "--auto-crawl-max-results",
        type=int,
        default=5,
        help="Max links per auto-crawler query (default: 5).",
    )
    parser.add_argument(
        "--auto-crawl-write-outputs",
        action="store_true",
        help="When --auto-run-crawlers is used, also write <site-id>-crawl.json files under out-dir.",
    )
    parser.add_argument(
        "--language-codes",
        type=str,
        default="ENG",
        help=(
            "Comma-separated language codes to keep for discovery rows (explicit or inferred). "
            "Entries with no resolvable code pass through. Default: ENG. Use --no-language-filter to disable."
        ),
    )
    parser.add_argument(
        "--no-language-filter",
        action="store_true",
        help="Do not filter discovery rows by language (include all resolved languages).",
    )
    args = parser.parse_args(argv)
    cfg = build_config_from_args(args)
    sourcing_path = (
        Path(args.sourcing_config).expanduser().resolve()
        if args.sourcing_config
        else (cfg.manifests_dir / DEFAULT_SOURCING_CONFIG)
    )
    sound_sites_path = (
        Path(args.sound_sites).expanduser().resolve()
        if args.sound_sites
        else (cfg.manifests_dir / DEFAULT_SOUND_SITES)
    )
    universe_path = (
        Path(args.universe_manifest).expanduser().resolve()
        if args.universe_manifest
        else (cfg.manifests_dir / DEFAULT_DISCOVERY_MANIFEST)
    )
    out_dir = (
        Path(args.out_dir).expanduser().resolve()
        if args.out_dir
        else (cfg.manifests_dir / "candidates")
    )

    lang_codes = parse_language_filter_arg(
        args.language_codes,
        no_filter=bool(args.no_language_filter),
    )

    report = build_candidate_manifests(
        cfg,
        sourcing_config_path=sourcing_path,
        sound_sites_path=sound_sites_path,
        universe_path=universe_path,
        out_dir=out_dir,
        fetch_sound_pages=bool(args.fetch_sound_pages),
        progress=not args.no_progress,
        inventory_spriters_zips=not bool(args.no_inventory_spriters_zips),
        language_filter_codes=lang_codes,
        consume_crawler_outputs=bool(args.consume_crawler_outputs),
        auto_run_crawlers=bool(args.auto_run_crawlers),
        auto_crawl_max_results=max(1, int(args.auto_crawl_max_results)),
        auto_crawl_write_outputs=bool(args.auto_crawl_write_outputs),
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
