from __future__ import annotations
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit
from .models import PrimarySourceAssessment,SearchResult,SourceKind
from .text import domain_of,normalize_text
_DOC_PATH_HINTS=("/law","/laws","/decree","/document","/regulation","/judgment","/constitution","/gazette","/act/")
_DOC_TEXT_HINTS=("متن حکم","حکم انتصاب","حکم عزل","قانون","اصل قانون اساسی","مصوبه","آیین نامه","آیین‌نامه","رأی دادگاه","رای دادگاه","فرمان","decree","regulation","judgment","constitution","official gazette")
_STATEMENT_HINTS=("بیانیه","اطلاعیه","press release","statement","سخنگو","اعلام کرد")
_REPRO_HINTS=("به نقل از","به گزارش","according to","reported by","خبرگزاری")
@dataclass(slots=True)
class AuthorityRegistry:
    """Issuer identity registry, not a truth/reputation whitelist."""
    domains:dict[str,str]=field(default_factory=dict)
    def add(self,domain:str,issuer:str)->None: self.domains[domain.lower().strip(".")]=issuer
    def authority_for(self,domain:str)->str|None:
        d=domain.lower().strip(".")
        if d in self.domains:return self.domains[d]
        if d.endswith(".gov") or ".gov." in d:return d
        if d.endswith(".mil") or ".mil." in d:return d
        if d.endswith(".int") or d.endswith(".europa.eu"):return d
        return None
@dataclass(slots=True)
class PrimarySourceAssessor:
    authority_registry:AuthorityRegistry=field(default_factory=AuthorityRegistry)
    def assess(self,result:SearchResult,excerpt:str="")->PrimarySourceAssessment:
        domain=domain_of(result.url);authority=self.authority_registry.authority_for(domain)
        text=normalize_text(f"{result.title} {result.snippet} {excerpt[:1800]}").casefold();path=urlsplit(result.url).path.casefold()
        doc_path=any(h in path for h in _DOC_PATH_HINTS);doc_text=any(h.casefold() in text for h in _DOC_TEXT_HINTS)
        statement=any(h.casefold() in text for h in _STATEMENT_HINTS);reproduction=any(h.casefold() in text for h in _REPRO_HINTS)
        provider_primary=result.source_kind==SourceKind.PRIMARY_DOCUMENT;signals=[];warnings=[]
        if authority:signals.append("issuer_authority_domain")
        if doc_path:signals.append("document_path")
        if doc_text:signals.append("document_content")
        if provider_primary:signals.append("provider_primary_hint")
        if result.document_type_hint:signals.append("document_type_hint")
        if result.issuer_hint:signals.append("issuer_hint")
        if reproduction:warnings.append("reproduction_language")
        if statement and not doc_text:warnings.append("statement_not_document")
        if not authority:warnings.append("issuer_authority_unverified")
        authority_match=bool(authority);document_signal=doc_text or bool(result.document_type_hint)
        is_primary=authority_match and document_signal and not (reproduction and not doc_text)
        if is_primary:
            confidence=.72+.08*doc_path+.06*provider_primary+.04*bool(result.issuer_hint);confidence=min(.96,confidence)
        else:
            confidence=min(.55,.2+.12*doc_text+.08*provider_primary+.1*authority_match)
        issuer=result.issuer_hint or authority;dtype=result.document_type_hint
        if not dtype and doc_text:
            for h in _DOC_TEXT_HINTS:
                if h.casefold() in text:dtype=h;break
        reason="authority and document signals match" if is_primary else "primary status rejected: issuer authority and document ownership were not both established"
        return PrimarySourceAssessment(is_primary,round(confidence,3),issuer,result.publisher or domain,dtype,authority_match,signals,warnings,reason)
    def official_statement_likely(self,result:SearchResult,excerpt:str="")->bool:
        domain=domain_of(result.url)
        if not self.authority_registry.authority_for(domain):return result.source_kind==SourceKind.OFFICIAL_STATEMENT
        text=normalize_text(f"{result.title} {result.snippet} {excerpt[:800]}").casefold()
        return result.source_kind==SourceKind.OFFICIAL_STATEMENT or any(h.casefold() in text for h in _STATEMENT_HINTS)
