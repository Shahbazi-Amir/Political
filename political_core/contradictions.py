from __future__ import annotations
import re
from collections.abc import Sequence
from .models import Contradiction,ContradictionType,Evidence,EvidenceStance,ReasoningDecision

def _date_tokens(text:str)->set[str]: return set(re.findall(r"\b(?:13|14|19|20)\d{2}(?:[/-]\d{1,2}(?:[/-]\d{1,2})?)?\b",text))
def build_contradictions(decision:ReasoningDecision,evidence:Sequence[Evidence],claim_id:str="C1")->list[Contradiction]:
    if decision.contradictions: return decision.contradictions
    supports=[e for e in evidence if decision.evidence_stances.get(e.evidence_id,e.stance)==EvidenceStance.SUPPORTS]
    contradicts=[e for e in evidence if decision.evidence_stances.get(e.evidence_id,e.stance)==EvidenceStance.CONTRADICTS]
    out=[]
    for a in supports:
        for b in contradicts:
            ad,bd=_date_tokens(f"{a.title} {a.excerpt[:1000]}"),_date_tokens(f"{b.title} {b.excerpt[:1000]}")
            ctype=ContradictionType.DATE_CONFLICT if ad and bd and ad!=bd else ContradictionType.DIRECT_FACT_CONFLICT
            severity=.55 if ctype==ContradictionType.DATE_CONFLICT else .72
            if a.proves_statement_made and not a.supports_underlying_fact: ctype=ContradictionType.SOURCE_CLAIM_VS_FACT;severity=.6
            out.append(Contradiction(claim_id,a.evidence_id,b.evidence_id,ctype,severity,False,""))
    return out[:20]
