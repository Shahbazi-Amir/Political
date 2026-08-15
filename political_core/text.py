from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRANSLATION = str.maketrans({
    "ي": "ی", "ى": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه", "ؤ": "و", "إ": "ا", "أ": "ا",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4", "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4", "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
})
_ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_DIACRITICS = re.compile(r"[\u064b-\u065f\u0670]")
_WS = re.compile(r"\s+")
_TRACKING_KEYS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id", "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src", "source", "campaign"}


def normalize_text(text: str) -> str:
    text = (text or "").translate(_TRANSLATION)
    text = _DIACRITICS.sub("", text)
    text = _ZERO_WIDTH.sub(" ", text)
    text = text.replace("ـ", "")
    return _WS.sub(" ", text).strip()


def fingerprint(text: str) -> str:
    compact = re.sub(r"[؟?!.،,:;؛\-–—()\[\]{}\"'«»]", " ", normalize_text(text).casefold())
    compact = _WS.sub(" ", compact).strip()
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


def canonical_url(url: str) -> str:
    parts = urlsplit((url or "").strip())
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError("invalid public URL")
    host = parts.hostname.lower().strip(".")
    port = parts.port
    netloc = host
    if port and not ((parts.scheme.lower() == "http" and port == 80) or (parts.scheme.lower() == "https" and port == 443)):
        netloc = f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in _TRACKING_KEYS]
    query.sort()
    return urlunsplit((parts.scheme.lower(), netloc, path, urlencode(query), ""))


def domain_of(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower().strip(".")
    return host[4:] if host.startswith("www.") else host


def token_set(text: str) -> set[str]:
    text = normalize_text(text).casefold()
    return {t for t in re.findall(r"[\w\u0600-\u06ff]+", text) if len(t) > 2}


def lexical_relevance(claim: str, text: str) -> float:
    a, b = token_set(claim), token_set(text)
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a))


def build_queries(claim: str, limit: int) -> list[str]:
    claim = normalize_text(claim)
    if not claim:
        return []
    reduced = re.sub(r"^(آیا|ایا|میخوام بدونم|می خواهم بدانم|درسته که|درست است که|واقعا|واقعاً)\s+", "", claim, flags=re.I).strip(" ؟?!.")
    candidates = [reduced[:320] or claim[:320], f'{reduced[:220]} "منبع رسمی"', f'{reduced[:220]} "تکذیب"']
    out: list[str] = []
    for item in candidates:
        if item and item not in out:
            out.append(item)
        if len(out) >= limit:
            break
    return out
