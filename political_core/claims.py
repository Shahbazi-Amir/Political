from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Protocol, Sequence

from .analysis import extract_quoted_phrases
from .entity import EntityAliasRegistry, extract_entities
from .models import Claim, ClaimResearchCoverage, ClaimType, EvidenceRequirement, Intent, RequirementType, SearchQuery
from .temporal import parse_date_text
from .text import normalize_text

_NEGATIVE=("هیچ","وجود ندارد","وجود نداشته","نبوده","نیست","نشده","صادر نشده","تکذیب شده","پیدا نشده")
_HIGH_IMPACT=("جنگ","حمله","موشک","کشته","مرگ","ترور","بازداشت","اعدام","کودتا","انتخابات","استعفا","عزل","برکنار","انتصاب","جرم","اتهام")
_CURRENT=("امروز","الان","اکنون","در حال حاضر","فعلا","فعلاً","هم اکنون","هم‌اکنون","فعلی")
_BREAKING=("فوری","همین الان","دقایقی پیش","ساعتی پیش","تازه","لحظاتی پیش")
_COMPLEX_MARKERS=("بنابراین","در نتیجه","به همین دلیل","در حالی که","اگر","مگر","از طرفی","در مقابل")
_FILLER_PREFIXES=(
    r"^(?:سلام[،,\s]*)?",r"^(?:میخوام بدونم|می خواهم بدانم|می‌خواهم بدانم)\s+",
    r"^(?:لطفا|لطفاً)\s+",r"^(?:آیا|ایا)\s+",r"^(?:درسته که|درست است که|واقعا|واقعاً)\s+",
)
_FILLER_SUFFIXES=(r"\s*(?:درسته|درست است|واقعیه|واقعی است)\s*[؟?]?$",)


class ClaimDecomposer(Protocol):
    def decompose(self,text:str)->Sequence[str]: ...


def classify_intent(text:str)->Intent:
    t=normalize_text(text).casefold()
    if any(x in t for x in ("استدلال","مغالطه","نتیجه گیری","نتیجه‌گیری")):return Intent.ARGUMENT_ANALYSIS
    if any(x in t for x in ("نقل قول","نقل‌قول","گفته که","این جمله را گفته","دقیقاً گفت")):return Intent.QUOTE_CHECK
    if any(x in t for x in ("قانون اساسی","اصل 176","اصل ۱۷۶")):return Intent.CONSTITUTIONAL_CHECK
    if any(x in t for x in ("قانون","حقوقی","مصوبه","آیین نامه","آیین‌نامه")):return Intent.LEGAL_CHECK
    if any(x in t for x in ("حکم","منصوب","انتصاب","عزل","برکنار","نماینده","دبیر")):return Intent.APPOINTMENT_CHECK
    if any(x in t for x in ("خط زمانی","تایم لاین","تایملاین","به ترتیب","از چه سال")):return Intent.TIMELINE_REQUEST
    if any(x in t for x in _NEGATIVE):return Intent.NEGATIVE_CLAIM_CHECK
    if any(x in t for x in _CURRENT):return Intent.CURRENT_STATUS_CHECK
    if any(x in t for x in ("شایعه","شنیده","میگن","می گن")):return Intent.RUMOR_CHECK
    if any(x in t for x in ("خبر","رسانه","گزارش")):return Intent.NEWS_CHECK
    return Intent.FACT_CHECK


def classify_claim_type(text:str,intent:Intent|None=None)->ClaimType:
    t=normalize_text(text).casefold();intent=intent or classify_intent(t)
    if intent==Intent.CONSTITUTIONAL_CHECK:return ClaimType.CONSTITUTIONAL
    if intent==Intent.LEGAL_CHECK:return ClaimType.LEGAL
    if intent==Intent.TIMELINE_REQUEST:return ClaimType.TIMELINE
    if intent==Intent.QUOTE_CHECK or extract_quoted_phrases(t):return ClaimType.QUOTE
    if any(x in t for x in ("منصوب","انتصاب","حکم","عزل","برکنار","دبیر")):return ClaimType.APPOINTMENT
    if any(x in t for x in ("عضو","عضویت","نماینده")):return ClaimType.MEMBERSHIP
    if any(x in t for x in _CURRENT):return ClaimType.CURRENT_STATUS
    if any(x in t for x in ("چون","به دلیل","باعث","سبب")):return ClaimType.CAUSAL
    if any(x in t for x in ("خواهد","پیش بینی","پیش‌بینی","احتمالا","احتمالاً")):return ClaimType.PREDICTION
    if intent==Intent.NEGATIVE_CLAIM_CHECK:return ClaimType.NEGATIVE
    return ClaimType.EVENT


