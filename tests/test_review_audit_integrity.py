from __future__ import annotations
import json
from political_core.dataset import is_auditable_verified_case,review_case_fingerprint
from political_core.primary_eval import primary_source_metrics
from political_core.review import apply_review_decision


def base_case():
    return {"id":"r1","claim":"ادعا","language":"fa","claim_type":"event","category":"appointment","reference_date":"2026-08-16","candidate_verdict":"true","expected_verdict":None,"acceptable_verdicts":[],"ground_truth_sources":["https://example.gov/doc"],"ground_truth_notes":"source note","review_status":"machine_prepared","independent_human_review":False,"reviewed_at":None,"tags":["appointment"],"preparer_id":"machine-a"}


def review(case):
    return {"case_id":case["id"],"case_fingerprint":review_case_fingerprint(case),"reviewer_id":"human-b","reviewed_at":"2026-08-16T08:00:00+03:30","expected_verdict":"true","acceptable_verdicts":["true"],"reviewer_note":"independently checked source and wording"}


def test_review_promotion_preserves_ground_truth_and_hash_is_recomputable():
    case=base_case();source_note=case["ground_truth_notes"];out=apply_review_decision(case,review(case))
    assert out["ground_truth_notes"]==source_note
    assert out["reviewer_note"]=="independently checked source and wording"
    assert out["review_case_hash"]==review_case_fingerprint(out)
    assert is_auditable_verified_case(out)


def test_post_review_case_tampering_invalidates_audit():
    case=base_case();out=apply_review_decision(case,review(case));out["claim"]="ادعای تغییر یافته پس از review"
    assert not is_auditable_verified_case(out)


def test_preparer_identity_is_inside_review_fingerprint():
    a=base_case();b=base_case();b["preparer_id"]="machine-other"
    assert review_case_fingerprint(a)!=review_case_fingerprint(b)


def test_primary_metrics_reject_structurally_verified_but_non_auditable_row():
    raw=base_case();raw.update({"review_status":"verified","independent_human_review":True,"reviewed_at":"2026-08-16","expected_verdict":"true","reviewer_note":"x","expected_primary":True,"actual_primary":True})
    metrics=primary_source_metrics([raw])
    assert metrics["reviewed_cases"]==0 and metrics["rejected_non_auditable_verified"]==1
    assert metrics["production_precision_established"] is False


def test_primary_metrics_accept_auditable_reviewed_row():
    case=base_case();out=apply_review_decision(case,review(case));out.update({"expected_primary":True,"actual_primary":True})
    metrics=primary_source_metrics([out])
    assert metrics["reviewed_cases"]==1 and metrics["tp"]==1 and metrics["precision"]==1.0
