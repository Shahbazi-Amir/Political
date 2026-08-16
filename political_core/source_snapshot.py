from __future__ import annotations
import hashlib
from datetime import datetime,timezone
from typing import Any
from .text import canonical_url

def build_source_record(url:str,content:str,*,media_type:str="text/html",retrieved_at:str|None=None,publication_date:str|None=None,archive_url:str|None=None)->dict[str,Any]:
    return {
        "url":url,
        "canonical_url":canonical_url(url),
        "retrieved_at":retrieved_at or datetime.now(timezone.utc).isoformat(),
        "content_sha256":hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "media_type":media_type,
        "publication_date":publication_date,
        "archive_url":archive_url,
        "status":"reachable",
    }

def source_changed(record:dict[str,Any],content:str)->bool:
    expected=str(record.get("content_sha256") or "")
    if not expected:return False
    return hashlib.sha256(content.encode("utf-8")).hexdigest()!=expected
