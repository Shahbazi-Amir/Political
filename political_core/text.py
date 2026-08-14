from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRANSLATION = str.maketrans({
    "ي": "ی",
    "ى": "ی",
    "ك": "ک",
    "ۀ": "ه",
    "ة": "ه",
    "ؤ": "و",
    "إ": "ا",
    "أ": "ا",
})
_ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_WS = re.compile(r"\s+")
_TRACKING_KEYS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src",
}


def normalize_text(text: str) -> str:
    text = (text or "").translate(_TRANSLATION)
    text = _ZERO_WIDTH.sub(" ", text)
    return _WS.sub(" ", text).strip()


def fingerprint(text: str) -> str:
    return hashlib.sha256(normalize_text(text).casefold().encode("utf-8")).hexdigest()


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    port = parts.port
    netloc = host
    if port and not ((parts.scheme == "http" and port == 80) or (parts.scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in _TRACKING_KEYS]
    query.sort()
    return urlunsplit((parts.scheme.lower(), netloc, path, urlencode(query), ""))


def domain_of(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def build_queries(claim: str, limit: int) -> list[str]:
    """Cheap deterministic query planning; no model call is required."""
    claim = normalize_text(claim)
    if not claim:
        return []
    candidates = [claim[:320]]
    # A second query removes common question/preamble words that often hurt Persian search recall.
    reduced = re.sub(
        r"^(آیا|ایا|میخوام بدونم|می خواهم بدانم|میخوام ببینم|درسته که|درست است که|واقعاً|واقعا)\s+",
        "",
        claim,
        flags=re.IGNORECASE,
    ).strip(" ؟?!.")
    if reduced and reduced != candidates[0]:
        candidates.append(reduced[:320])
    # For deeper checks, add existence/document language without imposing a political viewpoint.
    if limit > 2:
        candidates.extend([
            f'{reduced[:220]} "حکم"',
            f'{reduced[:220]} "متن کامل"',
            f'{reduced[:220]} "منبع رسمی"',
            f'{reduced[:220]} "تکذیب"',
        ])
    out: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        key = item.casefold()
        if item and key not in seen:
            seen.add(key)
            out.append(item)
        if len(out) >= limit:
            break
    return out
