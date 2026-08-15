from __future__ import annotations

import re

from .text import normalize_text

_CAUSAL = ("چون", "به دلیل", "بنابراین", "در نتیجه", "باعث", "سبب", "پس")
_AUTHORITY = ("چون رهبر", "چون رئیس", "چون کارشناس", "چون رسانه", "چون دولت", "چون مقام")
_LOADED = ("خیانت", "خائن", "رسوایی", "مفتضح", "فاجعه", "پیروزی قاطع", "شکست سنگین", "عقب نشینی", "عقب‌نشینی", "دروغگو", "دیکتاتور")


def analyze_argument(text: str) -> dict:
    t = normalize_text(text)
    segments = [x.strip() for x in re.split(r"[؛;]|\s+(?:بنابراین|در نتیجه|پس)\s+", t) if x.strip()]
    conclusion = segments[-1] if len(segments) > 1 else ""
    premises = segments[:-1] if len(segments) > 1 else []
    signals: list[str] = []
    if any(x in t for x in _CAUSAL): signals.append("causal_or_inference_marker")
    if any(x in t for x in _AUTHORITY): signals.append("authority_reliance_marker")
    if any(x in t for x in ("همه", "هیچکس", "همیشه", "هرگز")): signals.append("possible_overgeneralization_marker")
    if "یا" in t and any(x in t for x in ("فقط", "تنها")): signals.append("possible_false_dilemma_marker")
    return {"premises": premises, "conclusion": conclusion, "signals": signals, "note": "signals are prompts for scrutiny, not automatic fallacy labels"}


def analyze_framing(text: str) -> dict:
    t = normalize_text(text).casefold()
    found = [term for term in _LOADED if term in t]
    return {"loaded_terms": found, "has_framing_signal": bool(found), "note": "framing signal does not by itself make the underlying factual claim false"}


def extract_quoted_phrases(text: str) -> list[str]:
    found = re.findall(r"[«\"]([^»\"]{3,300})[»\"]", text)
    return list(dict.fromkeys(normalize_text(x) for x in found if normalize_text(x)))
