from __future__ import annotations

from dataclasses import dataclass,replace
from collections.abc import Sequence

from .models import (
    Claim,ClaimResearchCoverage,DocumentState,Evidence,EvidenceStance,QuoteMatchStatus,
    QuoteVerification,ReasoningDecision,SourceKind,SourceRole,Verdict,
)
from .provenance import independent_source_count
from .temporal import FreshnessPolicy


@dataclass(slots=True)
class EvidenceProfile:
    independent_sources:int
    primary_count:int
    weak_count:int
    support_count:int
    contradiction_count:int
    average_quality:float
    stale_current_evidence:bool
    official_statement_only:bool
    retracted_count:int
    min_coverage:float

    @property
    def strength(self)->str:
        if self.primary_count and self.average_quality>=.78 and self.independent_sources>=1 and not self.stale_current_evidence:
            return "high"
        if self.independent_sources>=2 and self.average_quality>=.62 and self.min_coverage>=.5:
            return "medium"
        return "low"


def profile_evidence(
    evidence:Sequence[Evidence],
    cited_ids:set[str],
    claims:Sequence[Claim],
    coverage:Sequence[ClaimResearchCoverage]|None=None,
    freshness:FreshnessPolicy|None=None,
)->EvidenceProfile:
    cited=[e for e in evidence if e.evidence_id in cited_ids]
    primary=sum(
        (e.source_kind==SourceKind.PRIMARY_DOCUMENT or e.source_role==SourceRole.PRIMARY_DOCUMENT)
        and e.primary_assessment.is_primary for e in cited
    )
    weak=sum(
        e.source_kind in {SourceKind.UNKNOWN,SourceKind.SOCIAL,SourceKind.AGGREGATOR}
        or e.source_role in {SourceRole.ANONYMOUS_SOURCE,SourceRole.SOCIAL_POST,SourceRole.AGGREGATOR}
        for e in cited
    )
    support=sum(e.stance==EvidenceStance.SUPPORTS for e in cited)
    contradiction=sum(e.stance==EvidenceStance.CONTRADICTS for e in cited)
    avg=sum(e.quality_score for e in cited)/len(cited) if cited else 0.0
    freshness=freshness or FreshnessPolicy()
    stale=bool(cited) and any(c.current_status or c.breaking_news for c in claims) and all(
        freshness.evidence_is_stale(e,claims) for e in cited
    )
    official_only=bool(cited) and all(e.source_role==SourceRole.OFFICIAL_PARTY_STATEMENT for e in cited)
    retracted=sum(e.document_state in {DocumentState.RETRACTED,DocumentState.DELETED} for e in cited)
    min_cov=min((c.coverage_score for c in (coverage or [])),default=1.0)
    return EvidenceProfile(
        independent_source_count(cited),primary,weak,support,contradiction,avg,stale,official_only,retracted,min_cov
    )


def _is_underlying_contested_fact(claims:Sequence[Claim])->bool:
    return any(
        c.high_impact and c.claim_type.value not in {"appointment","membership","legal","constitutional"}
        for c in claims
    )


def apply_guardrails(
    decision:ReasoningDecision,
    evidence:Sequence[Evidence],
    claims:Sequence[Claim],
    *,
    coverage:Sequence[ClaimResearchCoverage]|None=None,
    quote_verifications:Sequence[QuoteVerification]|None=None,
    freshness:FreshnessPolicy|None=None,
)->tuple[ReasoningDecision,EvidenceProfile]:
    valid={e.evidence_id for e in evidence}
    citations=[x for x in decision.citation_ids if x in valid]
    stances={k:v for k,v in decision.evidence_stances.items() if k in valid}
    annotated=[replace(e,stance=stances.get(e.evidence_id,e.stance)) for e in evidence]
    if isinstance(evidence,list):
        evidence[:]=annotated

    confidence=min(1.0,max(0.0,float(decision.confidence)))
    verdict=decision.verdict
    profile=profile_evidence(annotated,set(citations),claims,coverage,freshness)

    if not citations:
        return replace(
            decision,verdict=Verdict.UNVERIFIED,confidence=min(confidence,.22),citation_ids=[],
            evidence_stances=stances,uncertainty=(decision.uncertainty+" نتیجه بدون استناد معتبر بود.").strip()
        ),profile

    cited_count=len(citations)
    if cited_count==1 and profile.weak_count==1:
        confidence=min(confidence,.32)
    elif profile.independent_sources<=1 and profile.primary_count==0:
        confidence=min(confidence,.60)
    if cited_count>1 and profile.independent_sources<=1 and profile.primary_count==0:
        confidence=min(confidence,.56)

    conflict=decision.conflict_detected or profile.contradiction_count>0 or any(
        c.severity>=.6 and not c.resolved for c in decision.contradictions
    )
    if conflict:
        confidence=min(confidence,.62)
        if profile.support_count and profile.contradiction_count and verdict in {Verdict.TRUE,Verdict.FALSE}:
            verdict=Verdict.CONFLICTING_EVIDENCE

    if any(c.breaking_news for c in claims) and profile.primary_count==0:
        confidence=min(confidence,.55)
    if any(c.high_impact for c in claims) and profile.primary_count==0 and profile.independent_sources<2:
        confidence=min(confidence,.52)

    cited=[e for e in annotated if e.evidence_id in citations]
    if _is_underlying_contested_fact(claims) and cited and all(
        e.proves_statement_made and not e.supports_underlying_fact for e in cited
    ):
        confidence=min(confidence,.50)
        if verdict==Verdict.TRUE:
            verdict=Verdict.UNVERIFIED

    for q in quote_verifications or []:
        if q.status not in {QuoteMatchStatus.EXACT_MATCH,QuoteMatchStatus.NORMALIZED_MATCH} or not q.original_source_found:
            confidence=min(confidence,.42)
            if verdict==Verdict.TRUE:
                verdict=Verdict.UNVERIFIED

    if any(c.is_negative for c in claims):
        min_cov=min((c.coverage_score for c in (coverage or [])),default=0.0)
        archive_attempt=all(
            any(x.claim_id==c.claim_id and x.archive_search_attempted for x in (coverage or []))
            for c in claims if c.is_negative
        )
        if not archive_attempt or min_cov<.66:
            confidence=min(confidence,.48)
        elif profile.primary_count==0:
            confidence=min(confidence,.56)
        if verdict==Verdict.TRUE and profile.primary_count==0:
            verdict=Verdict.UNVERIFIED

    if profile.stale_current_evidence:
        confidence=min(confidence,.48)
        if verdict==Verdict.TRUE:
            verdict=Verdict.OUTDATED

    if coverage:
        critical=[x.coverage_score for x in coverage]
        if critical and min(critical)<.5:
            confidence=min(confidence,.50)
        elif critical and min(critical)<.75:
            confidence=min(confidence,.68)

    if profile.retracted_count:
        confidence=min(confidence,.38)
        if verdict==Verdict.TRUE:
            verdict=Verdict.UNVERIFIED

    cited_primaryish=[e for e in cited if e.source_kind==SourceKind.PRIMARY_DOCUMENT]
    if cited_primaryish and not all(e.primary_assessment.is_primary for e in cited_primaryish):
        confidence=min(confidence,.55)

    if confidence>.95 and profile.primary_count==0:
        confidence=.95

    return replace(
        decision,verdict=verdict,confidence=round(confidence,3),citation_ids=citations,evidence_stances=stances
    ),profile
