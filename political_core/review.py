from __future__ import annotations

import argparse
import gzip
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .dataset import iter_jsonl, promote_verified, review_case_fingerprint, validate_case, validate_jsonl


@dataclass(slots=True)
class ReviewApplyReport:
    total_cases: int = 0
    decisions: int = 0
    applied: int = 0
    unchanged: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:return not self.errors
    def to_dict(self) -> dict[str, Any]:
        return {"total_cases":self.total_cases,"decisions":self.decisions,"applied":self.applied,"unchanged":self.unchanged,"errors":self.errors,"ok":self.ok}


def case_fingerprint(case:dict[str,Any])->str:
    """Public compatibility alias for the dataset review fingerprint."""
    return review_case_fingerprint(case)


def review_template(case:dict[str,Any])->dict[str,Any]:
    return {
        "case_id":str(case.get("id") or ""),"case_fingerprint":review_case_fingerprint(case),
        "reviewer_id":"","reviewed_at":"","expected_verdict":case.get("candidate_verdict"),
        "acceptable_verdicts":[],"reviewer_note":"",
    }


def validate_review_decision(decision:dict[str,Any],case:dict[str,Any])->list[str]:
    errors=[];case_id=str(case.get("id") or "")
    if str(decision.get("case_id") or "")!=case_id:errors.append("case_id_mismatch")
    if str(decision.get("case_fingerprint") or "")!=review_case_fingerprint(case):errors.append("stale_or_wrong_case_fingerprint")
    reviewer=str(decision.get("reviewer_id") or "").strip()
    if not reviewer:errors.append("missing_reviewer_id")
    preparer=str(case.get("preparer_id") or case.get("prepared_by") or "").strip()
    if reviewer and preparer and reviewer.casefold()==preparer.casefold():errors.append("reviewer_must_be_independent_from_preparer")
    if not str(decision.get("reviewed_at") or "").strip():errors.append("missing_reviewed_at")
    if not str(decision.get("reviewer_note") or "").strip():errors.append("missing_reviewer_note")
    if case.get("review_status") not in {"human_required","machine_prepared"}:errors.append("case_not_reviewable")
    if decision.get("expected_verdict") is None:errors.append("missing_expected_verdict")
    return errors


def apply_review_decision(case:dict[str,Any],decision:dict[str,Any])->dict[str,Any]:
    errors=validate_review_decision(decision,case)
    if errors:raise ValueError(",".join(errors))
    acceptable=decision.get("acceptable_verdicts")
    if acceptable is not None and not isinstance(acceptable,list):raise ValueError("acceptable_verdicts_must_be_list")
    original_hash=review_case_fingerprint(case)
    out=promote_verified(
        case,expected_verdict=str(decision["expected_verdict"]),reviewed_at=str(decision["reviewed_at"]),
        reviewer_note=str(decision["reviewer_note"]),acceptable_verdicts=list(acceptable or [str(decision["expected_verdict"])]),
    )
    out["reviewer_id"]=str(decision["reviewer_id"]).strip();out["review_case_hash"]=original_hash
    if review_case_fingerprint(out)!=original_hash:raise ValueError("promotion_mutated_reviewed_case_fields")
    return out


def _load_decisions(path:str|Path)->tuple[dict[str,dict[str,Any]],list[dict[str,Any]]]:
    decisions={};errors=[]
    for line_no,decision in iter_jsonl(path):
        case_id=str(decision.get("case_id") or "")
        if not case_id:errors.append({"line":line_no,"error":"missing_case_id"});continue
        if case_id in decisions:errors.append({"line":line_no,"case_id":case_id,"error":"duplicate_review_decision"});continue
        decisions[case_id]=decision
    return decisions,errors


def _write_jsonl(path:str|Path,rows:Iterable[dict[str,Any]])->None:
    path=Path(path);opener=gzip.open if path.suffix==".gz" else open
    with opener(path,mode="wt",encoding="utf-8") as handle:
        for row in rows:handle.write(json.dumps(row,ensure_ascii=False,separators=(",",":"))+"\n")


def export_review_templates(dataset_path:str|Path,output_path:str|Path)->dict[str,Any]:
    rows=[];skipped=0
    for _,case in iter_jsonl(dataset_path):
        if validate_case(case):skipped+=1;continue
        if case.get("review_status") in {"human_required","machine_prepared"}:rows.append(review_template(case))
        else:skipped+=1
    _write_jsonl(output_path,rows);return {"templates":len(rows),"skipped":skipped}


def apply_review_file(dataset_path:str|Path,decisions_path:str|Path,output_path:str|Path)->ReviewApplyReport:
    decisions,decision_errors=_load_decisions(decisions_path);report=ReviewApplyReport(decisions=len(decisions),errors=list(decision_errors));rows=[];seen_cases=set()
    for line_no,case in iter_jsonl(dataset_path):
        report.total_cases+=1;case_id=str(case.get("id") or "")
        if not case_id:report.errors.append({"line":line_no,"error":"dataset_case_missing_id"});rows.append(case);continue
        seen_cases.add(case_id);decision=decisions.get(case_id)
        if decision is None:report.unchanged+=1;rows.append(case);continue
        try:promoted=apply_review_decision(case,decision)
        except Exception as exc:report.errors.append({"line":line_no,"case_id":case_id,"error":str(exc)});rows.append(case);continue
        report.applied+=1;rows.append(promoted)
    for case_id in sorted(set(decisions)-seen_cases):report.errors.append({"case_id":case_id,"error":"review_decision_for_unknown_case"})
    if report.errors:return report
    _write_jsonl(output_path,rows);post=validate_jsonl(output_path)
    if not post.valid:report.errors.append({"error":"output_dataset_invalid","details":post.errors})
    return report


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(prog="political-review");sub=parser.add_subparsers(dest="command",required=True)
    export=sub.add_parser("export");export.add_argument("dataset");export.add_argument("output")
    apply=sub.add_parser("apply");apply.add_argument("dataset");apply.add_argument("decisions");apply.add_argument("output");args=parser.parse_args(argv)
    if args.command=="export":print(json.dumps(export_review_templates(args.dataset,args.output),ensure_ascii=False,indent=2));return 0
    report=apply_review_file(args.dataset,args.decisions,args.output);print(json.dumps(report.to_dict(),ensure_ascii=False,indent=2));return 0 if report.ok else 2


if __name__=="__main__":raise SystemExit(main())
