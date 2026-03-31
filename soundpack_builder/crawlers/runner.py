from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from soundpack_builder.core.manifest_io import read_json, write_json
from soundpack_builder.crawlers.http import CrawlerHttpClient, HttpFetchConfig
from soundpack_builder.crawlers.models import CrawlCandidateLink, CrawlQuery, CrawlRunResult
from soundpack_builder.crawlers.registry import get_crawler


def build_http_config(sourcing_config: Dict[str, Any]) -> HttpFetchConfig:
    fetch = sourcing_config.get("fetch") if isinstance(sourcing_config.get("fetch"), dict) else {}
    retries = int(fetch.get("maxRetries", 2))
    delay = float(fetch.get("delayBetweenRequestsSec", 0.25))
    return HttpFetchConfig(max_retries=max(0, retries), delay_between_requests_sec=max(0.0, delay))


def run_crawler(
    *,
    query: CrawlQuery,
    sourcing_config: Dict[str, Any],
) -> CrawlRunResult:
    http = CrawlerHttpClient(build_http_config(sourcing_config))
    crawler = get_crawler(query.site_id, http)
    results = crawler.fetch_results(query)
    links: List[CrawlCandidateLink] = []
    review: List[Dict[str, str]] = []
    shortlist = results[: max(1, query.max_results)]
    for result in shortlist:
        link = crawler.resolve_result(result, query)
        if link is None:
            review.append(
                {
                    "siteId": query.site_id,
                    "universe": query.universe,
                    "character": query.character,
                    "url": result.result_url,
                    "title": result.title,
                    "reason": "zip_not_found_on_asset_page",
                }
            )
            continue
        links.append(link)
    return CrawlRunResult(
        site_id=query.site_id,
        links=links,
        review=review,
        metadata={
            "maxResults": query.max_results,
            "resultCount": len(results),
            "shortlistCount": len(shortlist),
            "linkCount": len(links),
            "reviewCount": len(review),
        },
    )


def write_generated_output(path: Path, result: CrawlRunResult) -> None:
    payload: Dict[str, Any] = {
        "schemaVersion": 1,
        "siteId": result.site_id,
        "metadata": result.metadata,
        "entries": [row.as_generated_row() for row in result.links],
        "review": result.review,
    }
    write_json(path, payload)


def apply_links_to_universe_manifest(
    *,
    manifest_path: Path,
    links: List[CrawlCandidateLink],
) -> Dict[str, int]:
    data = read_json(manifest_path)
    chars = data.get("characters")
    if not isinstance(chars, list):
        raise ValueError("Expected universe manifest to contain a characters[] array.")

    applied = 0
    skipped = 0
    by_key = {(row.universe, row.character): [] for row in links}
    for link in links:
        by_key[(link.universe, link.character)].append(link)

    for ch in chars:
        if not isinstance(ch, dict):
            continue
        key = (str(ch.get("universe", "")).strip(), str(ch.get("character", "")).strip())
        batch = by_key.get(key)
        if not batch:
            continue
        current = ch.get("candidateLinks")
        if not isinstance(current, list):
            current = []
            ch["candidateLinks"] = current
        existing_urls = {str(item.get("url", "")).strip() for item in current if isinstance(item, dict)}
        for item in batch:
            if item.url in existing_urls:
                skipped += 1
                continue
            current.append(item.as_manifest_link())
            existing_urls.add(item.url)
            applied += 1

    write_json(manifest_path, data)
    return {"applied": applied, "skipped": skipped}
