from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import SearchResult


class SearxNGSearchProvider:
    def __init__(self, base_url: str, timeout: float = 8.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def search(self, query: str, limit: int):
        url = self.base_url + "/search?" + urlencode({"q": query, "format": "json", "language": "fa-IR"})
        req = Request(url, headers={"User-Agent": "PoliticalCore/0.2"})
        with urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read(2_000_000).decode("utf-8", "replace"))
        out = []
        for item in data.get("results", [])[:limit]:
            if not item.get("url"):
                continue
            out.append(SearchResult(url=str(item["url"]), title=str(item.get("title") or ""), snippet=str(item.get("content") or ""), published_at=item.get("publishedDate") or item.get("published_at"), publisher=item.get("engine")))
        return out
