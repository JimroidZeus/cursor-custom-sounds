from __future__ import annotations

from typing import Dict, List, Type

from soundpack_builder.crawlers.base import SiteCrawler
from soundpack_builder.crawlers.http import CrawlerHttpClient


_REGISTRY: Dict[str, Type[SiteCrawler]] = {}


def register(site_id: str):
    def _wrap(cls: Type[SiteCrawler]) -> Type[SiteCrawler]:
        _REGISTRY[site_id] = cls
        return cls

    return _wrap


def list_crawlers() -> List[str]:
    return sorted(_REGISTRY.keys())


def get_crawler(site_id: str, http_client: CrawlerHttpClient) -> SiteCrawler:
    cls = _REGISTRY.get(site_id)
    if cls is None:
        known = ", ".join(list_crawlers()) or "<none>"
        raise ValueError(f"Unknown crawler site id: {site_id}. Known: {known}")
    return cls(http_client)
