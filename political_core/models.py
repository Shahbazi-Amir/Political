from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class Verdict(StrEnum):
    TRUE = "true"
    MOSTLY_TRUE = "mostly_true"
    MISSING_CONTEXT = "missing_context"
    MISLEADING = "misleading"
    MOSTLY_FALSE = "mostly_false"
    FALSE = "false"
    UNVERIFIED = "unverified"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    OUTDATED = "outdated"
    OPINION_NOT_FACT = "opinion_not_fact"
    PREDICTION = "prediction"
    VERIFICATION_UNAVAILABLE = "verification_unavailable"


class Intent(StrEnum):
    FACT_CHECK = "fact_check"
    NEWS_CHECK = "news_check"
    QUOTE_CHECK = "quote_check"
    HISTORICAL_CHECK = "historical_check"
    CURRENT_STATUS_CHECK = "current_status_check"
    APPOINTMENT_CHECK = "appointment_check"
    LEGAL_CHECK = "legal_check"
    CONSTITUTIONAL_CHECK = "constitutional_check"
    DOCUMENT_CHECK = "document_check"
    ARGUMENT_ANALYSIS = "argument_analysis"
    CAUSAL_CLAIM_ANALYSIS = "causal_claim_analysis"
    TIMELINE_REQUEST = "timeline_request"
    SOURCE_CHECK = "source_check"
    MEDIA_ANALYSIS = "media_analysis"
    RUMOR_CHECK = "rumor_check"
    NEGATIVE_CLAIM_CHECK = "negative_claim_check"
    COMPARISON = "comparison"
    CONTEXT_CHECK = "context_check"


class ClaimType(StrEnum):
    EVENT = "event"
    APPOINTMENT = "appointment"
    MEMBERSHIP = "membership"
    LEGAL = "legal"
    CONSTITUTIONAL = "constitutional"
    HISTORICAL = "historical"
    CURRENT_STATUS = "current_status"
    QUOTE = "quote"
    NUMBER = "number"
    CAUSAL = "causal"
    IDENTITY = "identity"
    LOCATION = "location"
    TIMELINE = "timeline"
    NEGATIVE = "negative"
    PREDICTION = "prediction"
    OPINION = "opinion"
    INTERPRETATION = "interpretation"
    UNKNOWN = "unknown"


class SourceKind(StrEnum):
    PRIMARY_DOCUMENT = "primary_document"
    OFFICIAL_STATEMENT = "official_statement"
    ACADEMIC = "academic"
    WIRE = "wire"
    NEWSROOM = "newsroom"
    FACT_CHECK = "fact_check"
    SOCIAL = "social"
    AGGREGATOR = "aggregator"
    UNKNOWN = "unknown"


class SourceRole(StrEnum):
    PRIMARY_DOCUMENT = "primary_document"
    OFFICIAL_PARTY_STATEMENT = "official_party_statement"
    DIRECT_REPORTING = "direct_reporting"
    INDEPENDENT_REPORTING = "independent_reporting"
    SECONDARY_REPORTING = "secondary_reporting"
    ANALYSIS = "analysis"
    COMMENTARY = "commentary"
    AGGREGATOR = "aggregator"
    ANONYMOUS_SOURCE = "anonymous_source"
    SOCIAL_POST = "social_post"
    REPRODUCTION = "reproduction"
    UNKNOWN = "unknown"


