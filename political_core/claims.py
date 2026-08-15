from __future__ import annotations

import re

from .models import Claim, ClaimType, Intent, SearchQuery
from .text import normalize_text

_NEGATIVE = ("هیچ", "وجود ندارد", "وجود نداشته", "نبوده", "نیست", "نشده", "صادر نشده", "تکذیب شده")
_HIGH_IMPACT = ("جنگ", "حمله", "موشک", "کشته", "مرگ", "ترور", "بازداشت", "اعدام", "کودتا", "انتخابات", "استعفا", "عزل", "انتصاب", "جرم", "اتهام")
_CURRENT = ("امروز", "الان", "اکنون", "در حال حاضر", "فعلا", "فعلاً", "هم اکنون", "هم‌اکنون")
_BREAKING = ("فوری", "همین الان", "دقایقی پیش", "ساعتی پیش", "تازه", "لحظاتی پیش")


def classify_intent(text: str) -> Intent:
    t = normalize_text(text).casefold()
    if any(x in t for x in ("استدلال", "مغالطه", "نتیجه گیری", "نتیجه‌گیری")):
        return Intent.ARGUMENT_ANALYSIS
    if any(x in t for x in ("نقل قول", "نقل‌قول", "گفته که", "این جمله را گفته")):
        return Intent.QUOTE_CHECK
    if any(x in t for x in ("قانون اساسی", "اصل 176", "اصل ۱۷۶")):
        return Intent.CONSTITUTIONAL_CHECK
    if any(x in t for x in ("قانون", "حقوقی", "مصوبه")):
        return Intent.LEGAL_CHECK
    if any(x in t for x in ("حکم", "منصوب", "انتصاب", "عزل", "نماینده")):
        return Intent.APPOINTMENT_CHECK
    if any(x in t for x in ("خط زمانی", "تایم لاین", "تایملاین", "به ترتیب", "از چه سال")):
        return Intent.TIMELINE_REQUEST
    if any(x in t for x in _NEGATIVE):
        return Intent.NEGATIVE_CLAIM_CHECK
    if any(x in t for x in _CURRENT):
        return Intent.CURRENT_STATUS_CHECK
    if any(x in t for x in ("شایعه", "شنیده", "میگن", "می گن")):
        return Intent.RUMOR_CHECK
    if any(x in t for x in ("خبر", "رسانه", "گزارش")):
        return Intent.NEWS_CHECK
    return Intent.FACT_CHECK


def classify_claim_type(text: str, intent: Intent | None = None) -> ClaimType:
    t = normalize_text(text).casefold()
    intent = intent or classify_intent(t)
    if intent == Intent.CONSTITUTIONAL_CHECK:
        return ClaimType.CONSTITUTIONAL
    if intent == Intent.LEGAL_CHECK:
        return ClaimType.LEGAL
    if intent == Intent.TIMELINE_REQUEST:
        return ClaimType.TIMELINE
    if intent == Intent.QUOTE_CHECK:
        return ClaimType.QUOTE
    if any(x in t for x in ("منصوب", "انتصاب", "حکم", "عزل", "دبیر")):
        return ClaimType.APPOINTMENT
    if intent == Intent.NEGATIVE_CLAIM_CHECK:
        return ClaimType.NEGATIVE
    if any(x in t for x in ("عضو", "عضویت", "نماینده")):
        return ClaimType.MEMBERSHIP
    if any(x in t for x in _CURRENT):
        return ClaimType.CURRENT_STATUS
    if any(x in t for x in ("چون", "به دلیل", "باعث", "سبب")):
        return ClaimType.CAUSAL
    if any(x in t for x in ("خواهد", "پیش بینی", "پیش‌بینی", "احتمالا", "احتمالاً")):
        return ClaimType.PREDICTION
    return ClaimType.EVENT


def _required_evidence(claim_type: ClaimType) -> list[str]:
    mapping = {
        ClaimType.APPOINTMENT: ["appointment_or_replacement_document", "official_membership_record"],
        ClaimType.MEMBERSHIP: ["official_membership_record", "appointment_or_replacement_document"],
        ClaimType.CONSTITUTIONAL: ["constitutional_text"],
        ClaimType.LEGAL: ["law_or_primary_legal_text"],
        ClaimType.QUOTE: ["original_transcript_audio_video"],
        ClaimType.CURRENT_STATUS: ["recent_primary_or_authoritative_record"],
        ClaimType.NEGATIVE: ["broad_archive_search", "absence_limitations"],
        ClaimType.TIMELINE: ["dated_primary_or_authoritative_records"],
    }
    return mapping.get(claim_type, ["independent_corroboration"])


