from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from .models import PrimarySourceAssessment, SearchResult, SourceKind
from .text import domain_of, normalize_text

_DOC_PATH_HINTS = ("/law", "/laws", "/decree", "/document", "/regulation", "/judgment", "/constitution", "/gazette", "/act/")
_DOC_TEXT_HINTS = (
    "متن حکم", "حکم انتصاب", "حکم عزل", "قانون", "اصل قانون اساسی", "مصوبه", "آیین نامه", "آیین‌نامه",
    "رأی دادگاه", "رای دادگاه", "فرمان", "decree", "regulation", "judgment", "constitution", "official gazette",
)
_STATEMENT_HINTS = ("بیانیه", "اطلاعیه", "press release", "statement", "سخنگو", "اعلام کرد")
_REPRO_HINTS = ("به نقل از", "به گزارش", "according to", "reported by", "خبرگزاری", "بازنشر")
_NEWS_PATH_HINTS = ("/news/", "/اخبار/", "/press/", "/media/")


def _issuer_key(value:str|None)->str:
    text=normalize_text(value or "").casefold()
    text=re.sub(r"\b(the|office|ministry|organization|agency)\b"," ",text)
    text=re.sub(r"[^\w\u0600-\u06ff]+"," ",text)
    return " ".join(text.split())


def _issuer_compatible(hint:str|None,authority:str|None,domain:str)->bool:
    if not hint or not authority:return True
    if authority.casefold().strip(".")==domain.casefold().strip("."):return True
    raw_hint=normalize_text(hint).casefold().strip();raw_authority=normalize_text(authority).casefold().strip()
    if raw_hint==raw_authority:return True
    a,b=_issuer_key(hint),_issuer_key(authority)
    if not a or not b:return False
    return a==b or a in b or b in a


@dataclass(slots=True)
class AuthorityRegistry:
    """Issuer identity registry. This is NOT a truth/reputation whitelist."""

    domains: dict[str, str] = field(default_factory=dict)

    def add(self, domain: str, issuer: str) -> None:
        key = domain.lower().strip(".")
        if key:self.domains[key] = issuer

    def authority_for(self, domain: str) -> str | None:
        d = domain.lower().strip(".")
        if d in self.domains:return self.domains[d]
        for registered in sorted(self.domains, key=len, reverse=True):
            if d.endswith("." + registered):return self.domains[registered]
        if d.endswith(".gov") or ".gov." in d:return d
        if d.endswith(".mil") or ".mil." in d:return d
        if d.endswith(".int") or d.endswith(".europa.eu"):return d
        return None


@dataclass(slots=True)
class PrimarySourceAssessor:
    authority_registry: AuthorityRegistry = field(default_factory=AuthorityRegistry)

    def assess(self, result: SearchResult, excerpt: str = "") -> PrimarySourceAssessment:
        domain=domain_of(result.url);authority=self.authority_registry.authority_for(domain)
        text=normalize_text(f"{result.title} {result.snippet} {excerpt[:1800]}").casefold();path=urlsplit(result.url).path.casefold()
        doc_path=any(h in path for h in _DOC_PATH_HINTS);doc_text=any(h.casefold() in text for h in _DOC_TEXT_HINTS)
        statement=any(h.casefold() in text for h in _STATEMENT_HINTS);reproduction=any(h.casefold() in text for h in _REPRO_HINTS)
        newsroom_path=any(h in path for h in _NEWS_PATH_HINTS);provider_primary=result.source_kind==SourceKind.PRIMARY_DOCUMENT
        issuer_match=_issuer_compatible(result.issuer_hint,authority,domain)
        signals=[];warnings=[]
        if authority:signals.append("issuer_authority_domain")
        if doc_path:signals.append("document_path")
        if doc_text:signals.append("document_content")
        if provider_primary:signals.append("provider_primary_hint")
        if result.document_type_hint:signals.append("document_type_hint")
        if result.issuer_hint:signals.append("issuer_hint")
        if issuer_match and result.issuer_hint:signals.append("issuer_hint_matches_registry")
        if reproduction:warnings.append("reproduction_language")
        if reproduction and doc_text:warnings.append("possible_document_mirror")
        if statement and not doc_text:warnings.append("statement_not_document")
        if newsroom_path:warnings.append("newsroom_path")
        if not authority:warnings.append("issuer_authority_unverified")
        if authority and not issuer_match:warnings.append("issuer_hint_mismatch")
        authority_match=bool(authority);document_signal=doc_text or bool(result.document_type_hint)
        is_primary=bool(authority_match and issuer_match and document_signal and not reproduction and not(statement and not doc_text))
        if is_primary:
            confidence=.74+.07*doc_path+.05*provider_primary+.04*bool(result.issuer_hint)
            if newsroom_path:confidence-=.04
            confidence=min(.96,confidence)
        else:
            confidence=min(.55,.18+.12*doc_text+.08*provider_primary+.1*authority_match)
            if reproduction:confidence=min(confidence,.36)
            if authority and not issuer_match:confidence=min(confidence,.28)
        issuer=result.issuer_hint or authority;dtype=result.document_type_hint
        if not dtype and doc_text:
            for hint in _DOC_TEXT_HINTS:
                if hint.casefold() in text:dtype=hint;break
        reason="authority, issuer ownership and document signals match" if is_primary else "primary status rejected: document ownership was not established conservatively"
        return PrimarySourceAssessment(is_primary=is_primary,confidence=round(max(0.0,confidence),3),issuer=issuer,publisher=result.publisher or domain,document_type=dtype,authority_match=authority_match,originality_signals=signals,warning_signals=warnings,reason=reason)

    def official_statement_likely(self, result: SearchResult, excerpt: str = "") -> bool:
        domain=domain_of(result.url)
        if not self.authority_registry.authority_for(domain):return result.source_kind==SourceKind.OFFICIAL_STATEMENT
        text=normalize_text(f"{result.title} {result.snippet} {excerpt[:800]}").casefold()
        return result.source_kind==SourceKind.OFFICIAL_STATEMENT or any(h.casefold() in text for h in _STATEMENT_HINTS)