class EvidenceStance(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"
    UNCLEAR = "unclear"


class RequirementType(StrEnum):
    PRIMARY_DOCUMENT = "primary_document"
    OFFICIAL_MEMBERSHIP_RECORD = "official_membership_record"
    LAW_TEXT = "law_text"
    CONSTITUTIONAL_TEXT = "constitutional_text"
    ORIGINAL_TRANSCRIPT = "original_transcript"
    INDEPENDENT_CORROBORATION = "independent_corroboration"
    BROAD_ARCHIVE_SEARCH = "broad_archive_search"
    ABSENCE_LIMITATIONS = "absence_limitations"
    RECENT_AUTHORITATIVE_RECORD = "recent_authoritative_record"
    REPLACEMENT_SEARCH = "replacement_search"


class ContradictionType(StrEnum):
    DIRECT_FACT_CONFLICT = "direct_fact_conflict"
    DATE_CONFLICT = "date_conflict"
    ROLE_CONFLICT = "role_conflict"
    SCOPE_CONFLICT = "scope_conflict"
    SOURCE_CLAIM_VS_FACT = "source_claim_vs_fact"
    SEMANTIC_ONLY = "semantic_only"
    NOT_A_REAL_CONFLICT = "not_a_real_conflict"


class QuoteMatchStatus(StrEnum):
    EXACT_MATCH = "exact_match"
    NORMALIZED_MATCH = "normalized_match"
    PARTIAL_MATCH = "partial_match"
    PARAPHRASE_ONLY = "paraphrase_only"
    NOT_FOUND = "not_found"


class DocumentState(StrEnum):
    ACTIVE = "active"
    CORRECTED = "corrected"
    RETRACTED = "retracted"
    DELETED = "deleted"
    SUPERSEDED = "superseded"
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
        return cls(2, 8, 5, 5, 1, 8_000, 6 * 60 * 60)

    @classmethod
    def deep(cls) -> "Budget":
        return cls(6, 10, 12, 12, 2, 14_000, 60 * 60)


@dataclass(slots=True, frozen=True)
class SearchQuery:
    text: str
    purpose: str = "neutral"
    claim_id: str | None = None
    priority: int = 50


@dataclass(slots=True)
class SearchResult:
    url: str
    title: str
    snippet: str = ""
    published_at: str | None = None
    updated_at: str | None = None
    publisher: str | None = None
    cited_source: str | None = None
    source_kind: SourceKind = SourceKind.UNKNOWN
    issuer_hint: str | None = None
    document_type_hint: str | None = None
    retrieval_purposes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EntityRef:
    entity_id: str
    canonical_name: str
    surface: str
    entity_type: str = "unknown"
    aliases: list[str] = field(default_factory=list)
    confidence: float = 0.5


@dataclass(slots=True)
class DateInfo:
    raw_text: str
    parsed_datetime: str | None
    calendar: str = "unknown"
    precision: str = "day"
    source: str = "claim"
    confidence: float = 0.0


@dataclass(slots=True)
class EvidenceRequirement:
    requirement_type: RequirementType
    claim_id: str
    mandatory: bool = False
    preferred: bool = True
    satisfied: bool = False
    evidence_ids: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass(slots=True)
class Claim:
    claim_id: str
    original_text: str
    normalized_text: str
    atomic_text: str
    claim_type: ClaimType = ClaimType.UNKNOWN
    intent: Intent = Intent.FACT_CHECK
    entities: list[str] = field(default_factory=list)
    entity_refs: list[EntityRef] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)
    date_info: list[DateInfo] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    required_evidence: list[str] = field(default_factory=list)
    evidence_requirements: list[EvidenceRequirement] = field(default_factory=list)
    is_negative: bool = False
    high_impact: bool = False
    current_status: bool = False
    breaking_news: bool = False
    quoted_texts: list[str] = field(default_factory=list)
    reference_date: str | None = None


