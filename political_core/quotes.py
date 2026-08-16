from __future__ import annotations
from collections.abc import Sequence
from .models import Claim,Evidence,QuoteMatchStatus,QuoteVerification,SourceKind,SourceRole
from .text import normalize_text,token_set

def _partial_score(a:str,b:str)->float:
    aa,bb=token_set(a),token_set(b)
    return len(aa&bb)/max(1,len(aa)) if aa and bb else 0.0

def verify_quotes(claims:Sequence[Claim],evidence:Sequence[Evidence])->list[QuoteVerification]:
    out=[]
    for c in claims:
        for quote in c.quoted_texts:
            nq=normalize_text(quote).casefold(); best=QuoteMatchStatus.NOT_FOUND; ids=[]; original=False; conf=0.0
            for e in evidence:
                raw=e.excerpt; ne=normalize_text(raw).casefold(); status=QuoteMatchStatus.NOT_FOUND; score=0.0
                if quote in raw: status=QuoteMatchStatus.EXACT_MATCH;score=.98
                elif nq and nq in ne: status=QuoteMatchStatus.NORMALIZED_MATCH;score=.92
                else:
                    p=_partial_score(quote,raw)
                    if p>=.85: status=QuoteMatchStatus.PARTIAL_MATCH;score=min(.82,p)
                    elif p>=.55: status=QuoteMatchStatus.PARAPHRASE_ONLY;score=min(.6,p)
                if status!=QuoteMatchStatus.NOT_FOUND:
                    ids.append(e.evidence_id)
                    original=original or e.source_kind==SourceKind.PRIMARY_DOCUMENT or e.source_role in {SourceRole.PRIMARY_DOCUMENT,SourceRole.DIRECT_REPORTING,SourceRole.OFFICIAL_PARTY_STATEMENT}
                    order=[QuoteMatchStatus.NOT_FOUND,QuoteMatchStatus.PARAPHRASE_ONLY,QuoteMatchStatus.PARTIAL_MATCH,QuoteMatchStatus.NORMALIZED_MATCH,QuoteMatchStatus.EXACT_MATCH]
                    if order.index(status)>order.index(best): best=status;conf=score
            out.append(QuoteVerification(c.claim_id,quote,best,list(dict.fromkeys(ids)),original,round(conf,3)))
    return out
