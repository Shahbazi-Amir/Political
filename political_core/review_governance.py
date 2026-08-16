from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .dataset import (
    REVIEW_POLICY_VERSION,
    adjudication_record_hash,
    governance_bundle_hash,
    is_auditable_verified_case,
    iter_jsonl,
    parse_reviewed_at,
    review_case_fingerprint,
    review_record_hash,
)
from .models import Verdict
from .review import validate_review_decision
from .reviewer_identity import ReviewerIdentityProvider

_VALID_VERDICTS={v.value for v in Verdict}


@dataclass(frozen=True,slots=True)
class ReviewPolicy:
    required_reviewers_per_case:int=1
    require_identity_registry:bool=False
    reviewer_role:str="reviewer"
    adjudicator_role:str="adjudicator"
    minimum_identity_assurance:str="unverified"
    policy_version:str=REVIEW_POLICY_VERSION
    def __post_init__(self)->None:
        if self.required_reviewers_per_case<1:raise ValueError("required_reviewers_per_case must be >= 1")


@dataclass(slots=True)
class ReviewConsensus:
    status:str
    case_id:str
    reviewer_ids:list[str]=field(default_factory=list)
    expected_verdict:str|None=None
    acceptable_verdicts:list[str]=field(default_factory=list)
    errors:list[str]=field(default_factory=list)
    @property
    def verified(self)->bool:
        return self.status=="verified" and self.expected_verdict in _VALID_VERDICTS


_ASSURANCE_ORDER={"unverified":0,"registry_verified":1,"externally_authenticated":2}


def _identity_ok(identity:Any,policy:ReviewPolicy,role:str)->bool:
    if identity is None or not identity.active or not identity.has_role(role):return False
    assurance=str(getattr(identity,"assurance_level","registry_verified"))
    return _ASSURANCE_ORDER.get(assurance,0)>=_ASSURANCE_ORDER.get(policy.minimum_identity_assurance,0)


def _eligible_decisions(case:dict[str,Any],decisions:Iterable[dict[str,Any]],*,policy:ReviewPolicy,identity_provider:ReviewerIdentityProvider|None)->tuple[list[dict[str,Any]],list[str]]:
    valid=[];errors=[];seen=set()
    for decision in decisions:
        reviewer=str(decision.get("reviewer_id") or "").strip()
        decision_errors=list(validate_review_decision(decision,case))
        verdict=str(decision.get("expected_verdict") or "")
        try:parse_reviewed_at(decision.get("reviewed_at"))
        except ValueError as exc:decision_errors.append(str(exc))
        if verdict not in _VALID_VERDICTS:decision_errors.append("invalid_expected_verdict")
        if reviewer in seen and reviewer:decision_errors.append("duplicate_reviewer")
        if policy.require_identity_registry and identity_provider is None:decision_errors.append("identity_registry_required")
        if identity_provider is None and policy.minimum_identity_assurance!="unverified":decision_errors.append("identity_provider_required_for_assurance")
        if identity_provider is not None:
            identity=identity_provider.resolve(reviewer)
            if not _identity_ok(identity,policy,policy.reviewer_role):decision_errors.append("invalid_reviewer_identity_role_or_assurance")
            preparer=str(case.get("preparer_id") or case.get("prepared_by") or "").strip()
            if preparer and reviewer.casefold()==preparer.casefold():decision_errors.append("reviewer_must_be_independent_from_preparer")
        if decision_errors:
            errors.extend(f"{reviewer or '<missing>'}:{x}" for x in dict.fromkeys(decision_errors));continue
        seen.add(reviewer);valid.append(decision)
    return valid,errors


def _acceptable_consensus(decisions:list[dict[str,Any]],expected:str)->list[str]:
    sets=[]
    for row in decisions:
        values=set(str(x) for x in (row.get("acceptable_verdicts") or [expected]) if str(x) in _VALID_VERDICTS)
        values.add(expected)
        sets.append(values)
    common=set.intersection(*sets) if sets else {expected}
    return sorted(common)


