from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from collections.abc import Sequence

from .models import Claim, Evidence, EvidenceStance, ReasoningDecision, SourceKind, SourceRole, Verdict
from .provenance import independent_source_count


@dataclass(slots=True)
class EvidenceProfile:
    independent_sources: int
    primary_count: int
    weak_count: int
    support_count: int
    contradiction_count: int
    average_quality: float
    stale_current_evidence: bool

    @property
    def strength(self) -> str:
        if self.primary_count and self.average_quality >= 0.78 and self.independent_sources >= 1:
            return "high"
        if self.independent_sources >= 2 and self.average_quality >= 0.62:
            return "medium"
        return "low"


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def profile_evidence(evidence: Sequence[Evidence], cited_ids: set[str], claims: Sequence[Claim]) -> EvidenceProfile:
    cited = [e for e in evidence if e.evidence_id in cited_ids]
    primary = sum(e.source_kind == SourceKind.PRIMARY_DOCUMENT or e.source_role == SourceRole.PRIMARY_DOCUMENT for e in cited)
    weak = sum(e.source_kind in {SourceKind.UNKNOWN, SourceKind.SOCIAL, SourceKind.AGGREGATOR} or e.source_role in {SourceRole.ANONYMOUS_SOURCE, SourceRole.SOCIAL_POST, SourceRole.AGGREGATOR} for e in cited)
    support = sum(e.stance == EvidenceStance.SUPPORTS for e in cited)
    contradiction = sum(e.stance == EvidenceStance.CONTRADICTS for e in cited)
    avg = sum(e.quality_score for e in cited) / len(cited) if cited else 0.0
    current = any(c.current_status for c in claims)
    stale = False
    if current and cited:
        now = datetime.now(timezone.utc)
        dated = [_parse_date(e.updated_at or e.published_at or e.event_date) for e in cited]
        dated = [d for d in dated if d is not None]
        stale = bool(dated) and all((now - d).days > 180 for d in dated)
    return EvidenceProfile(independent_source_count(cited), primary, weak, support, contradiction, avg, stale)


def apply_guardrails(decision: ReasoningDecision, evidence: Sequence[Evidence], claims: Sequence[Claim]) -> tuple[ReasoningDecision, EvidenceProfile]:
    valid = {e.evidence_id for e in evidence}
    citations = [x for x in decision.citation_ids if x in valid]
    stances = {k: v for k, v in decision.evidence_stances.items() if k in valid}
    annotated = [replace(e, stance=stances.get(e.evidence_id, e.stance)) for e in evidence]
    if isinstance(evidence, list):
        evidence[:] = annotated
    confidence = min(1.0, max(0.0, float(decision.confidence)))
    verdict = decision.verdict
    profile = profile_evidence(annotated, set(citations), claims)

    if not citations:
        return replace(decision, verdict=Verdict.UNVERIFIED, confidence=min(confidence, 0.25), citation_ids=[], evidence_stances=stances, uncertainty=(decision.uncertainty + " نتیجه بدون استناد معتبر بود و تأییدنشده تلقی شد.").strip()), profile
    cited_count = len(citations)
    if cited_count == 1 and profile.weak_count == 1:
        confidence = min(confidence, 0.35)
    elif profile.independent_sources <= 1 and profile.primary_count == 0:
        confidence = min(confidence, 0.62)
    if cited_count > 1 and profile.independent_sources <= 1 and profile.primary_count == 0:
        confidence = min(confidence, 0.58)
    conflict = decision.conflict_detected or profile.contradiction_count > 0
    if conflict:
        confidence = min(confidence, 0.65)
        if profile.support_count and profile.contradiction_count and verdict in {Verdict.TRUE, Verdict.FALSE}:
            verdict = Verdict.CONFLICTING_EVIDENCE
    if any(c.breaking_news for c in claims) and profile.primary_count == 0:
        confidence = min(confidence, 0.60)
    if any(c.high_impact for c in claims) and profile.primary_count == 0 and profile.independent_sources < 2:
        confidence = min(confidence, 0.55)
    if any(c.is_negative for c in claims) and profile.primary_count == 0:
        confidence = min(confidence, 0.58)
        if verdict == Verdict.TRUE:
            verdict = Verdict.UNVERIFIED
    if profile.stale_current_evidence:
        confidence = min(confidence, 0.55)
        if verdict == Verdict.TRUE:
            verdict = Verdict.OUTDATED
    if confidence > 0.95 and profile.primary_count == 0:
        confidence = 0.95
    return replace(decision, verdict=verdict, confidence=confidence, citation_ids=citations, evidence_stances=stances), profile
