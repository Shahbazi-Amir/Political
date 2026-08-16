from __future__ import annotations
import hashlib
from typing import Any

SPLIT_POLICY_VERSION="split-v1"

def case_split(case:dict[str,Any])->str:
    explicit=case.get("split")
    if explicit in {"train","calibration","evaluation"}:return str(explicit)
    case_id=str(case.get("id") or "")
    bucket=int(hashlib.sha256(case_id.encode("utf-8")).hexdigest()[:8],16)%100
    if bucket<20:return "calibration"
    return "evaluation"
