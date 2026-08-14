from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlsplit

from .models import SearchResult, SourceKind
from .text import domain_of


_BASE_SCORE = {
    SourceKind.PRIMARY_DOCUMENT: 1.00,
    SourceKind.OFFICIAL_STATEMENT: 0.90,
    SourceKind.ACADEMIC: 0.88,
    SourceKind.WIRE: 0.82,
    SourceKind.FACT_CHECK: 0.78,
    SourceKind.NEWSROOM: 0.72,
    SourceKind.UNKNOWN: 0.52,
    SourceKind.SOCIAL: 0.28,
}


@dataclass(slots=True)
class SourcePolicy:
    """Scores evidence quality, not political correctness or ideological alignment."""

    domain_kind_overrides: dict[str, SourceKind] = field(default_factory=dict)
    domain_score_overrides: dict[str, float] = field(default_factory=dict)

    def classify(self, result: SearchResult) -> SourceKind:
        domain = domain_of(result.url)
        if domain in self.domain_kind_overrides:
            return self.domain_kind_overrides[domain]
        if result.source_kind != SourceKind.UNKNOWN:
            return result.source_kind

        path = urlsplit(result.url).path.lower()
        title = result.title.casefold()
        # Generic signals only. No political outlet is permanently whitelisted as "truth".
        if any(token in path for token in ("/law", "/laws", "/constitution", "/judgment", "/decree", "/document")):
            return SourceKind.PRIMARY_DOCUMENT
        if any(token in title for token in ("official statement", "press release", "بیانیه رسمی", "متن حکم")):
            return SourceKind.OFFICIAL_STATEMENT
        if domain.endswith(".edu") or domain.endswith(".ac.ir"):
            return SourceKind.ACADEMIC
        if any(x in domain for x in ("x.com", "twitter.com", "t.me", "telegram.me", "facebook.com", "instagram.com")):
            return SourceKind.SOCIAL
        return SourceKind.UNKNOWN

    def score(self, result: SearchResult, excerpt: str) -> float:
        domain = domain_of(result.url)
        if domain in self.domain_score_overrides:
            base = self.domain_score_overrides[domain]
        else:
            base = _BASE_SCORE[self.classify(result)]
        if len(excerpt.strip()) >= 500:
            base += 0.03
        if not result.title.strip():
            base -= 0.05
        return min(1.0, max(0.0, base))

    @staticmethod
    def independence_key(url: str) -> str:
        """Conservative independence key: same registrable-looking host counts once.

        We intentionally do not pretend to know hidden ownership/syndication. Deployments can
        override or pre-normalize domains when media groups share the same editorial source.
        """
        domain = domain_of(url)
        parts = domain.split(".")
        if len(parts) <= 2:
            return domain
        # Handles common ccTLD patterns conservatively enough without an external PSL dependency.
        if len(parts[-2]) <= 3 and len(parts[-1]) == 2:
            return ".".join(parts[-3:])
        return ".".join(parts[-2:])
