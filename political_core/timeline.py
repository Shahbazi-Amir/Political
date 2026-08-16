from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime,timezone

from .models import Claim,Evidence,TimelineEvent
from .temporal import parse_date_text
from .text import normalize_text

_EVENTS=[
    ("برکنار","dismissal"),("عزل","dismissal"),("استعفا","resignation"),("درگذشت","death"),
    ("جایگزین","replacement"),("تمدید","renewal"),("انتصاب","appointment"),("منصوب","appointment"),
    ("انتخاب شد","election"),
]
_ROLE_WORDS=("دبیر","نماینده","رئیس","رییس","وزیر","معاون","فرمانده","مشاور","عضو")
_CANONICAL_ROLE_PATTERNS=(
    (r"دبیر\s+شورای\s+عالی\s+امنیت\s+ملی","دبیر شورای عالی امنیت ملی"),
    (r"نماینده(?:\s+\S+){0,4}\s+در\s+شورای\s+عالی\s+امنیت\s+ملی","نماینده در شورای عالی امنیت ملی"),
    (r"نمایندگی(?:\s+\S+){0,4}\s+در\s+شورای\s+عالی\s+امنیت\s+ملی","نماینده در شورای عالی امنیت ملی"),
)


def _role(text:str)->str:
    t=normalize_text(text)
    for pattern,label in _CANONICAL_ROLE_PATTERNS:
        if re.search(pattern,t):return label
    for word in _ROLE_WORDS:
        m=re.search(rf"({word}\s+[\u0600-\u06ff]+(?:\s+[\u0600-\u06ff]+){{0,5}})",t)
        if m:return m.group(1)
    return ""


def _sort_date(raw:str|None)->datetime:
    if not raw:return datetime.max.replace(tzinfo=timezone.utc)
    try:
        dt=datetime.fromisoformat(raw.replace("Z","+00:00"));return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        parsed=parse_date_text(raw)
        if parsed and parsed[0].parsed_datetime:
            return datetime.fromisoformat(parsed[0].parsed_datetime)
    return datetime.max.replace(tzinfo=timezone.utc)


def _same_role(a:TimelineEvent,b:TimelineEvent)->bool:
    role_match=not a.role or not b.role or a.role==b.role
    institution_match=not a.institution or not b.institution or a.institution==b.institution
    return role_match and institution_match


def build_timeline(claims:Sequence[Claim],evidence:Sequence[Evidence])->list[TimelineEvent]:
    if not any(c.claim_type.value in {"appointment","membership","timeline","current_status"} for c in claims):return []
    events=[]
    for e in evidence:
        text=normalize_text(f"{e.title} {e.excerpt[:1600]}");etype=None
        for token,label in _EVENTS:
            if token in text:etype=label;break
        if not etype:continue
        target_claims=[c for c in claims if not e.retrieval_claim_ids or c.claim_id in e.retrieval_claim_ids]
        entity="";entity_id=None
        for c in target_claims:
            for ref in c.entity_refs:
                if ref.entity_type=="person" and (normalize_text(ref.surface) in text or normalize_text(ref.canonical_name) in text):
                    entity=ref.canonical_name;entity_id=ref.entity_id;break
            if entity:break
        role=_role(text);date=e.event_date or e.published_at or e.updated_at
        if not date:continue
        institution=""
        for c in target_claims:
            for ref in c.entity_refs:
                if ref.entity_type in {"organization","institution"} and (normalize_text(ref.surface) in text or normalize_text(ref.canonical_name) in text):
                    institution=ref.canonical_name;break
            if institution:break
        events.append(TimelineEvent(entity,role,etype,entity_id,institution or None,date,None,e.event_date,e.published_at,[e.evidence_id],min(.96,e.quality_score)))

    merged={}
    for ev in events:
        key=(ev.entity_id or ev.entity,ev.role,ev.event_type,ev.start_date,ev.institution)
        old=merged.get(key)
        if old is None:
            merged[key]=ev
        else:
            old.evidence_ids=list(dict.fromkeys(old.evidence_ids+ev.evidence_ids))
            old.confidence=max(old.confidence,ev.confidence)
    out=list(merged.values());out.sort(key=lambda x:_sort_date(x.start_date));return out[:40]


def derive_current_roles(events:Sequence[TimelineEvent])->dict[str,list[TimelineEvent]]:
    active={}
    for ev in sorted(events,key=lambda x:_sort_date(x.start_date)):
        key=ev.entity_id or ev.entity or "unknown";active.setdefault(key,[])
        if ev.event_type in {"dismissal","resignation","death"}:
            for old in active[key]:
                if not old.end_date and _same_role(old,ev):old.end_date=ev.start_date
        elif ev.event_type=="replacement":
            for rows in active.values():
                for old in rows:
                    if not old.end_date and _same_role(old,ev):old.end_date=ev.start_date
        elif ev.event_type in {"appointment","renewal","election"}:
            for old in active[key]:
                if not old.end_date and _same_role(old,ev):old.end_date=ev.start_date
            active[key].append(ev)
    return active


def active_role_events(events:Sequence[TimelineEvent])->list[TimelineEvent]:
    roles=derive_current_roles(events)
    out=[event for rows in roles.values() for event in rows if not event.end_date]
    return sorted(out,key=lambda x:(x.institution or "",x.role,x.entity))
