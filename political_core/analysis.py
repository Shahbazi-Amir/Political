from __future__ import annotations
import re
from .text import normalize_text,token_set
def extract_quoted_phrases(text:str)->list[str]:
    out=[]
    for a,b in re.findall(r"«([^»]{2,500})»|\"([^\"]{2,500})\"",text or ""):
        q=(a or b).strip()
        if q and q not in out:out.append(q)
    return out[:12]
def analyze_argument(text:str)->dict:
    t=normalize_text(text);causal=any(x in t for x in ("چون","به دلیل","باعث","سبب","بنابراین","در نتیجه","پس "))
    conclusion=None;parts=re.split(r"\s+(?:بنابراین|در نتیجه|پس)\s+",t,maxsplit=1)
    if len(parts)==2:conclusion=parts[1]
    return {"argument_detected":causal,"conclusion":conclusion,"signals":{"causal_language":any(x in t for x in ("چون","به دلیل","باعث","سبب")),"conclusion_language":any(x in t for x in ("بنابراین","در نتیجه","پس ")),"absolute_language":any(x in t for x in ("همیشه","هرگز","قطعاً","قطعا","بدون شک"))}}
def analyze_framing(text:str)->dict:
    t=normalize_text(text);loaded=("خیانت","رسوایی","شکست مفتضحانه","پیروزی قاطع","عقب نشینی","عقب‌نشینی","دیکتاتور","تروریست","قهرمان")
    found=[x for x in loaded if x in t];return {"loaded_terms":found,"framing_detected":bool(found)}
def quoted_phrase_similarity(a:str,b:str)->float:
    aa,bb=token_set(a),token_set(b)
    return len(aa&bb)/len(aa|bb) if aa and bb else 0.0
