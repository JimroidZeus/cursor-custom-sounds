from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from soundpack_builder.crawlers.http import CrawlerHttpClient
from soundpack_builder.crawlers.models import CrawlCandidateLink, CrawlQuery, CrawlResult
from soundpack_builder.crawlers.runner import apply_links_to_universe_manifest, run_crawler
from soundpack_builder.crawlers.sites.spriters_resource import SpritersResourceCrawler


class _FakeHttp:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages

    def get_text(self, url: str) -> str:
        if url not in self.pages:
            raise RuntimeError(f"Missing fixture for URL: {url}")
        return self.pages[url]


class SpritersCrawlerTests(unittest.TestCase):
    def test_build_search_url(self) -> None:
        crawler = SpritersResourceCrawler(CrawlerHttpClient())
        query = CrawlQuery(universe="dc", character="batman", site_id="spriters-resource-sounds")
        self.assertEqual(
            crawler.build_search_url(query),
            "https://sounds.spriters-resource.com/browse/?name=batman&sect=1",
        )

    def test_parse_search_and_resolve_zip(self) -> None:
        fixtures = Path(__file__).resolve().parent / "fixtures" / "crawlers"
        search_html = (fixtures / "spriters-search.html").read_text(encoding="utf-8")
        asset_html = (fixtures / "spriters-asset.html").read_text(encoding="utf-8")
        pages = {
            "https://sounds.spriters-resource.com/browse/?name=batman&sect=1": search_html,
            "https://sounds.spriters-resource.com/wii_u/legodimensions/asset/403988/": asset_html,
            "https://sounds.spriters-resource.com/wii_u/legodimensions/asset/403989/": asset_html,
            "https://sounds.spriters-resource.com/wii_u/othergame/asset/400001/": asset_html,
        }
        crawler = SpritersResourceCrawler(_FakeHttp(pages))  # type: ignore[arg-type]
        query = CrawlQuery(universe="dc", character="batman", site_id="spriters-resource-sounds", max_results=2)

        results = crawler.fetch_results(query)
        self.assertEqual(len(results), 3)
        self.assertGreaterEqual(results[0].score, results[1].score)
        self.assertEqual(
            results[0].result_url,
            "https://sounds.spriters-resource.com/wii_u/legodimensions/asset/403988/",
        )

        link = crawler.resolve_result(results[0], query)
        self.assertIsNotNone(link)
        assert link is not None
        self.assertEqual(link.siteId, "spriters-resource-sounds")
        self.assertEqual(link.url, "https://sounds.spriters-resource.com/media/assets/401/403988.zip")
        self.assertEqual(link.sourcePage, results[0].result_url)

    def test_run_crawler_shortlist_and_review(self) -> None:
        class _NoZipCrawler(SpritersResourceCrawler):
            def fetch_results(self, query: CrawlQuery) -> list[CrawlResult]:
                return [
                    CrawlResult(
                        site_id=query.site_id,
                        query_url="q",
                        result_url=f"https://sounds.spriters-resource.com/wii_u/a/asset/{i}/",
                        title=f"title {i}",
                        score=float(10 - i),
                    )
                    for i in range(6)
                ]

            def resolve_result(self, result: CrawlResult, query: CrawlQuery) -> CrawlCandidateLink | None:
                return None

        from soundpack_builder.crawlers.registry import _REGISTRY

        old = _REGISTRY.get("spriters-resource-sounds")
        _REGISTRY["spriters-resource-sounds"] = _NoZipCrawler
        try:
            report = run_crawler(
                query=CrawlQuery(
                    universe="dc",
                    character="batman",
                    site_id="spriters-resource-sounds",
                    max_results=3,
                ),
                sourcing_config={"fetch": {"maxRetries": 0, "delayBetweenRequestsSec": 0.0}},
            )
        finally:
            if old is None:
                _REGISTRY.pop("spriters-resource-sounds", None)
            else:
                _REGISTRY["spriters-resource-sounds"] = old
        self.assertEqual(report.metadata["shortlistCount"], 3)
        self.assertEqual(len(report.links), 0)
        self.assertEqual(len(report.review), 3)


class ApplyManifestLinksTests(unittest.TestCase):
    def test_apply_links_dedupes_urls(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manifest_path = Path(td) / "universe.json"
            manifest_path.write_text(
                """
{
  "characters": [
    {
      "universe": "dc",
      "character": "batman",
      "candidateLinks": [
        {"url": "https://x/a.zip", "siteId": "spriters-resource-sounds"}
      ]
    }
  ]
}
""".strip(),
                encoding="utf-8",
            )
            stats = apply_links_to_universe_manifest(
                manifest_path=manifest_path,
                links=[
                    CrawlCandidateLink(
                        universe="dc",
                        character="batman",
                        siteId="spriters-resource-sounds",
                        url="https://x/a.zip",
                    ),
                    CrawlCandidateLink(
                        universe="dc",
                        character="batman",
                        siteId="spriters-resource-sounds",
                        url="https://x/b.zip",
                        label="Batman",
                    ),
                ],
            )
            self.assertEqual(stats, {"applied": 1, "skipped": 1})
            payload = manifest_path.read_text(encoding="utf-8")
            self.assertIn("https://x/a.zip", payload)
            self.assertIn("https://x/b.zip", payload)