def complexity_score(text:str)->int:
    t=normalize_text(text)
    return min(4,len(t)//140)+sum(1 for x in _COMPLEX_MARKERS if x in t)+min(3,len(re.findall(r"[؛;\n]",t)))+(2 if extract_quoted_phrases(t) and len(t)>120 else 0)


def _split_atomic(text:str)->list[str]:
    text=normalize_text(text).strip(" ؟?!.")
    parts=[p.strip() for p in re.split(r"[؛;\n]+|\s+(?:و\s+به\s+همین\s+دلیل|بنابراین|در نتیجه|اما|ولی)\s+",text) if p.strip()]
    if len(parts)==1 and len(text)>160:
        parts=[p.strip() for p in re.split(r"\s+و\s+(?=(?:چون|اینکه|آیا|بعد|همچنین|اگر|نماینده|دبیر|عضو|حق|حکم))",text) if p.strip()]
    return parts[:8] or [text]


def _requirements(ctype:ClaimType,claim_id:str,negative:bool,current:bool)->list[EvidenceRequirement]:
    req=[]
    def add(rt:RequirementType,mandatory:bool=False,preferred:bool=True)->None:req.append(EvidenceRequirement(rt,claim_id,mandatory,preferred))
    if ctype==ClaimType.APPOINTMENT:
        add(RequirementType.PRIMARY_DOCUMENT,True);add(RequirementType.OFFICIAL_MEMBERSHIP_RECORD)
    elif ctype==ClaimType.MEMBERSHIP:
        add(RequirementType.OFFICIAL_MEMBERSHIP_RECORD,True);add(RequirementType.PRIMARY_DOCUMENT)
    elif ctype==ClaimType.CONSTITUTIONAL:add(RequirementType.CONSTITUTIONAL_TEXT,True)
    elif ctype==ClaimType.LEGAL:add(RequirementType.LAW_TEXT,True)
    elif ctype==ClaimType.QUOTE:add(RequirementType.ORIGINAL_TRANSCRIPT,True)
    else:add(RequirementType.INDEPENDENT_CORROBORATION)
    if current:
        add(RequirementType.RECENT_AUTHORITATIVE_RECORD,True);add(RequirementType.REPLACEMENT_SEARCH)
    if negative:
        add(RequirementType.BROAD_ARCHIVE_SEARCH,True);add(RequirementType.ABSENCE_LIMITATIONS,True)
    return req


def analyze_claims(text:str,*,reference_date:datetime|None=None,registry:EntityAliasRegistry|None=None,decomposer:ClaimDecomposer|None=None,allow_model_decomposition:bool=False)->list[Claim]:
    normalized=normalize_text(text);intent=classify_intent(normalized)
    if allow_model_decomposition and decomposer and complexity_score(normalized)>=4:
        try:parts=[normalize_text(x) for x in decomposer.decompose(normalized) if normalize_text(x)][:8]
        except Exception:parts=_split_atomic(normalized)
    else:parts=_split_atomic(normalized)
    ref=reference_date or datetime.now(timezone.utc);claims=[];registry=registry or EntityAliasRegistry()
    for idx,part in enumerate(parts,1):
        local_intent=classify_intent(part)
        ctype=classify_claim_type(part,local_intent if local_intent!=Intent.FACT_CHECK else intent)
        negative=any(x in part.casefold() for x in _NEGATIVE)
        current=any(x in part.casefold() for x in _CURRENT) or ctype==ClaimType.CURRENT_STATUS
        refs=extract_entities(part,registry);dinfo=parse_date_text(part,ref);req=_requirements(ctype,f"C{idx}",negative,current)
        claim=Claim(
            claim_id=f"C{idx}",original_text=text,normalized_text=normalized,atomic_text=part,
            claim_type=ctype,intent=local_intent if local_intent!=Intent.FACT_CHECK else intent,
            entities=[r.canonical_name for r in refs],entity_refs=refs,
            dates=[d.raw_text for d in dinfo],date_info=dinfo,
            required_evidence=[x.requirement_type.value for x in req],evidence_requirements=req,
            is_negative=negative,high_impact=any(x in part.casefold() for x in _HIGH_IMPACT),
            current_status=current,breaking_news=any(x in part.casefold() for x in _BREAKING),
            quoted_texts=extract_quoted_phrases(part),reference_date=ref.isoformat(),
        )
        if idx>1 and any(x in normalized for x in ("بنابراین","در نتیجه","به همین دلیل")):claim.dependencies=[c.claim_id for c in claims]
        claims.append(claim)
    return claims


def _search_core_text(text:str)->str:
    value=normalize_text(text).strip(" ؟?!.،,")
    for pattern in _FILLER_PREFIXES:value=re.sub(pattern,"",value,flags=re.I).strip()
    for pattern in _FILLER_SUFFIXES:value=re.sub(pattern,"",value,flags=re.I).strip()
    value=re.sub(r"\b(?:بررسی کن|صحت سنجی کن|صحت‌سنجی کن|فکت چک کن|فکت‌چک کن)\b"," ",value,flags=re.I)
    value=re.sub(r"\s+"," ",value).strip()
    return value[:290]


def _query_candidates(claim:Claim,registry:EntityAliasRegistry)->list[SearchQuery]:
    q=_search_core_text(claim.atomic_text) or claim.atomic_text[:290];items=[]
    people=[r.canonical_name for r in claim.entity_refs if r.entity_type=="person"]
    focus=" ".join(dict.fromkeys(people[:2])) or q
    def add(text:str,purpose:str,priority:int)->None:
        text=normalize_text(text)[:350]
        if text:items.append(SearchQuery(text,purpose,claim.claim_id,priority))
    if claim.is_negative:add(f'{focus} {q[:180]} حکم سند آرشیو انتصاب',"negative_existence",5)
    elif claim.claim_type in {ClaimType.APPOINTMENT,ClaimType.MEMBERSHIP}:add(f'{focus} {q[:180]} "حکم" "انتصاب"',"primary",5)
    elif claim.claim_type in {ClaimType.LEGAL,ClaimType.CONSTITUTIONAL}:add(f'{q[:220]} "متن قانون" "اصل"',"primary",5)
    elif claim.claim_type==ClaimType.QUOTE:
        quoted=" ".join(f'"{x[:120]}"' for x in claim.quoted_texts[:1])
        add(f'{focus} {quoted or q[:180]} متن کامل ویدئو رونوشت',"primary",5)
    elif claim.current_status:add(f'{focus} {q[:180]} جدیدترین فعلی',"freshness",5)
    else:add(q,"neutral",10)
    add(q,"neutral",20)
    if claim.current_status or claim.claim_type in {ClaimType.APPOINTMENT,ClaimType.MEMBERSHIP}:add(f'{focus} جایگزین عزل استعفا تمدید',"replacement",25)
    add(f'{focus} {q[:170]} تکذیب نادرست خلاف',"challenge",30)
    add(f'{focus} {q[:170]} تایید تأیید سند',"support",40)
    if claim.is_negative:add(f'{focus} آرشیو فهرست اعضا سوابق',"archive",15)
    variants=[]
    for ref in claim.entity_refs[:3]:variants.extend(registry.variants(ref.canonical_name))
    latin=[v for v in variants if any("a"<=c.lower()<="z" for c in v)]
    if latin:add(f'{" ".join(latin[:2])} {q[:160]}',"transliteration",45)
    return items


def plan_queries(claims:list[Claim],limit:int,registry:EntityAliasRegistry|None=None)->list[SearchQuery]:
    registry=registry or EntityAliasRegistry()
    if limit<=0:return []
    per={c.claim_id:_query_candidates(c,registry) for c in claims};selected=[];seen=set()
    priority_types={ClaimType.APPOINTMENT,ClaimType.MEMBERSHIP,ClaimType.LEGAL,ClaimType.CONSTITUTIONAL,ClaimType.QUOTE}
    for claim in sorted(claims,key=lambda c:(not(c.high_impact or c.is_negative or c.current_status or c.claim_type in priority_types),c.claim_id)):
        if not per[claim.claim_id]:continue
        item=min(per[claim.claim_id],key=lambda x:x.priority);key=normalize_text(item.text).casefold()
        if key not in seen:selected.append(item);seen.add(key)
        if len(selected)>=limit:return selected
    remaining=[item for items in per.values() for item in items]
    for item in sorted(remaining,key=lambda x:(x.priority,x.claim_id or "")):
        key=normalize_text(item.text).casefold()
        if key in seen:continue
        selected.append(item);seen.add(key)
        if len(selected)>=limit:break
    return selected


def coverage_template(claims:Sequence[Claim],planned:Sequence[SearchQuery])->list[ClaimResearchCoverage]:
    by=defaultdict(list)
    for q in planned:
        if q.claim_id:by[q.claim_id].append(q.purpose)
    return [ClaimResearchCoverage(
        claim_id=c.claim_id,planned_purposes=list(by[c.claim_id]),
        primary_search_attempted="primary" in by[c.claim_id],challenge_search_attempted="challenge" in by[c.claim_id],
        archive_search_attempted=any(p in {"archive","negative_existence"} for p in by[c.claim_id]),
        replacement_search_attempted="replacement" in by[c.claim_id],query_count=len(by[c.claim_id]),
    ) for c in claims]


def finalize_coverage(coverage:list[ClaimResearchCoverage],claims:Sequence[Claim])->list[ClaimResearchCoverage]:
    cmap={c.claim_id:c for c in claims}
    for cov in coverage:
        c=cmap[cov.claim_id];desired={"neutral"}
        if c.claim_type in {ClaimType.APPOINTMENT,ClaimType.MEMBERSHIP,ClaimType.LEGAL,ClaimType.CONSTITUTIONAL,ClaimType.QUOTE}:desired.add("primary")
        if c.is_negative:desired.add("negative_existence")
        if c.current_status:desired.add("replacement")
        if c.high_impact:desired.add("challenge")
        have=set(cov.successful_purposes)
        if "negative_existence" in desired and "archive" in have:have.add("negative_existence")
        cov.coverage_score=round(len(desired&have)/max(1,len(desired)),3)
    return coverage
