from __future__ import annotations

import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class HttpFetchConfig:
    max_retries: int = 2
    delay_between_requests_sec: float = 0.25
    timeout_sec: float = 20.0
    user_agent: str = "cursor-custom-sounds-crawler/1.0"


class CrawlerHttpClient:
    def __init__(self, config: Optional[HttpFetchConfig] = None) -> None:
        self.config = config or HttpFetchConfig()

    def get_text(self, url: str) -> str:
        raw = self.get_bytes(url)
        return raw.decode("utf-8", errors="replace")

    def get_bytes(self, url: str) -> bytes:
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            req = urllib.request.Request(url, headers={"User-Agent": self.config.user_agent})
            try:
                with urllib.request.urlopen(req, timeout=self.config.timeout_sec) as resp:
                    if attempt == 0 and self.config.delay_between_requests_sec > 0:
                        time.sleep(self.config.delay_between_requests_sec)
                    return resp.read()
            except (urllib.error.URLError, OSError) as exc:
                last_error = exc
                if attempt < self.config.max_retries:
                    backoff = self.config.delay_between_requests_sec * (2**attempt)
                    if backoff > 0:
                        time.sleep(backoff)
        if last_error is None:
            raise RuntimeError(f"Failed to fetch URL: {url}")
        raise RuntimeError(f"Failed to fetch URL: {url} ({last_error})") from last_error
