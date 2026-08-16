from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

from .models import Verdict

REQUIRED_CATEGORIES = (
    "appointment","dismissal","membership","current_status","constitutional","legal","quote","negative_claim",
    "breaking_news_like","copied_sources","conflicting_sources","official_statement_vs_fact","outdated_claim","misleading","missing_context","causal_argument",
)
_REVIEW_STATES = {"human_required", "machine_prepared", "verified", "rejected"}
_VALID_VERDICTS = {v.value for v in Verdict}


@dataclass(slots=True)
class DatasetValidation:
    total_cases:int=0
    valid_cases:int=0
    verified_cases:int=0
    review_ready_cases:int=0
    duplicate_ids:list[str]=field(default_factory=list)
    errors:list[dict[str,Any]]=field(default_factory=list)
    category_counts:dict[str,int]=field(default_factory=dict)
    verified_category_counts:dict[str,int]=field(default_factory=dict)

    @property
    def valid(self)->bool:return not self.errors and not self.duplicate_ids
    @property
    def review_queue_ready(self)->bool:
        return self.valid and self.review_ready_cases>=100 and all(self.category_counts.get(c,0)>=5 for c in REQUIRED_CATEGORIES)
    @property
    def production_benchmark_ready(self)->bool:
        return self.valid and self.verified_cases>=100 and all(self.verified_category_counts.get(c,0)>=5 for c in REQUIRED_CATEGORIES)
    def to_dict(self)->dict[str,Any]:
        return {"total_cases":self.total_cases,"valid_cases":self.valid_cases,"verified_cases":self.verified_cases,"review_ready_cases":self.review_ready_cases,"duplicate_ids":self.duplicate_ids,"errors":self.errors,"category_counts":self.category_counts,"verified_category_counts":self.verified_category_counts,"review_queue_ready":self.review_queue_ready,"production_benchmark_ready":self.production_benchmark_ready}


def iter_jsonl(path:str|Path)->Iterable[tuple[int,dict[str,Any]]]:
    path=Path(path);opener=gzip.open if path.suffix==".gz" else open
    with opener(path,mode="rt",encoding="utf-8") as handle:
        for line_no,line in enumerate(handle,1):
            line=line.strip()
            if not line:continue
            try:value=json.loads(line)
            except json.JSONDecodeError as exc:
                yield line_no,{"__parse_error__":str(exc)};continue
            if not isinstance(value,dict):
                yield line_no,{"__parse_error__":"case must be a JSON object"};continue
            yield line_no,value


def _public_http_url(value:str)->bool:
    try:parts=urlsplit(value)
    except Exception:return False
    return parts.scheme in {"http","https"} and bool(parts.hostname)


def validate_case(case:dict[str,Any],*,line_no:int|None=None)->list[str]:
    errors=[]
    if "__parse_error__" in case:return [str(case["__parse_error__"])]
    for key in ("id","claim","language","claim_type","category","review_status"):
        if not str(case.get(key) or "").strip():errors.append(f"missing_{key}")
    if case.get("language")!="fa":errors.append("language_must_be_fa")
    category=str(case.get("category") or "")
    if category not in REQUIRED_CATEGORIES:errors.append("unsupported_category")
    review_status=str(case.get("review_status") or "")
    if review_status not in _REVIEW_STATES:errors.append("unsupported_review_status")
    sources=case.get("ground_truth_sources")
    if not isinstance(sources,list) or not sources:errors.append("missing_ground_truth_sources")
    elif any(not isinstance(source,str) or not _public_http_url(source) for source in sources):errors.append("invalid_ground_truth_source_url")
    tags=case.get("tags")
    if not isinstance(tags,list) or category not in tags:errors.append("category_missing_from_tags")
    independent=case.get("independent_human_review") is True;reviewed_at=case.get("reviewed_at");expected=case.get("expected_verdict");candidate=case.get("candidate_verdict")
    if candidate is not None and candidate not in _VALID_VERDICTS:errors.append("invalid_candidate_verdict")
    if review_status=="verified":
        if expected not in _VALID_VERDICTS:errors.append("verified_case_invalid_expected_verdict")
        if not independent:errors.append("verified_case_requires_independent_human_review")
        if not reviewed_at:errors.append("verified_case_missing_reviewed_at")
        if not str(case.get("ground_truth_notes") or "").strip():errors.append("verified_case_missing_ground_truth_notes")
    elif independent:errors.append("independent_human_review_only_valid_for_verified")
    acceptable=case.get("acceptable_verdicts",[])
    if not isinstance(acceptable,list) or any(v not in _VALID_VERDICTS for v in acceptable):errors.append("invalid_acceptable_verdicts")
    return errors


def validate_jsonl(path:str|Path)->DatasetValidation:
    report=DatasetValidation();ids=set();duplicates=set();categories=Counter();verified_categories=Counter()
    for line_no,case in iter_jsonl(path):
        report.total_cases+=1;errors=validate_case(case,line_no=line_no);case_id=str(case.get("id") or "")
        if case_id:
            if case_id in ids:duplicates.add(case_id)
            ids.add(case_id)
        if errors:
            report.errors.append({"line":line_no,"id":case_id or None,"errors":errors});continue
        report.valid_cases+=1;category=str(case["category"]);categories[category]+=1
        if case.get("review_status") in {"human_required","machine_prepared","verified"}:report.review_ready_cases+=1
        if case.get("review_status")=="verified":report.verified_cases+=1;verified_categories[category]+=1
    report.duplicate_ids=sorted(duplicates)
    report.category_counts={c:categories.get(c,0) for c in REQUIRED_CATEGORIES}
    report.verified_category_counts={c:verified_categories.get(c,0) for c in REQUIRED_CATEGORIES}
    return report


def promote_verified(case:dict[str,Any],*,expected_verdict:str,reviewed_at:str,reviewer_note:str,acceptable_verdicts:list[str]|None=None)->dict[str,Any]:
    """Promote only when the caller supplies metadata from a real human review."""
    if expected_verdict not in _VALID_VERDICTS:raise ValueError("expected_verdict is invalid")
    if not reviewed_at or not reviewer_note.strip():raise ValueError("reviewed_at and reviewer_note are required")
    out=dict(case);out.update({"review_status":"verified","expected_verdict":expected_verdict,"acceptable_verdicts":list(acceptable_verdicts or [expected_verdict]),"independent_human_review":True,"reviewed_at":reviewed_at,"ground_truth_notes":reviewer_note})
    errors=validate_case(out)
    if errors:raise ValueError("invalid promoted case: "+",".join(errors))
    return out


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(prog="political-dataset");parser.add_argument("path");parser.add_argument("--require-review-queue-ready",action="store_true");parser.add_argument("--require-production-ready",action="store_true");args=parser.parse_args(argv)
    report=validate_jsonl(args.path);print(json.dumps(report.to_dict(),ensure_ascii=False,indent=2))
    if not report.valid:return 2
    if args.require_review_queue_ready and not report.review_queue_ready:return 3
    if args.require_production_ready and not report.production_benchmark_ready:return 4
    return 0


if __name__=="__main__":raise SystemExit(main())
