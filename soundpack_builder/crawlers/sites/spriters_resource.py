from __future__ import annotations

import re
import urllib.parse
from html.parser import HTMLParser
from typing import List, Tuple

from soundpack_builder.crawlers.base import SiteCrawler
from soundpack_builder.crawlers.models import CrawlCandidateLink, CrawlQuery, CrawlResult
from soundpack_builder.crawlers.registry import register

SITE_ID = "spriters-resource-sounds"
BASE_URL = "https://sounds.spriters-resource.com"
_ASSET_LINK_RE = re.compile(r"^https?://sounds\.spriters-resource\.com/[^/]+/[^/]+/asset/\d+/?$", re.IGNORECASE)
_ASSET_ID_RE = re.compile(r"/asset/(\d+)/?$", re.IGNORECASE)
_ZIP_RE = re.compile(
    r"https?://sounds\.spriters-resource\.com/media/assets/\d+/\d+\.zip(?:\?[^\"'<>\s]+)?",
    re.IGNORECASE,
)


class _AnchorCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._current_href = ""
        self._text_parts: List[str] = []
        self.items: List[Tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = ""
        for key, value in attrs:
            if key.lower() == "href":
                href = (value or "").strip()
                break
        self._current_href = href
        self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._current_href:
            self._text_parts.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a":
            return
        if self._current_href:
            title = " ".join(part for part in self._text_parts if part)
            self.items.append((self._current_href, title.strip()))
        self._current_href = ""
        self._text_parts = []


def _tokenize(*parts: str) -> List[str]:
    out: List[str] = []
    for p in parts:
        for token in re.split(r"[^a-z0-9]+", p.lower()):
            if token:
                out.append(token)
    return out


@register(SITE_ID)
class SpritersResourceCrawler(SiteCrawler):
    site_id = SITE_ID

    def build_search_url(self, query: CrawlQuery) -> str:
        return f"{BASE_URL}/browse/?name={urllib.parse.quote_plus(query.character)}&sect=1"

    def fetch_results(self, query: CrawlQuery) -> List[CrawlResult]:
        search_url = self.build_search_url(query)
        html = self.http.get_text(search_url)
        parser = _AnchorCollector()
        parser.feed(html)
        results: List[CrawlResult] = []
        seen = set()
        for href, title in parser.items:
            joined = urllib.parse.urljoin(BASE_URL, href)
            norm = joined.split("?", 1)[0].rstrip("/") + "/"
            if not _ASSET_LINK_RE.match(norm):
                continue
            if norm in seen:
                continue
            seen.add(norm)
            score, notes = self._score_result(
                title=title,
                url=norm,
                character=query.character,
                universe=query.universe,
            )
            results.append(
                CrawlResult(
                    site_id=self.site_id,
                    query_url=search_url,
                    result_url=norm,
                    title=title or "asset",
                    score=score,
                    notes=notes,
                )
            )
        results.sort(key=lambda row: (-row.score, row.result_url))
        return results

    def resolve_result(self, result: CrawlResult, query: CrawlQuery) -> CrawlCandidateLink | None:
        html = self.http.get_text(result.result_url)
        zip_matches = _ZIP_RE.findall(html)
        if not zip_matches:
            return None
        best_zip = zip_matches[0]
        return CrawlCandidateLink(
            universe=query.universe,
            character=query.character,
            siteId=self.site_id,
            url=best_zip,
            sourcePage=result.result_url,
            label=self._build_label(result),
            matchQuality=self._match_quality(result.score),
            score=result.score,
            notes=result.notes,
        )

    def _score_result(self, *, title: str, url: str, character: str, universe: str) -> Tuple[float, List[str]]:
        notes: List[str] = []
        score = 0.0
        title_tokens = set(_tokenize(title))
        char_tokens = set(_tokenize(character))
        universe_tokens = set(_tokenize(universe))
        if title_tokens and char_tokens and char_tokens.issubset(title_tokens):
            score += 3.0
            notes.append("exact_character_match")
        else:
            overlap = len(title_tokens.intersection(char_tokens))
            if overlap:
                score += min(2.0, 0.6 * overlap)
                notes.append("partial_character_match")
        universe_overlap = len(title_tokens.intersection(universe_tokens))
        if universe_overlap:
            score += min(1.5, 0.5 * universe_overlap)
            notes.append("universe_overlap")
        if re.search(r"\b(japanese|french|german|spanish|italian|dutch|russian|korean)\b", title.lower()):
            score -= 0.8
            notes.append("language_variant_penalty")
        asset_id = self._asset_id(url)
        if asset_id:
            score += 0.05
        return score, notes

    def _build_label(self, result: CrawlResult) -> str:
        title = " ".join(result.title.split())
        if not title:
            return ""
        if len(title) <= 70:
            return title
        return title[:67].rstrip() + "..."

    def _match_quality(self, score: float) -> str:
        if score >= 3.0:
            return "high"
        if score >= 1.5:
            return "medium"
        return "low"

    def _asset_id(self, url: str) -> str:
        m = _ASSET_ID_RE.search(url)
        return m.group(1) if m else ""