def _split_atomic(text: str) -> list[str]:
    text = normalize_text(text).strip(" ؟?!.")
    parts = [p.strip() for p in re.split(r"[؛;\n]+|\s+(?:و\s+به\s+همین\s+دلیل|بنابراین|در نتیجه|اما|ولی)\s+", text) if p.strip()]
    if len(parts) == 1 and len(text) > 180:
        parts = [p.strip() for p in re.split(r"\s+و\s+(?=(?:چون|اینکه|آیا|بعد|همچنین|اگر|نماینده|دبیر|عضو))", text) if p.strip()]
    return parts[:8] or [text]


def _dates(text: str) -> list[str]:
    return re.findall(r"\b(?:13|14|19|20)\d{2}(?:[/-]\d{1,2}(?:[/-]\d{1,2})?)?\b", normalize_text(text))


def _entities(text: str) -> list[str]:
    out = re.findall(r"[«\"]([^»\"]{2,80})[»\"]", text)
    for m in re.finditer(r"(?:آقای|خانم|دکتر|سردار|آیت الله|آیت‌الله)\s+([\u0600-\u06ff]+(?:\s+[\u0600-\u06ff]+){0,3})", text):
        out.append(m.group(1))
    return list(dict.fromkeys(x.strip() for x in out if x.strip()))[:12]


def analyze_claims(text: str) -> list[Claim]:
    normalized = normalize_text(text)
    intent = classify_intent(normalized)
    parts = _split_atomic(normalized)
    claims: list[Claim] = []
    for idx, part in enumerate(parts, start=1):
        ctype = classify_claim_type(part, intent)
        negative = any(x in part.casefold() for x in _NEGATIVE)
        required = _required_evidence(ctype)
        if negative:
            required = list(dict.fromkeys(required + ["broad_archive_search", "absence_limitations"]))
        claim = Claim(
            claim_id=f"C{idx}", original_text=text, normalized_text=normalized, atomic_text=part,
            claim_type=ctype, intent=intent, entities=_entities(part), dates=_dates(part), required_evidence=required,
            is_negative=negative, high_impact=any(x in part.casefold() for x in _HIGH_IMPACT),
            current_status=any(x in part.casefold() for x in _CURRENT) or ctype == ClaimType.CURRENT_STATUS,
            breaking_news=any(x in part.casefold() for x in _BREAKING),
        )
        if idx > 1 and any(x in normalized for x in ("بنابراین", "در نتیجه", "به همین دلیل")):
            claim.dependencies = [c.claim_id for c in claims]
        claims.append(claim)
    return claims


def plan_queries(claims: list[Claim], limit: int) -> list[SearchQuery]:
    planned: list[SearchQuery] = []
    for claim in claims:
        q = claim.atomic_text[:300]
        planned.append(SearchQuery(q, "neutral", claim.claim_id))
        if claim.claim_type in {ClaimType.APPOINTMENT, ClaimType.MEMBERSHIP}:
            planned.append(SearchQuery(f'{q[:220]} "متن حکم" OR "حکم انتصاب"', "primary", claim.claim_id))
        elif claim.claim_type in {ClaimType.LEGAL, ClaimType.CONSTITUTIONAL}:
            planned.append(SearchQuery(f'{q[:220]} "متن قانون" OR "اصل"', "primary", claim.claim_id))
        elif claim.claim_type == ClaimType.QUOTE:
            planned.append(SearchQuery(f'{q[:220]} "متن کامل" OR "ویدئو"', "primary", claim.claim_id))
        else:
            planned.append(SearchQuery(f'{q[:240]} "منبع رسمی"', "primary", claim.claim_id))
        if limit > 2:
            planned.append(SearchQuery(f'{q[:250]} تکذیب OR نادرست OR خلاف', "challenge", claim.claim_id))
            planned.append(SearchQuery(f'{q[:250]} تایید OR تأیید OR سند', "support", claim.claim_id))
            if claim.current_status:
                planned.append(SearchQuery(f'{q[:230]} جدیدترین OR امروز OR اکنون', "freshness", claim.claim_id))
            if claim.is_negative:
                planned.append(SearchQuery(f'{q[:220]} آرشیو OR حکم OR سند', "negative_existence", claim.claim_id))
    out: list[SearchQuery] = []
    seen: set[str] = set()
    for item in planned:
        key = normalize_text(item.text).casefold()
        if key and key not in seen:
            seen.add(key)
            out.append(item)
        if len(out) >= limit:
            break
    return out
