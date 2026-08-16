from __future__ import annotations
import argparse, json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from .dataset import is_auditable_verified_case, iter_jsonl, review_case_fingerprint
from .models import Verdict
from .review import apply_review_decision, validate_review_decision
from .reviewer_identity import ReviewerIdentityProvider

_VALID_VERDICTS = {v.value for v in Verdict}

@dataclass(frozen=True, slots=True)
class ReviewPolicy:
    required_reviewers_per_case: int = 1
    require_identity_registry: bool = False
    reviewer_role: str = "reviewer"
    adjudicator_role: str = "adjudicator"
    def __post_init__(self) -> None:
        if self.required_reviewers_per_case < 1: raise ValueError("required_reviewers_per_case must be >= 1")

@dataclass(slots=True)
class ReviewConsensus:
    status: str
    case_id: str
    reviewer_ids: list[str] = field(default_factory=list)
    expected_verdict: str | None = None
    errors: list[str] = field(default_factory=list)
    @property
    def verified(self) -> bool:return self.status == "verified" and self.expected_verdict in _VALID_VERDICTS

def _eligible_decisions(case: dict[str, Any], decisions: Iterable[dict[str, Any]], *, policy: ReviewPolicy, identity_provider: ReviewerIdentityProvider | None) -> tuple[list[dict[str, Any]], list[str]]:
    valid=[]; errors=[]; seen=set()
    for decision in decisions:
        reviewer=str(decision.get("reviewer_id") or "").strip();decision_errors=list(validate_review_decision(decision,case));verdict=str(decision.get("expected_verdict") or "")
        if verdict not in _VALID_VERDICTS:decision_errors.append("invalid_expected_verdict")
        if reviewer in seen and reviewer:decision_errors.append("duplicate_reviewer")
        if policy.require_identity_registry and identity_provider is None:decision_errors.append("identity_registry_required")
        if identity_provider is not None:
            identity=identity_provider.resolve(reviewer)
            if identity is None:decision_errors.append("unknown_reviewer_identity")
            elif not identity.active:decision_errors.append("inactive_reviewer_identity")
            elif not identity.has_role(policy.reviewer_role):decision_errors.append("reviewer_missing_required_role")
            preparer=str(case.get("preparer_id") or case.get("prepared_by") or "").strip()
            if preparer and reviewer.casefold()==preparer.casefold():decision_errors.append("reviewer_must_be_independent_from_preparer")
        if decision_errors:errors.extend(f"{reviewer or '<missing>'}:{x}" for x in dict.fromkeys(decision_errors));continue
        seen.add(reviewer);valid.append(decision)
    return valid,errors

def evaluate_review_consensus(case: dict[str, Any], decisions: Iterable[dict[str, Any]], *, policy: ReviewPolicy | None = None, identity_provider: ReviewerIdentityProvider | None = None) -> ReviewConsensus:
    policy=policy or ReviewPolicy();valid,errors=_eligible_decisions(case,decisions,policy=policy,identity_provider=identity_provider);case_id=str(case.get("id") or "");reviewer_ids=[str(x["reviewer_id"]).strip() for x in valid]
    if errors:return ReviewConsensus("invalid",case_id,reviewer_ids,errors=errors)
    if len(valid)<policy.required_reviewers_per_case:return ReviewConsensus("insufficient_reviews",case_id,reviewer_ids)
    verdicts={str(x["expected_verdict"]) for x in valid}
    if len(verdicts)!=1:return ReviewConsensus("review_conflict",case_id,reviewer_ids)
    return ReviewConsensus("verified",case_id,reviewer_ids,next(iter(verdicts)))

def promote_consensus(case: dict[str, Any], decisions: Iterable[dict[str, Any]], *, policy: ReviewPolicy | None = None, identity_provider: ReviewerIdentityProvider | None = None) -> dict[str, Any]:
    decisions=list(decisions);consensus=evaluate_review_consensus(case,decisions,policy=policy,identity_provider=identity_provider)
    if not consensus.verified:raise ValueError(f"review consensus not promotable: {consensus.status}")
    chosen=next(x for x in decisions if str(x.get("expected_verdict"))==consensus.expected_verdict);promoted=apply_review_decision(case,chosen);promoted["reviewer_id"]=",".join(consensus.reviewer_ids);promoted["reviewer_note"]=" | ".join(f"{x['reviewer_id']}: {str(x.get('reviewer_note') or '').strip()}" for x in decisions if str(x.get("reviewer_id") or "").strip() in consensus.reviewer_ids);promoted["review_records"]=[{"reviewer_id":str(x["reviewer_id"]).strip(),"reviewed_at":str(x["reviewed_at"]),"expected_verdict":str(x["expected_verdict"]),"acceptable_verdicts":list(x.get("acceptable_verdicts") or [x["expected_verdict"]]),"reviewer_note":str(x.get("reviewer_note") or "").strip(),"case_fingerprint":str(x.get("case_fingerprint") or "")} for x in decisions if str(x.get("reviewer_id") or "").strip() in consensus.reviewer_ids];promoted["review_case_hash"]=review_case_fingerprint(case)
    if not is_auditable_verified_case(promoted):raise ValueError("promoted consensus failed auditable review validation")
    return promoted

