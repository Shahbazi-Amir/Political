from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass,field

from .models import EntityRef
from .text import normalize_text,normalized_key,transliterate_fa

_DEFAULT_ALIASES={
    "شورای عالی امنیت ملی":{"شعام","شورای عالی امنیت ملی","شورای امنیت ملی ایران","SNSC"},
    "قانون اساسی جمهوری اسلامی ایران":{"قانون اساسی","قانون اساسی جمهوری اسلامی ایران","Constitution of Iran"},
    "ریاست جمهوری ایران":{"ریاست جمهوری","ریاست‌جمهوری","نهاد ریاست جمهوری"},
    "مجلس شورای اسلامی":{"مجلس","مجلس شورای اسلامی","Islamic Consultative Assembly"},
    "ایران":{"ایران","جمهوری اسلامی ایران","Iran"},
    "محمدباقر ذوالقدر":{"محمد باقر ذوالقدر","محمدباقر ذوالقدر","Mohammad Bagher Zolghadr","Zolghadr","Zolqadr"},
    "سعید جلیلی":{"سعید جلیلی","Saeed Jalili","Jalili"},"علی شمخانی":{"علی شمخانی","Ali Shamkhani","Shamkhani"},
    "علی لاریجانی":{"علی لاریجانی","Ali Larijani","Larijani"},"محسن رضایی":{"محسن رضایی","Mohsen Rezaei","Mohsen Rezai","Rezaei","Rezai"},
    "علی‌اکبر احمدیان":{"علی اکبر احمدیان","علی‌اکبر احمدیان","Ali Akbar Ahmadian","Ahmadian"},
}
_DEFAULT_TYPES={
    "شورای عالی امنیت ملی":"organization","قانون اساسی جمهوری اسلامی ایران":"law","ریاست جمهوری ایران":"organization",
    "مجلس شورای اسلامی":"institution","ایران":"country","محمدباقر ذوالقدر":"person","سعید جلیلی":"person","علی شمخانی":"person",
    "علی لاریجانی":"person","محسن رضایی":"person","علی‌اکبر احمدیان":"person",
}
_ORG_HINTS=("شورا","وزارت","مجلس","دولت","ارتش","سپاه","دادگاه","سازمان","حزب","دفتر","ریاست جمهوری","خبرگزاری")
_OFFICE_HINTS=("رئیس","رییس","دبیر","نماینده","وزیر","معاون","فرمانده","سخنگو","مشاور","عضو")
_PERSON_PREFIXES=("آقای","خانم","دکتر","سردار","آیت الله","آیت‌الله","حجت الاسلام","حجت‌الاسلام")
_LOCATION_NAMES={"تهران","قم","مشهد","شیراز","تبریز","اصفهان","اهواز","باکو","واشنگتن","نیویورک"}

@dataclass(slots=True)
class EntityAliasRegistry:
    aliases:dict[str,set[str]]=field(default_factory=lambda:{k:set(v) for k,v in _DEFAULT_ALIASES.items()});entity_types:dict[str,str]=field(default_factory=lambda:dict(_DEFAULT_TYPES))
    def add(self,canonical:str,*aliases:str,entity_type:str|None=None)->None:
        canonical=normalize_text(canonical);self.aliases.setdefault(canonical,set()).update(normalize_text(x) for x in aliases if x)
        if entity_type:self.entity_types[canonical]=entity_type
    def canonicalize(self,text:str)->str:
        key=normalized_key(text)
        for canonical,aliases in self.aliases.items():
            if key==normalized_key(canonical) or any(key==normalized_key(alias) for alias in aliases):return canonical
        return normalize_text(text)
    def type_for(self,text:str,default:str="unknown")->str:return self.entity_types.get(self.canonicalize(text),default)
    def variants(self,text:str)->list[str]:
        canonical=self.canonicalize(text);out=[canonical]
        for can,aliases in self.aliases.items():
            if normalized_key(can)==normalized_key(canonical):out.extend(sorted(aliases))
        latin=transliterate_fa(canonical)
        if latin and latin.casefold()!=canonical.casefold():out.append(latin)
        seen=[];keys=set()
        for x in out:
            k=normalized_key(x)
            if x and k not in keys:keys.add(k);seen.append(x)
        return seen[:12]

def _entity_id(canonical:str,entity_type:str)->str:
    digest=hashlib.sha1(f"{entity_type}|{normalized_key(canonical)}".encode()).hexdigest()[:12];return f"{entity_type[:1].upper()}{digest}"

def _contains_alias(text:str,alias:str)->bool:
    hay=normalize_text(text);needle=normalize_text(alias)
    if not needle:return False
    # Treat Persian/Latin letters and digits as token characters. Plain substring matching
    # produced false entities such as Iran->Iranian and ایران->ایرانشهر.
    pattern=rf"(?<![\w\u0600-\u06ff]){re.escape(needle)}(?![\w\u0600-\u06ff])"
    return re.search(pattern,hay,flags=re.I) is not None

def extract_entities(text:str,registry:EntityAliasRegistry|None=None)->list[EntityRef]:
    registry=registry or EntityAliasRegistry();t=normalize_text(text);candidates=[]
    for q in re.findall(r"[«\"]([^»\"]{2,100})[»\"]",t):
        default="organization" if any(h in q for h in _ORG_HINTS) else "unknown";candidates.append((q,registry.type_for(q,default),.72))
    for canonical,aliases in registry.aliases.items():
        for alias in {canonical,*aliases}:
            if _contains_alias(t,alias):candidates.append((alias,registry.type_for(canonical,"organization"),.95))
    pref="|".join(map(re.escape,_PERSON_PREFIXES))
    for m in re.finditer(rf"(?:{pref})\s+([\u0600-\u06ff]+(?:\s+[\u0600-\u06ff]+){{1,3}})",t):candidates.append((m.group(1),"person",.9))
    role_pat="|".join(map(re.escape,_OFFICE_HINTS))
    for m in re.finditer(rf"([\u0600-\u06ff]{{2,}}(?:\s+[\u0600-\u06ff]{{2,}}){{1,3}})\s+(?={role_pat})",t):
        raw=m.group(1).strip()
        if not any(raw.endswith(h) for h in _ORG_HINTS):candidates.append((raw,"person",.72))
    for m in re.finditer(r"((?:شورای|وزارت|مجلس|سازمان|دفتر|دادگاه|ارتش|سپاه)\s+[\u0600-\u06ff]+(?:\s+[\u0600-\u06ff]+){0,5})",t):
        raw=m.group(1);candidates.append((raw,"institution" if raw.startswith("مجلس") else "organization",.78))
    for m in re.finditer(r"((?:رئیس|رییس|دبیر|نماینده|وزیر|معاون|فرمانده|سخنگو|مشاور)\s+[\u0600-\u06ff]+(?:\s+[\u0600-\u06ff]+){0,6})",t):candidates.append((m.group(1),"office",.7))
    for loc in _LOCATION_NAMES:
        if _contains_alias(t,loc):candidates.append((loc,"location",.8))
    out=[];seen=set()
    for surface,etype,conf in candidates:
        canonical=registry.canonicalize(surface);etype=registry.type_for(canonical,etype);key=(etype,normalized_key(canonical))
        if not canonical or key in seen:continue
        seen.add(key);out.append(EntityRef(_entity_id(canonical,etype),canonical,surface,etype,registry.variants(canonical),conf))
    return out[:24]