@dataclass(slots=True)
class PrimarySourceAssessment:
    is_primary: bool = False
    confidence: float = 0.0
    issuer: str | None = None
    publisher: str | None = None
    document_type: str | None = None
    authority_match: bool = False
    originality_signals: list[str] = field(default_factory=list)
    warning_signals: list[str] = field(default_factory=list)
    reason: str = ""


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
    canonical_url: str = ""
    publisher: str | None = None
    updated_at: str | None = None
    event_date: str | None = None
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source_role: SourceRole = SourceRole.UNKNOWN
    relevance_score: float = 0.0
    source_chain_id: str = ""
    source_chain_confidence: float = 0.0
    source_chain_reason: str = ""
    cited_source: str | None = None
    stance: EvidenceStance = EvidenceStance.UNCLEAR
    correction_status: str | None = None
    retraction_status: str | None = None
    document_state: DocumentState = DocumentState.UNKNOWN
    primary_assessment: PrimarySourceAssessment = field(default_factory=PrimarySourceAssessment)
    proves_statement_made: bool = False
    supports_underlying_fact: bool = False
    retrieval_purposes: list[str] = field(default_factory=list)

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "id": self.evidence_id,
            "title": self.title,
            "domain": self.domain,
            "publisher": self.publisher,
            "published_at": self.published_at,
            "updated_at": self.updated_at,
            "event_date": self.event_date,
            "source_kind": self.source_kind.value,
            "source_role": self.source_role.value,
            "quality_score": round(self.quality_score, 3),
            "relevance_score": round(self.relevance_score, 3),
            "source_chain_id": self.source_chain_id,
            "source_chain_confidence": round(self.source_chain_confidence, 3),
            "independence_key": self.independence_key,
            "primary_assessment": asdict(self.primary_assessment),
            "proves_statement_made": self.proves_statement_made,
            "supports_underlying_fact": self.supports_underlying_fact,
            "document_state": self.document_state.value,
            "retrieval_purposes": self.retrieval_purposes,
            "excerpt": self.excerpt,
        }


@dataclass(slots=True)
class ClaimResearchCoverage:
    claim_id: str
    planned_purposes: list[str] = field(default_factory=list)
    executed_purposes: list[str] = field(default_factory=list)
    successful_purposes: list[str] = field(default_factory=list)
    primary_search_attempted: bool = False
    challenge_search_attempted: bool = False
    archive_search_attempted: bool = False
    replacement_search_attempted: bool = False
    coverage_score: float = 0.0
    query_count: int = 0
    search_errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Contradiction:
    claim_id: str
    evidence_a: str
    evidence_b: str
    contradiction_type: ContradictionType = ContradictionType.DIRECT_FACT_CONFLICT
    severity: float = 0.5
    resolved: bool = False
    resolution: str = ""


@dataclass(slots=True)
class QuoteVerification:
    claim_id: str
    quote: str
    status: QuoteMatchStatus
    evidence_ids: list[str] = field(default_factory=list)
    original_source_found: bool = False
    confidence: float = 0.0


@dataclass(slots=True)
class TimelineEvent:
    entity: str
    role: str
    event_type: str
    entity_id: str | None = None
    institution: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    effective_date: str | None = None
    publication_date: str | None = None
    evidence_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0


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
    evidence_stances: dict[str, EvidenceStance] = field(default_factory=dict)
    missing_evidence: list[str] = field(default_factory=list)
    contradictions: list[Contradiction] = field(default_factory=list)
    usage: dict[str, int | float] = field(default_factory=dict)


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
    atomic_claims: list[Claim] = field(default_factory=list)
    evidence_strength: str = "low"
    supporting_evidence_ids: list[str] = field(default_factory=list)
    contradicting_evidence_ids: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    timeline: list[TimelineEvent] = field(default_factory=list)
    coverage: list[ClaimResearchCoverage] = field(default_factory=list)
    contradictions: list[Contradiction] = field(default_factory=list)
    quote_verifications: list[QuoteVerification] = field(default_factory=list)
    from_cache: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)
    cost_stats: dict[str, Any] = field(default_factory=dict)
    analysis: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        def convert(value: Any) -> Any:
            if isinstance(value, StrEnum):
                return value.value
            if isinstance(value, dict):
                return {k: convert(v) for k, v in value.items()}
            if isinstance(value, list):
                return [convert(v) for v in value]
            return value
        return convert(asdict(self))
