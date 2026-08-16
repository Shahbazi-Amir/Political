from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

from .models import Verdict

REQUIRED_CATEGORIES = (
    "appointment","dismissal","membership","current_status","constitutional","legal","quote","negative_claim",
    "breaking_news_like","copied_sources","conflicting_sources","official_statement_vs_fact","outdated_claim",
    "misleading","missing_context","causal_argument",
)
REVIEW_FINGERPRINT_FIELDS = (
    "id","claim","language","claim_type","category","reference_date","candidate_verdict",
    "ground_truth_sources","ground_truth_source_records","ground_truth_notes","tags","preparer_id","prepared_by","split",
)
_REVIEW_STATES = {"human_required","machine_prepared","verified","rejected","review_conflict"}
_VALID_VERDICTS = {v.value for v in Verdict}
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
REVIEW_POLICY_VERSION = "review-v2"


@dataclass(slots=True)
class DatasetValidation:
    total_cases:int=0
    valid_cases:int=0
    verified_cases:int=0
    auditable_verified_cases:int=0
    source_snapshot_verified_cases:int=0
    review_ready_cases:int=0
    duplicate_ids:list[str]=field(default_factory=list)
    errors:list[dict[str,Any]]=field(default_factory=list)
    review_audit_failures:list[str]=field(default_factory=list)
    category_counts:dict[str,int]=field(default_factory=dict)
    verified_category_counts:dict[str,int]=field(default_factory=dict)
    required_reviewers_per_case:int=1
    minimum_identity_assurance:str="unverified"

    @property
    def valid(self)->bool:
        return not self.errors and not self.duplicate_ids

    @property
    def review_queue_ready(self)->bool:
        return self.valid and self.review_ready_cases>=100 and all(self.category_counts.get(c,0)>=5 for c in REQUIRED_CATEGORIES)

    @property
    def production_benchmark_ready(self)->bool:
        return (
            self.valid
            and self.auditable_verified_cases>=100
            and self.source_snapshot_verified_cases==self.auditable_verified_cases
            and not self.review_audit_failures
            and all(self.verified_category_counts.get(c,0)>=5 for c in REQUIRED_CATEGORIES)
        )

    def to_dict(self)->dict[str,Any]:
        return {
            "total_cases":self.total_cases,"valid_cases":self.valid_cases,"verified_cases":self.verified_cases,
            "auditable_verified_cases":self.auditable_verified_cases,"source_snapshot_verified_cases":self.source_snapshot_verified_cases,"review_ready_cases":self.review_ready_cases,
            "duplicate_ids":self.duplicate_ids,"errors":self.errors,"review_audit_failures":self.review_audit_failures,
            "category_counts":self.category_counts,"verified_category_counts":self.verified_category_counts,
            "required_reviewers_per_case":self.required_reviewers_per_case,"minimum_identity_assurance":self.minimum_identity_assurance,
            "review_queue_ready":self.review_queue_ready,"production_benchmark_ready":self.production_benchmark_ready,
        }


def iter_jsonl(path:str|Path)->Iterable[tuple[int,dict[str,Any]]]:
    path=Path(path);opener=gzip.open if path.suffix==".gz" else open
    with opener(path,mode="rt",encoding="utf-8") as handle:
        for line_no,line in enumerate(handle,1):
            line=line.strip()
            if not line: continue
            try:value=json.loads(line)
            except json.JSONDecodeError as exc:
                yield line_no,{"__parse_error__":str(exc)};continue
            if not isinstance(value,dict):
                yield line_no,{"__parse_error__":"case must be a JSON object"};continue
            yield line_no,value


def _canonical_json(value:Any)->str:
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))