def evaluate_review_consensus(case:dict[str,Any],decisions:Iterable[dict[str,Any]],*,policy:ReviewPolicy|None=None,identity_provider:ReviewerIdentityProvider|None=None)->ReviewConsensus:
    policy=policy or ReviewPolicy();valid,errors=_eligible_decisions(case,decisions,policy=policy,identity_provider=identity_provider);case_id=str(case.get("id") or "");reviewer_ids=[str(x["reviewer_id"]).strip() for x in valid]
    if errors:return ReviewConsensus("invalid",case_id,reviewer_ids,errors=errors)
    if len(valid)<policy.required_reviewers_per_case:return ReviewConsensus("insufficient_reviews",case_id,reviewer_ids)
    verdicts={str(x["expected_verdict"]) for x in valid}
    if len(verdicts)!=1:return ReviewConsensus("review_conflict",case_id,reviewer_ids)
    expected=next(iter(verdicts));acceptable=_acceptable_consensus(valid,expected)
    if not acceptable or expected not in acceptable:return ReviewConsensus("acceptable_verdict_conflict",case_id,reviewer_ids,expected,acceptable)
    return ReviewConsensus("verified",case_id,reviewer_ids,expected,acceptable)


def _record(decision:dict[str,Any],case_hash:str,identity_assurance:str="unverified")->dict[str,Any]:
    record={
        "case_fingerprint":case_hash,
        "reviewer_id":str(decision["reviewer_id"]).strip(),
        "reviewed_at":str(decision["reviewed_at"]),
        "expected_verdict":str(decision["expected_verdict"]),
        "acceptable_verdicts":sorted(set(decision.get("acceptable_verdicts") or [decision["expected_verdict"]])),
        "reviewer_note":str(decision.get("reviewer_note") or "").strip(),
        "identity_assurance":identity_assurance,
    }
    record["review_hash"]=review_record_hash(record)
    return record


def promote_consensus(case:dict[str,Any],decisions:Iterable[dict[str,Any]],*,policy:ReviewPolicy|None=None,identity_provider:ReviewerIdentityProvider|None=None)->dict[str,Any]:
    policy=policy or ReviewPolicy();decisions=list(decisions);consensus=evaluate_review_consensus(case,decisions,policy=policy,identity_provider=identity_provider)
    if not consensus.verified:raise ValueError(f"review consensus not promotable: {consensus.status}")
    case_hash=review_case_fingerprint(case)
    records=[]
    for x in decisions:
        reviewer=str(x.get("reviewer_id") or "").strip()
        if reviewer not in consensus.reviewer_ids:continue
        identity=identity_provider.resolve(reviewer) if identity_provider is not None else None
        assurance=str(getattr(identity,"assurance_level","unverified"))
        records.append(_record(x,case_hash,assurance))
    latest=max(records,key=lambda x:parse_reviewed_at(x["reviewed_at"]))
    out=dict(case)
    out.update({
        "review_status":"verified",
        "expected_verdict":consensus.expected_verdict,
        "acceptable_verdicts":consensus.acceptable_verdicts,
        "independent_human_review":True,
        "reviewed_at":latest["reviewed_at"],
        "reviewer_id":",".join(consensus.reviewer_ids),
        "reviewer_note":" | ".join(f"{r['reviewer_id']}: {r['reviewer_note']}" for r in records),
        "review_case_hash":case_hash,
        "review_records":records,
        "review_policy_version":policy.policy_version,
        "required_reviewers_per_case":policy.required_reviewers_per_case,
        "minimum_identity_assurance":policy.minimum_identity_assurance,
    })
    out["governance_bundle_hash"]=governance_bundle_hash(out)
    if not is_auditable_verified_case(out,required_reviewers=policy.required_reviewers_per_case,require_governance_hash=True,minimum_identity_assurance=policy.minimum_identity_assurance):
        raise ValueError("promoted consensus failed auditable review validation")
    return out


