from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import DocumentState, SearchResult, SourceKind, SourceRole
from .primary_source import AuthorityRegistry, PrimarySourceAssessor
from .text import domain_of, registrable_domain

_BASE_SCORE={
    SourceKind.PRIMARY_DOCUMENT:.94,
    SourceKind.OFFICIAL_STATEMENT:.72,
    SourceKind.ACADEMIC:.84,
    SourceKind.WIRE:.76,
    SourceKind.FACT_CHECK:.74,
    SourceKind.NEWSROOM:.66,
    SourceKind.AGGREGATOR:.34,
    SourceKind.UNKNOWN:.44,
    SourceKind.SOCIAL:.24,
}


@dataclass(slots=True)
class SourcePolicy:
    """Evidence quality/proximity policy. It never encodes ideology or truth-by-brand."""
    domain_kind_overrides:dict[str,SourceKind]=field(default_factory=dict)
    domain_score_overrides:dict[str,float]=field(default_factory=dict)
    authority_registry:AuthorityRegistry=field(default_factory=AuthorityRegistry)
    primary_assessor:PrimarySourceAssessor=field(init=False)

    def __post_init__(self):
        self.primary_assessor=PrimarySourceAssessor(self.authority_registry)

    def primary_assessment(self,result:SearchResult,excerpt:str=""):
        d=domain_of(result.url)
        if self.domain_kind_overrides.get(d)==SourceKind.PRIMARY_DOCUMENT and not self.authority_registry.authority_for(d):
            self.authority_registry.add(d,result.issuer_hint or result.publisher or d)
        return self.primary_assessor.assess(result,excerpt)

    def classify(self,result:SearchResult,excerpt:str="")->SourceKind:
        domain=domain_of(result.url)
        override=self.domain_kind_overrides.get(domain)
        if override:
            if override==SourceKind.PRIMARY_DOCUMENT:
                return SourceKind.PRIMARY_DOCUMENT if self.primary_assessment(result,excerpt).is_primary else SourceKind.UNKNOWN
            return override
        if result.source_kind==SourceKind.PRIMARY_DOCUMENT:
            a=self.primary_assessment(result,excerpt)
            if a.is_primary:return SourceKind.PRIMARY_DOCUMENT
            if a.authority_match:return SourceKind.OFFICIAL_STATEMENT
            return SourceKind.UNKNOWN
        if result.source_kind!=SourceKind.UNKNOWN:
            return result.source_kind
        a=self.primary_assessment(result,excerpt)
        if a.is_primary:return SourceKind.PRIMARY_DOCUMENT
        if self.primary_assessor.official_statement_likely(result,excerpt):
            return SourceKind.OFFICIAL_STATEMENT
        if domain.endswith((".edu",".ac.ir",".edu.tr",".ac.uk")):return SourceKind.ACADEMIC
        if any(x in domain for x in ("x.com","twitter.com","t.me","telegram.me","facebook.com","instagram.com")):
            return SourceKind.SOCIAL
        title=result.title.casefold()
        if any(x in title for x in ("گردآوری اخبار","خبرخوان","aggregator")):return SourceKind.AGGREGATOR
        return SourceKind.UNKNOWN

    def role(self,result:SearchResult,excerpt:str="")->SourceRole:
        kind=self.classify(result,excerpt)
        text=f"{result.title} {result.snippet} {excerpt[:1000]}".casefold()
        if kind==SourceKind.PRIMARY_DOCUMENT:return SourceRole.PRIMARY_DOCUMENT
        if kind==SourceKind.OFFICIAL_STATEMENT:return SourceRole.OFFICIAL_PARTY_STATEMENT
        if kind==SourceKind.SOCIAL:return SourceRole.SOCIAL_POST
        if kind==SourceKind.AGGREGATOR:return SourceRole.AGGREGATOR
        if any(x in text for x in ("منابع آگاه","منبع ناشناس","anonymous source","sources familiar","official familiar")):
            return SourceRole.ANONYMOUS_SOURCE
        if result.cited_source or any(x in text for x in ("به نقل از","به گزارش خبرگزاری","according to","reported by","reuters","associated press")):
            return SourceRole.REPRODUCTION
        if kind in {SourceKind.WIRE,SourceKind.NEWSROOM}:return SourceRole.SECONDARY_REPORTING
        return SourceRole.UNKNOWN

    def score(self,result:SearchResult,excerpt:str,relevance:float=0.0)->float:
        domain=domain_of(result.url)
        kind=self.classify(result,excerpt)
        base=self.domain_score_overrides.get(domain,_BASE_SCORE[kind])
        role=self.role(result,excerpt)
        if kind==SourceKind.PRIMARY_DOCUMENT:
            base=min(base,self.primary_assessment(result,excerpt).confidence)
        if len(excerpt.strip())>=500:base+=.025
        if not result.title.strip():base-=.05
        if role in {SourceRole.REPRODUCTION,SourceRole.AGGREGATOR}:base-=.08
        if role==SourceRole.ANONYMOUS_SOURCE:base-=.12
        base+=min(.06,max(0.0,relevance)*.06)
        return min(1.0,max(0.0,base))

    @staticmethod
    def independence_key(url:str)->str:
        return registrable_domain(url)

    @staticmethod
    def cited_source_hint(result:SearchResult)->str|None:
        if result.cited_source:return result.cited_source.casefold().strip()
        text=f"{result.title} {result.snippet}"
        m=re.search(r"(?:به نقل از|به گزارش)\s+([^،,:؛]{2,60})",text)
        return m.group(1).strip().casefold() if m else None

    @staticmethod
    def document_state(excerpt:str)->DocumentState:
        t=excerpt.casefold()
        if any(x in t for x in ("پس گرفته شد","retracted","withdrawn")):return DocumentState.RETRACTED
        if any(x in t for x in ("اصلاحیه","تصحیح","correction","corrected")):return DocumentState.CORRECTED
        if any(x in t for x in ("حذف شد","deleted")):return DocumentState.DELETED
        if any(x in t for x in ("جایگزین شد","superseded")):return DocumentState.SUPERSEDED
        return DocumentState.ACTIVE
