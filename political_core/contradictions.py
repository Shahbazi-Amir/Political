from __future__ import annotations

from collections.abc import Sequence

from .models import Claim, Contradiction, ContradictionType, Evidence, EvidenceStance, ReasoningDecision


def _claim_ids_for_pair(a:Evidence,b:Evidence,claims:Sequence[Claim])->list[str]:
    valid={c.claim_id for c in claims}
    aa=set(a.retrieval_claim_ids)&valid;bb=set(b.retrieval_claim_ids)&valid
    both=sorted(aa&bb)
    if both:return both
    # If both items are explicitly mapped but to different claims, they are not
    # evidence of a contradiction in the same atomic claim.
    if aa and bb:return []
    one=sorted((aa or bb)&valid)
    return one or ([claims[0].claim_id] if claims else ["C1"])


def _validate_model_contradictions(decision:ReasoningDecision,evidence:Sequence[Evidence],claims:Sequence[Claim])->list[Contradiction]:
    valid_e={e.evidence_id for e in evidence};valid_c={c.claim_id for c in claims}
    out=[]
    for c in decision.contradictions:
        if c.evidence_a not in valid_e or c.evidence_b not in valid_e or c.evidence_a==c.evidence_b:continue
        if c.claim_id not in valid_c:continue
        out.append(Contradiction(c.claim_id,c.evidence_a,c.evidence_b,c.contradiction_type,min(1.0,max(0.0,float(c.severity))),bool(c.resolved),c.resolution))
    return out[:20]


def build_contradictions(decision:ReasoningDecision,evidence:Sequence[Evidence],claims:Sequence[Claim]|None=None)->list[Contradiction]:
    claims=list(claims or [])
    supplied=_validate_model_contradictions(decision,evidence,claims)
    if supplied:return supplied
    supports=[e for e in evidence if decision.evidence_stances.get(e.evidence_id,e.stance)==EvidenceStance.SUPPORTS]
    contradicts=[e for e in evidence if decision.evidence_stances.get(e.evidence_id,e.stance)==EvidenceStance.CONTRADICTS]
    out=[]
    for a in supports:
        for b in contradicts:
            claim_ids=_claim_ids_for_pair(a,b,claims)
            if not claim_ids:continue
            # Date conflict is only asserted from explicit event dates, not from any
            # random date token appearing in article text/publication history.
            ctype=ContradictionType.DIRECT_FACT_CONFLICT;severity=.72
            if a.event_date and b.event_date and a.event_date!=b.event_date:
                ctype=ContradictionType.DATE_CONFLICT;severity=.55
            if a.proves_statement_made and not a.supports_underlying_fact:
                ctype=ContradictionType.SOURCE_CLAIM_VS_FACT;severity=.6
            for claim_id in claim_ids:
                out.append(Contradiction(claim_id,a.evidence_id,b.evidence_id,ctype,severity,False,""))
                if len(out)>=20:return out
    return out