def review_case_fingerprint(case:dict[str,Any])->str:
    payload={key:case.get(key) for key in REVIEW_FINGERPRINT_FIELDS}
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def review_record_hash(record:dict[str,Any])->str:
    payload={
        "case_fingerprint":record.get("case_fingerprint"),
        "reviewer_id":str(record.get("reviewer_id") or "").strip(),
        "reviewed_at":record.get("reviewed_at"),
        "expected_verdict":record.get("expected_verdict"),
        "acceptable_verdicts":sorted(set(record.get("acceptable_verdicts") or [])),
        "reviewer_note":str(record.get("reviewer_note") or "").strip(),
        "identity_assurance":str(record.get("identity_assurance") or "unverified"),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def adjudication_record_hash(record:dict[str,Any])->str:
    payload={
        "case_fingerprint":record.get("case_fingerprint"),
        "reviewer_id":str(record.get("reviewer_id") or "").strip(),
        "reviewed_at":record.get("reviewed_at"),
        "expected_verdict":record.get("expected_verdict"),
        "acceptable_verdicts":sorted(set(record.get("acceptable_verdicts") or [])),
        "reviewer_note":str(record.get("reviewer_note") or "").strip(),
        "identity_assurance":str(record.get("identity_assurance") or "unverified"),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def governance_bundle_hash(case:dict[str,Any])->str:
    records=case.get("review_records") if isinstance(case.get("review_records"),list) else []
    adjudication=case.get("adjudication_record") if isinstance(case.get("adjudication_record"),dict) else None
    payload={
        "case_hash":str(case.get("review_case_hash") or ""),
        "policy_version":str(case.get("review_policy_version") or REVIEW_POLICY_VERSION),
        "required_reviewers_per_case":int(case.get("required_reviewers_per_case") or 1),
        "minimum_identity_assurance":str(case.get("minimum_identity_assurance") or "unverified"),
        "review_hashes":sorted(str(r.get("review_hash") or "") for r in records),
        "adjudication_hash":str(adjudication.get("review_hash") or "") if adjudication else None,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def parse_reviewed_at(value:Any,*,now:datetime|None=None,max_future_skew_seconds:int=300)->datetime:
    raw=str(value or "").strip()
    if not raw: raise ValueError("missing_reviewed_at")
    normalized=raw[:-1]+"+00:00" if raw.endswith("Z") else raw
    try:dt=datetime.fromisoformat(normalized)
    except ValueError as exc: raise ValueError("invalid_reviewed_at") from exc
    if dt.tzinfo is None: raise ValueError("reviewed_at_timezone_required")
    dt=dt.astimezone(timezone.utc);now=now or datetime.now(timezone.utc)
    if dt>now+timedelta(seconds=max_future_skew_seconds):raise ValueError("reviewed_at_in_future")
    return dt


def _public_http_url(value:str)->bool:
    try:parts=urlsplit(value)
    except Exception:return False
    return parts.scheme in {"http","https"} and bool(parts.hostname)


def _valid_source_record(record:Any)->bool:
    if not isinstance(record,dict):return False
    if not _public_http_url(str(record.get("url") or "")):return False
    sha=str(record.get("content_sha256") or "")
    if sha and not _HEX64.fullmatch(sha.lower()):return False
    retrieved=record.get("retrieved_at")
    if retrieved:
        try:parse_reviewed_at(retrieved,max_future_skew_seconds=86400)
        except ValueError:return False
    return True


def source_snapshot_complete(case:dict[str,Any])->bool:
    sources=[str(x) for x in (case.get("ground_truth_sources") or []) if isinstance(x,str)]
    records=case.get("ground_truth_source_records")
    if not sources or not isinstance(records,list) or len(records)<len(sources):return False
    by_url={str(r.get("url") or ""):r for r in records if isinstance(r,dict)}
    for url in sources:
        record=by_url.get(url)
        if record is None or not _valid_source_record(record):return False
        if not _HEX64.fullmatch(str(record.get("content_sha256") or "").lower()):return False
        if not str(record.get("retrieved_at") or "").strip():return False
    return True


def is_auditable_verified_case(case:dict[str,Any],*,required_reviewers:int=1,require_governance_hash:bool|None=None,minimum_identity_assurance:str="unverified")->bool:
    if case.get("review_status")!="verified" or case.get("independent_human_review") is not True:return False
    review_hash=str(case.get("review_case_hash") or "").strip().lower()
    if not _HEX64.fullmatch(review_hash) or review_hash!=review_case_fingerprint(case):return False
    records=case.get("review_records")
    if isinstance(records,list) and records:
        assurance_order={"unverified":0,"registry_verified":1,"externally_authenticated":2}
        minimum_level=assurance_order.get(minimum_identity_assurance,0)
        try:stored_required=int(case.get("required_reviewers_per_case") or 1)
        except (TypeError,ValueError):return False
        stored_assurance=str(case.get("minimum_identity_assurance") or "unverified")
        if stored_required<max(1,int(required_reviewers)):return False
        if assurance_order.get(stored_assurance,0)<minimum_level:return False
        distinct=set()
        for record in records:
            if not isinstance(record,dict):return False
            reviewer=str(record.get("reviewer_id") or "").strip()
            if not reviewer or reviewer in distinct:return False
            distinct.add(reviewer)
            if assurance_order.get(str(record.get("identity_assurance") or "unverified"),0)<minimum_level:return False
            try:parse_reviewed_at(record.get("reviewed_at"))
            except ValueError:return False
            expected=record.get("expected_verdict")
            if expected not in _VALID_VERDICTS:return False
            if str(record.get("case_fingerprint") or "")!=review_hash:return False
            stored=str(record.get("review_hash") or "").lower()
            if not _HEX64.fullmatch(stored) or stored!=review_record_hash(record):return False
        if len(distinct)<max(1,int(required_reviewers)):return False
        adjudication=case.get("adjudication_record")
        if adjudication is not None:
            if not isinstance(adjudication,dict):return False
            if str(adjudication.get("reviewer_id") or "").strip() in distinct:return False
            try:parse_reviewed_at(adjudication.get("reviewed_at"))
            except ValueError:return False
            stored=str(adjudication.get("review_hash") or "").lower()
            if not _HEX64.fullmatch(stored) or stored!=adjudication_record_hash(adjudication):return False
        stored_bundle=str(case.get("governance_bundle_hash") or "").lower()
        if not _HEX64.fullmatch(stored_bundle) or stored_bundle!=governance_bundle_hash(case):return False
        return True
    if required_reviewers>1 or minimum_identity_assurance!="unverified":return False
    # Backwards-compatible single-review validation. New governed promotions always create review_records.
    reviewer=str(case.get("reviewer_id") or "").strip();note=str(case.get("reviewer_note") or "").strip()
    try:parse_reviewed_at(case.get("reviewed_at"))
    except ValueError:return False
    if require_governance_hash is True:return False
    return bool(reviewer and note)


def validate_case(case:dict[str,Any],*,line_no:int|None=None,required_reviewers:int=1,minimum_identity_assurance:str="unverified")->list[str]:
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
    source_records=case.get("ground_truth_source_records")
    if source_records is not None and (not isinstance(source_records,list) or any(not _valid_source_record(x) for x in source_records)):
        errors.append("invalid_ground_truth_source_records")
    tags=case.get("tags")
    if not isinstance(tags,list) or category not in tags:errors.append("category_missing_from_tags")
    independent=case.get("independent_human_review") is True;expected=case.get("expected_verdict");candidate=case.get("candidate_verdict")
    if candidate is not None and candidate not in _VALID_VERDICTS:errors.append("invalid_candidate_verdict")
    if review_status=="verified":
        if expected not in _VALID_VERDICTS:errors.append("verified_case_invalid_expected_verdict")
        if not independent:errors.append("verified_case_requires_independent_human_review")
        try:parse_reviewed_at(case.get("reviewed_at"))
        except ValueError as exc:errors.append(str(exc))
        if not str(case.get("ground_truth_notes") or "").strip():errors.append("verified_case_missing_ground_truth_notes")
    elif independent:errors.append("independent_human_review_only_valid_for_verified")
    acceptable=case.get("acceptable_verdicts",[])
    if not isinstance(acceptable,list) or any(v not in _VALID_VERDICTS for v in acceptable):errors.append("invalid_acceptable_verdicts")
    split=case.get("split")
    if split is not None and split not in {"calibration","evaluation","train"}:errors.append("invalid_split")
    return list(dict.fromkeys(errors))


def validate_jsonl(path:str|Path,*,required_reviewers:int=1,minimum_identity_assurance:str="unverified")->DatasetValidation:
    report=DatasetValidation(required_reviewers_per_case=max(1,int(required_reviewers)),minimum_identity_assurance=minimum_identity_assurance);ids=set();duplicates=set();categories=Counter();verified_categories=Counter()
    for line_no,case in iter_jsonl(path):
        report.total_cases+=1;errors=validate_case(case,line_no=line_no,required_reviewers=report.required_reviewers_per_case,minimum_identity_assurance=report.minimum_identity_assurance);case_id=str(case.get("id") or "")
        if case_id:
            if case_id in ids:duplicates.add(case_id)
            ids.add(case_id)
        if errors:
            report.errors.append({"line":line_no,"id":case_id or None,"errors":errors});continue
        report.valid_cases+=1;category=str(case["category"]);categories[category]+=1
        if case.get("review_status") in {"human_required","machine_prepared","verified"}:report.review_ready_cases+=1
        if case.get("review_status")=="verified":
            report.verified_cases+=1
            if is_auditable_verified_case(case,required_reviewers=report.required_reviewers_per_case,minimum_identity_assurance=report.minimum_identity_assurance):
                report.auditable_verified_cases+=1;verified_categories[category]+=1
                if source_snapshot_complete(case):report.source_snapshot_verified_cases+=1
            else:report.review_audit_failures.append(case_id)
    report.duplicate_ids=sorted(duplicates);report.review_audit_failures=sorted(x for x in report.review_audit_failures if x)
    report.category_counts={c:categories.get(c,0) for c in REQUIRED_CATEGORIES};report.verified_category_counts={c:verified_categories.get(c,0) for c in REQUIRED_CATEGORIES}
    return report


def promote_verified(case:dict[str,Any],*,expected_verdict:str,reviewed_at:str,reviewer_note:str,acceptable_verdicts:list[str]|None=None)->dict[str,Any]:
    """Low-level structural promotion. Production flows should add governed review records."""
    if expected_verdict not in _VALID_VERDICTS:raise ValueError("expected_verdict is invalid")
    parse_reviewed_at(reviewed_at)
    if not reviewer_note.strip():raise ValueError("reviewer_note is required")
    out=dict(case);out.update({"review_status":"verified","expected_verdict":expected_verdict,"acceptable_verdicts":list(acceptable_verdicts or [expected_verdict]),"independent_human_review":True,"reviewed_at":reviewed_at,"reviewer_note":reviewer_note})
    return out


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(prog="political-dataset");parser.add_argument("path");parser.add_argument("--require-review-queue-ready",action="store_true");parser.add_argument("--require-production-ready",action="store_true");parser.add_argument("--required-reviewers",type=int,default=1);parser.add_argument("--minimum-identity-assurance",default="unverified",choices=["unverified","registry_verified","externally_authenticated"]);args=parser.parse_args(argv)
    report=validate_jsonl(args.path,required_reviewers=args.required_reviewers,minimum_identity_assurance=args.minimum_identity_assurance);print(json.dumps(report.to_dict(),ensure_ascii=False,indent=2))
    if not report.valid:return 2
    if args.require_review_queue_ready and not report.review_queue_ready:return 3
    if args.require_production_ready and not report.production_benchmark_ready:return 4
    return 0


if __name__=="__main__":raise SystemExit(main())
