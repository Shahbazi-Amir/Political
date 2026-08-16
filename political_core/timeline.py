from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime,timezone

from .models import Claim,Evidence,TimelineEvent
from .temporal import parse_date_text
from .text import normalize_text

_EVENTS=[("انتصاب","appointment"),("منصوب","appointment"),("تمدید","renewal"),("عزل","dismissal"),("استعفا","resignation"),("جایگزین","replacement"),("درگذشت","death"),("انتخاب شد","election")]
_ROLE_WORDS=("دبیر","نماینده","رئیس","رییس","وزیر","معاون","فرمانده","مشاور","عضو")


def _role(text:str)->str:
    t=normalize_text(text)
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


def build_timeline(claims:Sequence[Claim],evidence:Sequence[Evidence])->list[TimelineEvent]:
    if not any(c.claim_type.value in {"appointment","membership","timeline","current_status"} for c in claims):return []
    events=[]
    for e in evidence:
        text=normalize_text(f"{e.title} {e.excerpt[:1200]}");etype=None
        for token,label in _EVENTS:
            if token in text:etype=label;break
        if not etype:continue
        target_claims=[c for c in claims if not e.retrieval_claim_ids or c.claim_id in e.retrieval_claim_ids]
        entity="";entity_id=None
        for c in target_claims:
            for ref in c.entity_refs:
                if ref.entity_type=="person" and (ref.surface in text or ref.canonical_name in text):entity=ref.canonical_name;entity_id=ref.entity_id;break
            if entity:break
        role=_role(text);date=e.event_date or e.published_at or e.updated_at
        if not date:continue
        institution=""
        for c in target_claims:
            for ref in c.entity_refs:
                if ref.entity_type=="organization" and (ref.surface in text or ref.canonical_name in text):institution=ref.canonical_name;break
            if institution:break
        events.append(TimelineEvent(entity,role,etype,entity_id,institution or None,date,None,e.event_date,e.published_at,[e.evidence_id],min(.96,e.quality_score)))
    events.sort(key=lambda x:_sort_date(x.start_date));return events[:30]


def derive_current_roles(events:Sequence[TimelineEvent])->dict[str,list[TimelineEvent]]:
    active={}
    for ev in sorted(events,key=lambda x:_sort_date(x.start_date)):
        key=ev.entity_id or ev.entity or "unknown";active.setdefault(key,[])
        if ev.event_type in {"dismissal","resignation","death"}:
            for old in active[key]:
                if not old.end_date and (not ev.role or not old.role or ev.role==old.role):old.end_date=ev.start_date
        elif ev.event_type=="replacement":
            # When role/institution are known, replacement closes that role globally;
            # this handles a new person's event replacing a predecessor.
            for rows in active.values():
                for old in rows:
                    role_match=not ev.role or not old.role or ev.role==old.role
                    inst_match=not ev.institution or not old.institution or ev.institution==old.institution
                    if not old.end_date and role_match and inst_match:old.end_date=ev.start_date
        elif ev.event_type in {"appointment","renewal","election"}:
            if ev.event_type=="renewal":
                for old in active[key]:
                    if not old.end_date and (not ev.role or not old.role or ev.role==old.role):old.end_date=ev.start_date
            active[key].append(ev)
    return active
