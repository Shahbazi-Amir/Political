from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .models import Claim, ClaimType, DateInfo, Evidence
from .text import normalize_text

_PERSIAN_MONTHS={"فروردین":1,"اردیبهشت":2,"خرداد":3,"تیر":4,"مرداد":5,"شهریور":6,"مهر":7,"آبان":8,"آذر":9,"دی":10,"بهمن":11,"اسفند":12}
_JALALI_BREAKS=(-61,9,38,199,426,686,756,818,1111,1181,1210,1635,2060,2097,2192,2262,2324,2394,2456,3178)


def _gregorian_leap(y:int)->bool:
    return y%4==0 and (y%100!=0 or y%400==0)


def _jalali_cal(jy:int)->tuple[int,int,int]:
    if jy < _JALALI_BREAKS[0] or jy >= _JALALI_BREAKS[-1]:
        raise ValueError("Jalali year out of supported range")
    gy=jy+621; leap_j=-14; jp=_JALALI_BREAKS[0]; jump=0
    for jm in _JALALI_BREAKS[1:]:
        jump=jm-jp
        if jy<jm: break
        leap_j+=(jump//33)*8+((jump%33)//4); jp=jm
    n=jy-jp
    leap_j+=(n//33)*8+(((n%33)+3)//4)
    if jump%33==4 and jump-n==4: leap_j+=1
    leap_g=gy//4-((gy//100+1)*3)//4-150
    march=20+leap_j-leap_g
    if jump-n<6: n=n-jump+((jump+4)//33)*33
    leap=((n+1)%33-1)%4
    return leap,gy,march


def jalali_is_leap(jy:int)->bool:
    leap,_,_=_jalali_cal(jy)
    return leap==0


def _validate_jalali(jy:int,jm:int,jd:int)->None:
    if not (1<=jy<=3000 and 1<=jm<=12 and jd>=1): raise ValueError("invalid Jalali date")
    if jm<=6: max_day=31
    elif jm<=11: max_day=30
    else: max_day=30 if jalali_is_leap(jy) else 29
    if jd>max_day: raise ValueError("invalid Jalali day for month")


def jalali_to_gregorian(jy:int,jm:int,jd:int)->tuple[int,int,int]:
    _validate_jalali(jy,jm,jd)
    jy2=jy+1595
    days=-355668+365*jy2+(jy2//33)*8+((jy2%33+3)//4)+jd
    days+=(jm-1)*31 if jm<7 else (jm-7)*30+186
    gy=400*(days//146097);days%=146097
    if days>36524:
        gy+=100*((days-1)//36524);days=(days-1)%36524
        if days>=365:days+=1
    gy+=4*(days//1461);days%=1461
    if days>365:gy+=(days-1)//365;days=(days-1)%365
    gd=days+1;months=[0,31,29 if _gregorian_leap(gy) else 28,31,30,31,30,31,31,30,31,30,31];gm=1
    while gm<=12 and gd>months[gm]:gd-=months[gm];gm+=1
    return gy,gm,gd


def _iso(dt:datetime)->str:
    if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def parse_date_text(text:str,reference:datetime|None=None,source:str="claim")->list[DateInfo]:
    t=normalize_text(text);ref=reference or datetime.now(timezone.utc);out=[]
    relatives=[("همین الان",ref,.98,"minute"),("اکنون",ref,.95,"minute"),("امروز",ref,.95,"day"),("دیروز",ref-timedelta(days=1),.95,"day"),("فردا",ref+timedelta(days=1),.95,"day")]
    for phrase,dt,conf,precision in relatives:
        if phrase in t:out.append(DateInfo(phrase,_iso(dt),"relative",precision,source,conf))
    for m in re.finditer(r"(\d+)\s+(?:دقیقه|دقایق)\s+پیش",t):out.append(DateInfo(m.group(0),_iso(ref-timedelta(minutes=int(m.group(1)))),"relative","minute",source,.85))
    for m in re.finditer(r"(\d+)\s+(?:ساعت|ساعتی)\s+پیش",t):out.append(DateInfo(m.group(0),_iso(ref-timedelta(hours=int(m.group(1)))),"relative","hour",source,.85))
    for m in re.finditer(r"\b((?:13|14|19|20)\d{2})[/-](\d{1,2})[/-](\d{1,2})\b",t):
        y,mo,d=map(int,m.groups())
        try:
            if 1300<=y<1500:gy,gm,gd=jalali_to_gregorian(y,mo,d);dt=datetime(gy,gm,gd,tzinfo=timezone.utc);cal="jalali"
            else:dt=datetime(y,mo,d,tzinfo=timezone.utc);cal="gregorian"
            out.append(DateInfo(m.group(0),_iso(dt),cal,"day",source,.98))
        except ValueError:pass
    month_names="|".join(_PERSIAN_MONTHS)
    for m in re.finditer(rf"\b(\d{{1,2}})\s+({month_names})\s+((?:13|14)\d{{2}})\b",t):
        d=int(m.group(1));mo=_PERSIAN_MONTHS[m.group(2)];y=int(m.group(3))
        try:
            gy,gm,gd=jalali_to_gregorian(y,mo,d);out.append(DateInfo(m.group(0),_iso(datetime(gy,gm,gd,tzinfo=timezone.utc)),"jalali","day",source,.99))
        except ValueError:pass
    for m in re.finditer(r"\b((?:13|14|19|20)\d{2})\b",t):
        if any(m.group(0) in x.raw_text and x.raw_text!=m.group(0) for x in out):continue
        y=int(m.group(1))
        try:
            if 1300<=y<1500:gy,gm,gd=jalali_to_gregorian(y,1,1);dt=datetime(gy,gm,gd,tzinfo=timezone.utc);cal="jalali"
            else:dt=datetime(y,1,1,tzinfo=timezone.utc);cal="gregorian"
            out.append(DateInfo(m.group(0),_iso(dt),cal,"year",source,.75))
        except ValueError:pass
    # Keep deterministic order and avoid duplicate detections of the same span/text.
    seen=set();unique=[]
    for item in out:
        key=(item.raw_text,item.parsed_datetime,item.precision)
        if key not in seen:seen.add(key);unique.append(item)
    return unique


@dataclass(slots=True)
class FreshnessPolicy:
    breaking_hours:int=24
    current_office_days:int=14
    election_days:int=3
    current_event_days:int=7
    appointment_days:int=120
    generic_days:int=180
    legal_days:int=365
    stable_days:int=3650
    future_tolerance_hours:int=24

    def target_seconds(self,claims:Iterable[Claim])->int:
        claims=list(claims)
        if any(c.breaking_news for c in claims):return self.breaking_hours*3600
        if any(c.current_status for c in claims):return self.current_office_days*86400
        if any("انتخابات" in c.atomic_text for c in claims):return self.election_days*86400
        if any(c.claim_type in {ClaimType.CONSTITUTIONAL,ClaimType.LEGAL} for c in claims):return self.legal_days*86400
        if any(c.claim_type==ClaimType.APPOINTMENT for c in claims):return self.appointment_days*86400
        if any(c.high_impact for c in claims):return self.current_event_days*86400
        return self.generic_days*86400

    def evidence_is_stale(self,evidence:Evidence,claims:Iterable[Claim],now:datetime|None=None)->bool:
        claims=list(claims)
        if now is None:
            ref=next((c.reference_date for c in claims if c.reference_date),None)
            if ref:
                try:now=datetime.fromisoformat(ref.replace("Z","+00:00"))
                except ValueError:now=None
        now=now or datetime.now(timezone.utc)
        raw=evidence.updated_at or evidence.event_date or evidence.published_at
        if not raw:return any(c.current_status or c.breaking_news for c in claims)
        dt=None
        try:dt=datetime.fromisoformat(raw.replace("Z","+00:00"))
        except ValueError:
            parsed=parse_date_text(raw,now,source="evidence")
            if parsed and parsed[0].parsed_datetime:dt=datetime.fromisoformat(parsed[0].parsed_datetime)
        if dt is None:return any(c.current_status or c.breaking_news for c in claims)
        if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
        age=(now-dt).total_seconds()
        # Materially future-dated evidence is anomalous for a present/past claim.
        if age < -self.future_tolerance_hours*3600:return True
        return age>self.target_seconds(claims)
