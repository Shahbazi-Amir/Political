from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import SearchResult


class SearxNGSearchProvider:
    """Low-cost search adapter for a SearxNG instance with JSON enabled."""

    def __init__(self, base_url: str, timeout: float = 8.0, language: str = "fa") -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.language = language

    def search(self, query: str, limit: int) -> list[SearchResult]:
        params = urlencode({"q": query, "format": "json", "language": self.language, "safesearch": 0})
        req = Request(
            f"{self.base_url}/search?{params}",
            headers={"Accept": "application/json", "User-Agent": "PoliticalCore/0.1"},
        )
        with urlopen(req, timeout=self.timeout) as resp:
            payload = json.load(resp)
        out: list[SearchResult] = []
        for item in payload.get("results", [])[:limit]:
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            out.append(
                SearchResult(
                    url=url,
                    title=str(item.get("title") or "").strip(),
                    snippet=str(item.get("content") or "").strip(),
                    published_at=str(item.get("publishedDate") or "").strip() or None,
                )
            )
        return out