def adjudicate_review_conflict(case:dict[str,Any],decisions:Iterable[dict[str,Any]],adjudication:dict[str,Any],*,policy:ReviewPolicy|None=None,identity_provider:ReviewerIdentityProvider|None=None)->dict[str,Any]:
    policy=policy or ReviewPolicy(required_reviewers_per_case=2);decisions=list(decisions);consensus=evaluate_review_consensus(case,decisions,policy=policy,identity_provider=identity_provider)
    if consensus.status!="review_conflict":raise ValueError("adjudication requires a review_conflict")
    adjudicator=str(adjudication.get("reviewer_id") or "").strip()
    if adjudicator in set(consensus.reviewer_ids):raise ValueError("adjudicator must be distinct from reviewers")
    errors=list(validate_review_decision(adjudication,case));verdict=str(adjudication.get("expected_verdict") or "")
    try:parse_reviewed_at(adjudication.get("reviewed_at"))
    except ValueError as exc:errors.append(str(exc))
    if verdict not in _VALID_VERDICTS:errors.append("invalid_expected_verdict")
    if identity_provider is not None:
        identity=identity_provider.resolve(adjudicator)
        if not _identity_ok(identity,policy,policy.adjudicator_role):errors.append("invalid_adjudicator_identity_role_or_assurance")
    elif policy.require_identity_registry or policy.minimum_identity_assurance!="unverified":errors.append("identity_provider_required_for_adjudicator_assurance")
    if errors:raise ValueError(",".join(dict.fromkeys(errors)))
    case_hash=review_case_fingerprint(case)
    records=[]
    for x in decisions:
        reviewer=str(x.get("reviewer_id") or "").strip()
        identity=identity_provider.resolve(reviewer) if identity_provider is not None else None
        records.append(_record(x,case_hash,str(getattr(identity,"assurance_level","unverified"))))
    adj_identity=identity_provider.resolve(adjudicator) if identity_provider is not None else None
    adjudication_record=_record(adjudication,case_hash,str(getattr(adj_identity,"assurance_level","unverified")));adjudication_record["review_hash"]=adjudication_record_hash(adjudication_record)
    acceptable=sorted(set(adjudication.get("acceptable_verdicts") or [verdict]))
    if verdict not in acceptable:acceptable.append(verdict);acceptable.sort()
    out=dict(case)
    out.update({
        "review_status":"verified","expected_verdict":verdict,"acceptable_verdicts":acceptable,
        "independent_human_review":True,"reviewed_at":adjudication_record["reviewed_at"],
        "reviewer_id":",".join(consensus.reviewer_ids+[adjudicator]),
        "reviewer_note":adjudication_record["reviewer_note"],"review_case_hash":case_hash,
        "review_records":records,"adjudication_record":adjudication_record,
        "review_policy_version":policy.policy_version,
        "required_reviewers_per_case":policy.required_reviewers_per_case,
        "minimum_identity_assurance":policy.minimum_identity_assurance,
    })
    out["governance_bundle_hash"]=governance_bundle_hash(out)
    if not is_auditable_verified_case(out,required_reviewers=policy.required_reviewers_per_case,require_governance_hash=True,minimum_identity_assurance=policy.minimum_identity_assurance):
        raise ValueError("adjudicated case failed auditable review validation")
    return out


def review_status_report(dataset_path:str|Path,decisions_path:str|Path|None=None)->dict[str,Any]:
    cases={str(case.get("id") or ""):case for _,case in iter_jsonl(dataset_path) if str(case.get("id") or "")};states=Counter(str(case.get("review_status") or "unknown") for case in cases.values());reviewer_counts=Counter();conflicts=0
    if decisions_path is not None:
        grouped=defaultdict(list)
        for _,decision in iter_jsonl(decisions_path):grouped[str(decision.get("case_id") or "")].append(decision)
        for case_id,rows in grouped.items():
            if case_id not in cases:continue
            reviewer_counts[case_id]=len({str(row.get("reviewer_id") or "").strip() for row in rows if str(row.get("reviewer_id") or "").strip()})
            if len({str(x.get("expected_verdict") or "") for x in rows if x.get("expected_verdict")})>1:conflicts+=1
    return {"total":len(cases),"machine_prepared":states["machine_prepared"],"human_required":states["human_required"],"verified":states["verified"],"auditable_verified":sum(1 for case in cases.values() if is_auditable_verified_case(case)),"reviewed_once":sum(1 for n in reviewer_counts.values() if n==1),"reviewed_twice_or_more":sum(1 for n in reviewer_counts.values() if n>=2),"review_conflicts":conflicts,"rejected":states["rejected"]}


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(prog="political-review-governance");sub=parser.add_subparsers(dest="command",required=True);status=sub.add_parser("status");status.add_argument("dataset");status.add_argument("--decisions");args=parser.parse_args(argv);print(json.dumps(review_status_report(args.dataset,args.decisions),ensure_ascii=False,indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
