from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from soundpack_builder.crawlers.http import CrawlerHttpClient
from soundpack_builder.crawlers.models import CrawlCandidateLink, CrawlQuery, CrawlResult


class SiteCrawler(ABC):
    site_id: str

    def __init__(self, http_client: CrawlerHttpClient) -> None:
        self.http = http_client

    @abstractmethod
    def build_search_url(self, query: CrawlQuery) -> str:
        raise NotImplementedError

    @abstractmethod
    def fetch_results(self, query: CrawlQuery) -> List[CrawlResult]:
        raise NotImplementedError

    @abstractmethod
    def resolve_result(self, result: CrawlResult, query: CrawlQuery) -> CrawlCandidateLink | None:
        raise NotImplementedError

    def crawl(self, query: CrawlQuery) -> List[CrawlCandidateLink]:
        links: List[CrawlCandidateLink] = []
        for result in self.fetch_results(query):
            link = self.resolve_result(result, query)
            if link is not None:
                links.append(link)
            if len(links) >= query.max_results:
                break
        return links
