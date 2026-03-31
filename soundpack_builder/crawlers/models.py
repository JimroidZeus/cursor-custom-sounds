from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class CrawlQuery:
    universe: str
    character: str
    site_id: str
    max_results: int = 5


@dataclass(frozen=True)
class CrawlResult:
    site_id: str
    query_url: str
    result_url: str
    title: str
    score: float
    notes: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class CrawlCandidateLink:
    universe: str
    character: str
    siteId: str
    url: str
    label: str = ""
    matchQuality: str = ""
    sourcePage: str = ""
    score: float = 0.0
    notes: List[str] = field(default_factory=list)

    def as_manifest_link(self) -> Dict[str, str]:
        out: Dict[str, str] = {
            "url": self.url,
            "siteId": self.siteId,
        }
        if self.label:
            out["label"] = self.label
        if self.matchQuality:
            out["matchQuality"] = self.matchQuality
        return out

    def as_generated_row(self) -> Dict[str, object]:
        out: Dict[str, object] = {
            "universe": self.universe,
            "character": self.character,
            "siteId": self.siteId,
            "url": self.url,
            "score": round(float(self.score), 4),
        }
        if self.label:
            out["label"] = self.label
        if self.matchQuality:
            out["matchQuality"] = self.matchQuality
        if self.sourcePage:
            out["sourcePage"] = self.sourcePage
        if self.notes:
            out["notes"] = list(self.notes)
        return out


@dataclass(frozen=True)
class CrawlRunResult:
    site_id: str
    links: List[CrawlCandidateLink]
    review: List[Dict[str, str]]
    metadata: Dict[str, object]
