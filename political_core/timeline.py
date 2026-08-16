from __future__ import annotations
import re
from collections.abc import Sequence
from .models import Claim,Evidence,TimelineEvent
from .text import normalize_text
_EVENTS=[("انتصاب","appointment"),("منصوب","appointment"),("تمدید","renewal"),("عزل","dismissal"),("استعفا","resignation"),("جایگزین","replacement"),("درگذشت","death"),("انتخاب شد","election")]
_ROLE_WORDS=("دبیر","نماینده","رئیس","رییس","وزیر","معاون","فرمانده","مشاور","عضو")
def _role(text:str)->str:
    t=normalize_text(text)
    for word in _ROLE_WORDS:
        m=re.search(rf"({word}\s+[\u0600-\u06ff]+(?:\s+[\u0600-\u06ff]+){{0,5}})",t)
        if m:return m.group(1)
    return ""
def build_timeline(claims:Sequence[Claim],evidence:Sequence[Evidence])->list[TimelineEvent]:
    if not any(c.claim_type.value in {"appointment","membership","timeline","current_status"} for c in claims): return []
    events=[]
    for e in evidence:
        text=normalize_text(f"{e.title} {e.excerpt[:1200]}"); etype=None
        for token,label in _EVENTS:
            if token in text: etype=label;break
        if not etype: continue
        entity="";entity_id=None
        for c in claims:
            for ref in c.entity_refs:
                if ref.entity_type=="person" and (ref.surface in text or ref.canonical_name in text): entity=ref.canonical_name;entity_id=ref.entity_id;break
            if entity: break
        role=_role(text); date=e.event_date or e.published_at or e.updated_at
        if not date: continue
        institution=""
        for c in claims:
            for ref in c.entity_refs:
                if ref.entity_type=="organization" and (ref.surface in text or ref.canonical_name in text): institution=ref.canonical_name;break
            if institution: break
        events.append(TimelineEvent(entity,role,etype,entity_id,institution or None,date,None,e.event_date,e.published_at,[e.evidence_id],min(.96,e.quality_score)))
    events.sort(key=lambda x:x.start_date or ""); return events[:30]
def derive_current_roles(events:Sequence[TimelineEvent])->dict[str,list[TimelineEvent]]:
    active={}
    for ev in events:
        key=ev.entity_id or ev.entity or "unknown";active.setdefault(key,[])
        if ev.event_type in {"dismissal","resignation","death","replacement"}:
            for old in active[key]:
                if not old.end_date and (not ev.role or not old.role or ev.role==old.role): old.end_date=ev.start_date
        elif ev.event_type in {"appointment","renewal","election"}: active[key].append(ev)
    return active
