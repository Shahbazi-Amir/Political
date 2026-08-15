from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from .models import SearchResult, SourceKind, SourceRole
from .text import domain_of

_BASE_SCORE = {
    SourceKind.PRIMARY_DOCUMENT: 0.96,
    SourceKind.OFFICIAL_STATEMENT: 0.82,
    SourceKind.ACADEMIC: 0.86,
    SourceKind.WIRE: 0.78,
    SourceKind.FACT_CHECK: 0.76,
    SourceKind.NEWSROOM: 0.69,
    SourceKind.AGGREGATOR: 0.40,
    SourceKind.UNKNOWN: 0.50,
    SourceKind.SOCIAL: 0.26,
}


@dataclass(slots=True)
class SourcePolicy:
    """Scores evidence quality/proximity, never ideology or truth-by-brand."""
    domain_kind_overrides: dict[str, SourceKind] = field(default_factory=dict)
    domain_score_overrides: dict[str, float] = field(default_factory=dict)

    def classify(self, result: SearchResult) -> SourceKind:
        domain = domain_of(result.url)
        if domain in self.domain_kind_overrides:
            return self.domain_kind_overrides[domain]
        if result.source_kind != SourceKind.UNKNOWN:
            return result.source_kind
        path = urlsplit(result.url).path.casefold()
        title = result.title.casefold()
        if any(token in path for token in ("/law", "/laws", "/constitution", "/judgment", "/decree", "/document", "/regulation")):
            return SourceKind.PRIMARY_DOCUMENT
        if any(token in title for token in ("official statement", "press release", "بیانیه رسمی", "متن حکم", "حکم انتصاب", "متن قانون")):
            return SourceKind.OFFICIAL_STATEMENT
        if domain.endswith((".edu", ".ac.ir", ".edu.tr", ".ac.uk")):
            return SourceKind.ACADEMIC
        if any(x in domain for x in ("x.com", "twitter.com", "t.me", "telegram.me", "facebook.com", "instagram.com")):
            return SourceKind.SOCIAL
        if any(x in title for x in ("گردآوری اخبار", "خبرخوان", "aggregator")):
            return SourceKind.AGGREGATOR
        return SourceKind.UNKNOWN

    def role(self, result: SearchResult, excerpt: str = "") -> SourceRole:
        kind = self.classify(result)
        text = f"{result.title} {result.snippet} {excerpt[:800]}".casefold()
        if kind == SourceKind.PRIMARY_DOCUMENT:
            return SourceRole.PRIMARY_DOCUMENT
        if kind == SourceKind.OFFICIAL_STATEMENT:
            return SourceRole.OFFICIAL_PARTY_STATEMENT
        if kind == SourceKind.SOCIAL:
            return SourceRole.SOCIAL_POST
        if kind == SourceKind.AGGREGATOR:
            return SourceRole.AGGREGATOR
        if result.cited_source or any(x in text for x in ("به نقل از", "به گزارش خبرگزاری", "according to", "reported by")):
            return SourceRole.REPRODUCTION
        if any(x in text for x in ("منابع آگاه", "منبع ناشناس", "anonymous source", "sources familiar")):
            return SourceRole.ANONYMOUS_SOURCE
        if kind in {SourceKind.WIRE, SourceKind.NEWSROOM}:
            return SourceRole.SECONDARY_REPORTING
        return SourceRole.UNKNOWN

    def score(self, result: SearchResult, excerpt: str, relevance: float = 0.0) -> float:
        domain = domain_of(result.url)
        base = self.domain_score_overrides.get(domain, _BASE_SCORE[self.classify(result)])
        role = self.role(result, excerpt)
        if len(excerpt.strip()) >= 500:
            base += 0.03
        if not result.title.strip():
            base -= 0.05
        if role in {SourceRole.REPRODUCTION, SourceRole.AGGREGATOR}:
            base -= 0.08
        if role == SourceRole.ANONYMOUS_SOURCE:
            base -= 0.10
        base += min(0.08, max(0.0, relevance) * 0.08)
        return min(1.0, max(0.0, base))

    @staticmethod
    def independence_key(url: str) -> str:
        domain = domain_of(url)
        parts = domain.split(".")
        if len(parts) <= 2:
            return domain
        if len(parts[-2]) <= 3 and len(parts[-1]) == 2:
            return ".".join(parts[-3:])
        return ".".join(parts[-2:])

    @staticmethod
    def cited_source_hint(result: SearchResult) -> str | None:
        if result.cited_source:
            return result.cited_source.casefold().strip()
        text = f"{result.title} {result.snippet}"
        m = re.search(r"(?:به نقل از|به گزارش)\s+([^،,:؛]{2,60})", text)
        return m.group(1).strip().casefold() if m else None
