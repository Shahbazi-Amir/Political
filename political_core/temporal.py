from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .models import Claim, ClaimType, DateInfo, Evidence
from .text import normalize_text

_PERSIAN_MONTHS={"فروردین":1,"اردیبهشت":2,"خرداد":3,"تیر":4,"مرداد":5,"شهریور":6,"مهر":7,"آبان":8,"آذر":9,"دی":10,"بهمن":11,"اسفند":12}

def _gregorian_leap(y:int)->bool: return y%4==0 and (y%100!=0 or y%400==0)
def jalali_to_gregorian(jy:int,jm:int,jd:int)->tuple[int,int,int]:
    if not (1<=jm<=12 and 1<=jd<=31 and 1<=jy<=3000): raise ValueError("invalid Jalali date")
    jy += 1595; days = -355668 + 365*jy + (jy//33)*8 + ((jy%33+3)//4) + jd
    days += (jm-1)*31 if jm<7 else (jm-7)*30 + 186
    gy = 400*(days//146097); days %= 146097
    if days > 36524:
        gy += 100*((days-1)//36524); days = (days-1)%36524
        if days >= 365: days += 1
    gy += 4*(days//1461); days %= 1461
    if days > 365: gy += (days-1)//365; days = (days-1)%365
    gd=days+1; months=[0,31,29 if _gregorian_leap(gy) else 28,31,30,31,30,31,31,30,31,30,31]; gm=1
    while gm<=12 and gd>months[gm]: gd-=months[gm];gm+=1
    return gy,gm,gd

def _iso(dt:datetime)->str:
    if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()

def parse_date_text(text:str, reference:datetime|None=None, source:str="claim")->list[DateInfo]:
    t=normalize_text(text); ref=reference or datetime.now(timezone.utc); out=[]
    for phrase,dt,conf in [("همین الان",ref,.95),("اکنون",ref,.9),("امروز",ref,.95),("دیروز",ref-timedelta(days=1),.95),("فردا",ref+timedelta(days=1),.95)]:
        if phrase in t: out.append(DateInfo(phrase,_iso(dt),"relative","day",source,conf))
    m=re.search(r"(\d+)\s+(?:دقیقه|دقایق)\s+پیش",t)
    if m: out.append(DateInfo(m.group(0),_iso(ref-timedelta(minutes=int(m.group(1)))),"relative","minute",source,.8))
    m=re.search(r"(\d+)\s+(?:ساعت|ساعتی)\s+پیش",t)
    if m: out.append(DateInfo(m.group(0),_iso(ref-timedelta(hours=int(m.group(1)))),"relative","hour",source,.8))
    for m in re.finditer(r"\b((?:13|14|19|20)\d{2})[/-](\d{1,2})[/-](\d{1,2})\b",t):
        y,mo,d=map(int,m.groups())
        try:
            if 1300<=y<1500: gy,gm,gd=jalali_to_gregorian(y,mo,d);dt=datetime(gy,gm,gd,tzinfo=timezone.utc);cal="jalali"
            else: dt=datetime(y,mo,d,tzinfo=timezone.utc);cal="gregorian"
            out.append(DateInfo(m.group(0),_iso(dt),cal,"day",source,.98))
        except ValueError: pass
    month_names="|".join(_PERSIAN_MONTHS)
    for m in re.finditer(rf"\b(\d{{1,2}})\s+({month_names})\s+((?:13|14)\d{{2}})\b",t):
        d=int(m.group(1));mo=_PERSIAN_MONTHS[m.group(2)];y=int(m.group(3))
        try:
            gy,gm,gd=jalali_to_gregorian(y,mo,d);out.append(DateInfo(m.group(0),_iso(datetime(gy,gm,gd,tzinfo=timezone.utc)),"jalali","day",source,.99))
        except ValueError: pass
    for m in re.finditer(r"\b((?:13|14|19|20)\d{2})\b",t):
        if any(m.group(0) in x.raw_text and x.raw_text!=m.group(0) for x in out): continue
        y=int(m.group(1))
        if 1300<=y<1500: gy,_,_=jalali_to_gregorian(y,1,1);dt=datetime(gy,3,21,tzinfo=timezone.utc);cal="jalali"
        else: dt=datetime(y,1,1,tzinfo=timezone.utc);cal="gregorian"
        out.append(DateInfo(m.group(0),_iso(dt),cal,"year",source,.75))
    return out

@dataclass(slots=True)
class FreshnessPolicy:
    breaking_hours:int=24; current_office_days:int=14; election_days:int=3; current_event_days:int=7; appointment_days:int=120; generic_days:int=180; legal_days:int=365; stable_days:int=3650
    def target_seconds(self,claims:Iterable[Claim])->int:
        claims=list(claims)
        if any(c.breaking_news for c in claims): return self.breaking_hours*3600
        if any(c.current_status for c in claims): return self.current_office_days*86400
        if any("انتخابات" in c.atomic_text for c in claims): return self.election_days*86400
        if any(c.claim_type in {ClaimType.CONSTITUTIONAL,ClaimType.LEGAL} for c in claims): return self.legal_days*86400
        if any(c.claim_type==ClaimType.APPOINTMENT for c in claims): return self.appointment_days*86400
        if any(c.high_impact for c in claims): return self.current_event_days*86400
        return self.generic_days*86400
    def evidence_is_stale(self,evidence:Evidence,claims:Iterable[Claim],now:datetime|None=None)->bool:
        claims=list(claims)
        if now is None:
            ref=next((c.reference_date for c in claims if c.reference_date),None)
            if ref:
                try: now=datetime.fromisoformat(ref.replace("Z","+00:00"))
                except ValueError: now=None
        now=now or datetime.now(timezone.utc)
        raw=evidence.updated_at or evidence.published_at or evidence.event_date
        if not raw: return any(c.current_status or c.breaking_news for c in claims)
        dt=None
        try: dt=datetime.fromisoformat(raw.replace("Z","+00:00"))
        except ValueError:
            parsed=parse_date_text(raw,now,source="evidence")
            if parsed and parsed[0].parsed_datetime: dt=datetime.fromisoformat(parsed[0].parsed_datetime)
        if dt is None: return any(c.current_status or c.breaking_news for c in claims)
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        return (now-dt).total_seconds()>self.target_seconds(claims)
