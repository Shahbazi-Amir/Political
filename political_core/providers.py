from __future__ import annotations

from typing import Protocol, Sequence

from .models import Evidence, ReasoningDecision, SearchResult


class SearchProvider(Protocol):
    def search(self, query: str, limit: int) -> Sequence[SearchResult]: ...


class ReasoningProvider(Protocol):
    def evaluate(self, claim: str, evidence: Sequence[Evidence]) -> ReasoningDecision: ...


class Fetcher(Protocol):
    def fetch_text(self, url: str, max_chars: int, relevance_terms: str | None = None) -> str: ...
