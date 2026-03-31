"""
Resolve Freesound URLs from ``candidates/review.json`` via the Freesound API v2.

Reads review items with ``siteId == "freesound"``, maps each ``url`` to a preview
audio URL (HQ MP3 when available), and writes downloader-ready entries.

**Authentication:** set ``FREESOUND_API_KEY`` (see https://freesound.org/help/developers/)
in the environment or ``soundpack_builder/.env``.

**URL shapes supported**

- Sound: ``/s/<id>/``, ``/people/<user>/sounds/<id>/``
- Search: ``/search/?q=...``
- Tag browse: ``/browse/tags/<slug>/``
- Pack: ``/people/<user>/packs/<id>/`` (first sound in pack)

Search/tag/pack modes pick the **first** API result (same heuristic as opening the page
and taking the top hit).

Run::

    python -m soundpack_builder.tools.freesound_resolve
    python -m soundpack_builder.tools.freesound_resolve --review path/to/review.json --out path/out.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from soundpack_builder.core.config import add_output_path_args, build_config_from_args, freesound_api_key

API_BASE = "https://freesound.org/apiv2"
USER_AGENT = "cursor-custom-sounds-freesound-resolve/1.0"

_RE_SOUND_SHORT = re.compile(
    r"https?://(?:www\.)?freesound\.org/s/(\d+)/?",
    re.IGNORECASE,
)
_RE_SOUND_USER = re.compile(
    r"https?://(?:www\.)?freesound\.org/people/[^/]+/sounds/(\d+)/?",
    re.IGNORECASE,
)
_RE_SEARCH = re.compile(r"https?://(?:www\.)?freesound\.org/search/\?", re.IGNORECASE)
_RE_PACK = re.compile(
    r"https?://(?:www\.)?freesound\.org/people/[^/]+/packs/(\d+)/?",
    re.IGNORECASE,
)
_RE_TAG = re.compile(
    r"https?://(?:www\.)?freesound\.org/browse/tags/([^/?#]+)/?",
    re.IGNORECASE,
)

_PREVIEW_KEYS = (
    "preview-hq-mp3",
    "preview-hq-ogg",
    "preview-lq-mp3",
    "preview-lq-ogg",
)


@dataclass(frozen=True)
class ParsedFreesound:
    """kind is one of: sound, search, pack, tag."""

    kind: str
    sound_id: Optional[int] = None
    search_query: Optional[str] = None
    pack_id: Optional[int] = None
    tag_slug: Optional[str] = None


def parse_freesound_url(url: str) -> Optional[ParsedFreesound]:
    """If *url* is a recognized Freesound browse/search/sound URL, return its kind and parameters."""
    m = _RE_SOUND_SHORT.search(url)
    if m:
        return ParsedFreesound(kind="sound", sound_id=int(m.group(1)))
    m = _RE_SOUND_USER.search(url)
    if m:
        return ParsedFreesound(kind="sound", sound_id=int(m.group(1)))
    m = _RE_PACK.search(url)
    if m:
        return ParsedFreesound(kind="pack", pack_id=int(m.group(1)))
    m = _RE_TAG.search(url)
    if m:
        raw = m.group(1).strip()
        tag = urllib.parse.unquote(raw.replace("+", " "))
        return ParsedFreesound(kind="tag", tag_slug=tag)
    if _RE_SEARCH.search(url):
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        q = (qs.get("q") or [""])[0].strip()
        if q:
            return ParsedFreesound(kind="search", search_query=q)
    return None


def pick_preview_url(sound_obj: Dict[str, Any]) -> Optional[str]:
    previews = sound_obj.get("previews") if isinstance(sound_obj.get("previews"), dict) else {}
    for k in _PREVIEW_KEYS:
        u = previews.get(k)
        if isinstance(u, str) and u.startswith("http"):
            return u
    return None


def api_get_json(
    resource: str,
    token: str,
    *,
    query: Optional[Dict[str, str]] = None,
    timeout: float = 30.0,
) -> Any:
    """GET ``resource`` relative to ``/apiv2/`` (e.g. ``sounds/123/`` or ``search/text/``)."""
    r = resource.strip().rstrip("/")
    url = f"{API_BASE}/{r}/"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Token {token}",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"Freesound API HTTP {e.code} for {url}: {detail}") from e
    return json.loads(raw)


def fetch_sound_object(sound_id: int, token: str) -> Dict[str, Any]:
    data = api_get_json(
        f"sounds/{sound_id}",
        token,
        query={"fields": "id,name,previews,url"},
    )
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected sound payload for id={sound_id}")
    return data


def search_first_sound(token: str, *, query: str) -> Optional[Dict[str, Any]]:
    data = api_get_json(
        "search/text",
        token,
        query={
            "query": query,
            "fields": "id,name,previews",
            "page_size": "1",
            "page": "1",
        },
    )
    if not isinstance(data, dict):
        return None
    results = data.get("results")
    if not isinstance(results, list) or not results:
        return None
    first = results[0]
    return first if isinstance(first, dict) else None


def pack_first_sound(pack_id: int, token: str) -> Optional[Dict[str, Any]]:
    data = api_get_json(
        f"packs/{pack_id}/sounds",
        token,
        query={"fields": "id,name,previews", "page_size": "1", "page": "1"},
    )
    if not isinstance(data, dict):
        return None
    results = data.get("results")
    if not isinstance(results, list) or not results:
        return None
    first = results[0]
    return first if isinstance(first, dict) else None


def resolve_parsed_to_sound_dict(parsed: ParsedFreesound, token: str) -> Optional[Dict[str, Any]]:
    if parsed.kind == "sound" and parsed.sound_id is not None:
        return fetch_sound_object(parsed.sound_id, token)
    if parsed.kind == "search" and parsed.search_query:
        return search_first_sound(token, query=parsed.search_query)
    if parsed.kind == "pack" and parsed.pack_id is not None:
        return pack_first_sound(parsed.pack_id, token)
    if parsed.kind == "tag" and parsed.tag_slug:
        slug = parsed.tag_slug
        text_query = slug.replace("-", " ").strip()
        hit = search_first_sound(token, query=text_query)
        if hit:
            return hit
        for filt in (f"tag:{slug}", f"tags:{slug}"):
            try:
                data = api_get_json(
                    "search/text",
                    token,
                    query={
                        "query": "",
                        "filter": filt,
                        "fields": "id,name,previews",
                        "page_size": "1",
                        "page": "1",
                    },
                )
            except RuntimeError:
                continue
            if isinstance(data, dict):
                results = data.get("results")
                if isinstance(results, list) and results and isinstance(results[0], dict):
                    return results[0]
    return None


def review_item_to_entry(
    item: Dict[str, Any],
    *,
    direct_url: str,
    resolved_sound: Dict[str, Any],
) -> Dict[str, Any]:
    """Build one ``candidates.json``-style entry."""
    ev = item.get("hookEvent") or item.get("event")
    target = item.get("proposedTargetFile")
    row: Dict[str, Any] = {
        "universe": item["universe"],
        "character": item["character"],
        "targetFile": target,
        "url": direct_url,
        "source_page": item.get("url"),
        "note": (
            f"Freesound API preview; sound id={resolved_sound.get('id')!r} name={resolved_sound.get('name')!r}; "
            f"label={item.get('label')!r}"
        ),
        "source": "discovery",
    }
    if ev:
        row["event"] = ev
    if item.get("matchQuality") is not None:
        row["matchQuality"] = item.get("matchQuality")
    slug = item.get("packLabelSlug")
    if slug:
        row["packLabelSlug"] = str(slug).strip()
        if item.get("label") is not None:
            row["packLabel"] = item.get("label")
    return row


def resolve_review_items(
    items: List[Dict[str, Any]],
    token: str,
    *,
    delay_sec: float = 0.25,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Resolve Freesound review rows to downloader entries.

    Returns (entries, skipped) where each skipped item has ``url`` and ``reason``.
    """
    entries: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for item in items:
        if item.get("siteId") != "freesound":
            continue
        url = str(item.get("url") or "")
        parsed = parse_freesound_url(url)
        if not parsed:
            skipped.append({"url": url, "reason": "unrecognized_freesound_url"})
            continue
        try:
            sound = resolve_parsed_to_sound_dict(parsed, token)
        except Exception as e:
            skipped.append({"url": url, "reason": f"api_error:{e}"})
            if delay_sec > 0:
                time.sleep(delay_sec)
            continue
        if not sound:
            skipped.append({"url": url, "reason": "no_search_result"})
            if delay_sec > 0:
                time.sleep(delay_sec)
            continue
        direct = pick_preview_url(sound)
        if not direct:
            skipped.append({"url": url, "reason": "no_preview_in_response"})
            if delay_sec > 0:
                time.sleep(delay_sec)
            continue
        entries.append(review_item_to_entry(item, direct_url=direct, resolved_sound=sound))
        if delay_sec > 0:
            time.sleep(delay_sec)

    return entries, skipped


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Resolve Freesound URLs in review.json to preview MP3 URLs via API v2.",
    )
    add_output_path_args(parser)
    parser.add_argument(
        "--review",
        type=str,
        default=None,
        help="Path to review.json (default: <manifests>/candidates/review.json).",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Output JSON path (default: <manifests>/candidates/freesound-resolved.json).",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="Freesound API token (overrides FREESOUND_API_KEY).",
    )
    parser.add_argument(
        "--delay-sec",
        type=float,
        default=0.25,
        help="Delay between API calls (default: 0.25).",
    )
    args = parser.parse_args(argv)
    cfg = build_config_from_args(args)

    token = (args.token or "").strip() or freesound_api_key()
    if not token:
        print(
            "Missing API token: set FREESOUND_API_KEY or pass --token.",
            file=sys.stderr,
        )
        return 1

    review_path = (
        Path(args.review).expanduser().resolve()
        if args.review
        else (cfg.manifests_dir / "candidates" / "review.json")
    )
    out_path = (
        Path(args.out).expanduser().resolve()
        if args.out
        else (cfg.manifests_dir / "candidates" / "freesound-resolved.json")
    )

    if not review_path.is_file():
        print(f"Review file not found: {review_path}", file=sys.stderr)
        return 1

    data = json.loads(review_path.read_text(encoding="utf-8"))
    items = data.get("items")
    if not isinstance(items, list):
        print("Invalid review.json: missing 'items' list.", file=sys.stderr)
        return 1

    entries, skipped = resolve_review_items(items, token, delay_sec=float(args.delay_sec))

    out_obj: Dict[str, Any] = {
        "meta": {
            "schemaVersion": 1,
            "generator": "soundpack_builder.freesound_resolve",
            "sourceReview": str(review_path),
        },
        "entries": entries,
        "skipped": skipped,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_obj, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(out_path),
                "resolved": len(entries),
                "skipped": len(skipped),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
