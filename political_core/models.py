from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Verdict(StrEnum):
    TRUE = "true"
    MOSTLY_TRUE = "mostly_true"
    MISSING_CONTEXT = "missing_context"
    MISLEADING = "misleading"
    FALSE = "false"
    UNVERIFIED = "unverified"


class SourceKind(StrEnum):
    PRIMARY_DOCUMENT = "primary_document"
    OFFICIAL_STATEMENT = "official_statement"
    ACADEMIC = "academic"
    WIRE = "wire"
    NEWSROOM = "newsroom"
    FACT_CHECK = "fact_check"
    SOCIAL = "social"
    UNKNOWN = "unknown"


@dataclass(slots=True, frozen=True)
class Budget:
    max_queries: int
    results_per_query: int
    max_sources: int
    max_fetches: int
    max_reasoning_calls: int
    max_page_chars: int
    cache_ttl_seconds: int

    @classmethod
    def quick(cls) -> "Budget":
        return cls(
            max_queries=2,
            results_per_query=6,
            max_sources=5,
            max_fetches=5,
            max_reasoning_calls=1,
            max_page_chars=8_000,
            cache_ttl_seconds=6 * 60 * 60,
        )

    @classmethod
    def deep(cls) -> "Budget":
        return cls(
            max_queries=6,
            results_per_query=10,
            max_sources=10,
            max_fetches=10,
            max_reasoning_calls=2,
            max_page_chars=14_000,
            cache_ttl_seconds=60 * 60,
        )


@dataclass(slots=True)
class SearchResult:
    url: str
    title: str
    snippet: str = ""
    published_at: str | None = None
    source_kind: SourceKind = SourceKind.UNKNOWN


@dataclass(slots=True)
class Evidence:
    evidence_id: str
    url: str
    title: str
    domain: str
    excerpt: str
    published_at: str | None
    source_kind: SourceKind
    quality_score: float
    independence_key: str

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "id": self.evidence_id,
            "url": self.url,
            "title": self.title,
            "domain": self.domain,
            "published_at": self.published_at,
            "source_kind": self.source_kind.value,
            "quality_score": round(self.quality_score, 3),
            "excerpt": self.excerpt,
        }


@dataclass(slots=True)
class ReasoningDecision:
    verdict: Verdict
    confidence: float
    summary: str
    key_points: list[str] = field(default_factory=list)
    uncertainty: str = ""
    citation_ids: list[str] = field(default_factory=list)
    conflict_detected: bool = False
    conflict_resolution: str = ""


@dataclass(slots=True)
class FactCheckResult:
    claim: str
    normalized_claim: str
    verdict: Verdict
    confidence: float
    summary: str
    key_points: list[str]
    uncertainty: str
    evidence: list[Evidence]
    citation_ids: list[str]
    from_cache: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["verdict"] = self.verdict.value
        for item in data["evidence"]:
            kind = item.get("source_kind")
            if isinstance(kind, SourceKind):
                item["source_kind"] = kind.value
        return data
