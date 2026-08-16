from __future__ import annotations

from collections.abc import Sequence

from .models import Claim, Evidence, QuoteMatchStatus, QuoteVerification, SourceKind, SourceRole
from .text import normalize_text, token_set

_ORDER=[QuoteMatchStatus.NOT_FOUND,QuoteMatchStatus.PARAPHRASE_ONLY,QuoteMatchStatus.PARTIAL_MATCH,QuoteMatchStatus.NORMALIZED_MATCH,QuoteMatchStatus.EXACT_MATCH]


def _partial_score(a:str,b:str)->float:
    aa,bb=token_set(a),token_set(b)
    return len(aa&bb)/max(1,len(aa)) if aa and bb else 0.0


def _match(quote:str,e:Evidence)->tuple[QuoteMatchStatus,float]:
    raw=e.excerpt;nq=normalize_text(quote).casefold();ne=normalize_text(raw).casefold()
    if quote in raw:return QuoteMatchStatus.EXACT_MATCH,.98
    if nq and nq in ne:return QuoteMatchStatus.NORMALIZED_MATCH,.92
    p=_partial_score(quote,raw)
    if p>=.85:return QuoteMatchStatus.PARTIAL_MATCH,min(.82,p)
    if p>=.55:return QuoteMatchStatus.PARAPHRASE_ONLY,min(.6,p)
    return QuoteMatchStatus.NOT_FOUND,0.0


def _is_original_quote_source(e:Evidence)->bool:
    # Direct reporting alone is not the speaker's original transcript.
    if e.source_kind==SourceKind.PRIMARY_DOCUMENT or e.source_role==SourceRole.PRIMARY_DOCUMENT:return True
    return bool(e.source_role==SourceRole.OFFICIAL_PARTY_STATEMENT and e.primary_assessment.authority_match)


def verify_quotes(claims:Sequence[Claim],evidence:Sequence[Evidence])->list[QuoteVerification]:
    out=[]
    for c in claims:
        relevant=[e for e in evidence if not e.retrieval_claim_ids or c.claim_id in e.retrieval_claim_ids]
        for quote in c.quoted_texts:
            matches=[]
            for e in relevant:
                status,score=_match(quote,e)
                if status!=QuoteMatchStatus.NOT_FOUND:matches.append((status,score,e))
            if not matches:
                out.append(QuoteVerification(c.claim_id,quote,QuoteMatchStatus.NOT_FOUND,[],False,0.0));continue
            best=max(_ORDER.index(status) for status,_,_ in matches)
            best_matches=[x for x in matches if _ORDER.index(x[0])==best]
            status=best_matches[0][0];ids=list(dict.fromkeys(e.evidence_id for _,_,e in best_matches));conf=max(score for _,score,_ in best_matches)
            # Important: exact-match and original-source must belong to the SAME best-level evidence set.
            original=any(_is_original_quote_source(e) for _,_,e in best_matches)
            out.append(QuoteVerification(c.claim_id,quote,status,ids,original,round(conf,3)))
    return out