def adjudicate_review_conflict(case: dict[str, Any], decisions: Iterable[dict[str, Any]], adjudication: dict[str, Any], *, policy: ReviewPolicy | None = None, identity_provider: ReviewerIdentityProvider | None = None) -> dict[str, Any]:
    policy=policy or ReviewPolicy(required_reviewers_per_case=2);decisions=list(decisions);consensus=evaluate_review_consensus(case,decisions,policy=policy,identity_provider=identity_provider)
    if consensus.status!="review_conflict":raise ValueError("adjudication requires a review_conflict")
    adjudicator=str(adjudication.get("reviewer_id") or "").strip()
    if adjudicator in set(consensus.reviewer_ids):raise ValueError("adjudicator must be distinct from reviewers")
    errors=list(validate_review_decision(adjudication,case));verdict=str(adjudication.get("expected_verdict") or "")
    if verdict not in _VALID_VERDICTS:errors.append("invalid_expected_verdict")
    if identity_provider is not None:
        identity=identity_provider.resolve(adjudicator)
        if identity is None or not identity.active or not identity.has_role(policy.adjudicator_role):errors.append("invalid_adjudicator_identity_or_role")
    elif policy.require_identity_registry:errors.append("identity_registry_required")
    if errors:raise ValueError(",".join(dict.fromkeys(errors)))
    promoted=apply_review_decision(case,adjudication);promoted["reviewer_id"]=",".join(consensus.reviewer_ids+[adjudicator]);promoted["review_records"]=[{"reviewer_id":str(x["reviewer_id"]),"expected_verdict":str(x["expected_verdict"]),"reviewed_at":str(x["reviewed_at"])} for x in decisions];promoted["adjudication_record"]={"reviewer_id":adjudicator,"reviewed_at":str(adjudication["reviewed_at"]),"expected_verdict":verdict,"reviewer_note":str(adjudication.get("reviewer_note") or "").strip()};promoted["review_case_hash"]=review_case_fingerprint(case);promoted["reviewer_note"]=str(adjudication.get("reviewer_note") or "").strip()
    if not is_auditable_verified_case(promoted):raise ValueError("adjudicated case failed auditable review validation")
    return promoted

def review_status_report(dataset_path: str | Path, decisions_path: str | Path | None = None) -> dict[str, Any]:
    cases={str(case.get("id") or ""):case for _,case in iter_jsonl(dataset_path) if str(case.get("id") or "")};states=Counter(str(case.get("review_status") or "unknown") for case in cases.values());reviewer_counts=Counter();conflicts=0
    if decisions_path is not None:
        grouped=defaultdict(list)
        for _,decision in iter_jsonl(decisions_path):grouped[str(decision.get("case_id") or "")].append(decision)
        for case_id,rows in grouped.items():
            if case_id not in cases:continue
            reviewer_counts[case_id]=len({str(row.get("reviewer_id") or "").strip() for row in rows if str(row.get("reviewer_id") or "").strip()})
            if len({str(x.get("expected_verdict") or "") for x in rows if x.get("expected_verdict")})>1:conflicts+=1
    return {"total":len(cases),"machine_prepared":states["machine_prepared"],"human_required":states["human_required"],"verified":states["verified"],"auditable_verified":sum(1 for case in cases.values() if is_auditable_verified_case(case)),"reviewed_once":sum(1 for n in reviewer_counts.values() if n==1),"reviewed_twice_or_more":sum(1 for n in reviewer_counts.values() if n>=2),"review_conflicts":conflicts,"rejected":states["rejected"]}

def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(prog="political-review-governance");sub=parser.add_subparsers(dest="command",required=True);status=sub.add_parser("status");status.add_argument("dataset");status.add_argument("--decisions");args=parser.parse_args(argv);print(json.dumps(review_status_report(args.dataset,args.decisions),ensure_ascii=False,indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
