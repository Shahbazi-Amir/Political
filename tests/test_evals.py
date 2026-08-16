from __future__ import annotations

import json
from pathlib import Path

from political_core.dataset import review_case_fingerprint
from political_core.evals import evaluate_jsonl


def auditable(**updates):
    row={"id":"x","claim":"ادعا","language":"fa","claim_type":"event","category":"appointment","reference_date":"2026-08-16","candidate_verdict":"true","ground_truth_sources":["https://example.gov/doc"],"ground_truth_notes":"source note","tags":["appointment"],"preparer_id":"machine","review_status":"verified","independent_human_review":True,"reviewed_at":"2026-08-16","reviewer_id":"human","reviewer_note":"checked","expected_verdict":"true","actual_verdict":"true","acceptable_verdicts":["true"],"confidence":.9,"citation_ids":["E1"],"available_evidence_ids":["E1"]}
    row.update(updates);row["review_case_hash"]=review_case_fingerprint(row);return row


def test_unreviewed_dataset_does_not_claim_accuracy(tmp_path:Path):
    p=tmp_path/"x.jsonl";p.write_text(json.dumps({"claim":"x","review_status":"human_required","expected_verdict":"true"})+"\n")
    r=evaluate_jsonl(p);assert r["production_accuracy_established"] is False;assert r["verified_cases"]==0


def test_missing_review_status_never_defaults_to_verified(tmp_path:Path):
    p=tmp_path/"x.jsonl";p.write_text(json.dumps({"expected_verdict":"true","actual_verdict":"true","ground_truth_sources":["doc"]})+"\n")
    r=evaluate_jsonl(p);assert r["verified_cases"]==0


def test_false_high_confidence_metric_uses_only_auditable_reviews(tmp_path:Path):
    a=auditable(id="a",actual_verdict="false");b=auditable(id="b",actual_verdict="true")
    p=tmp_path/"x.jsonl";p.write_text("\n".join(json.dumps(x) for x in (a,b)),encoding="utf-8");r=evaluate_jsonl(p)
    assert r["verified_cases"]==2;assert r["false_high_confidence_rate"]==.5;assert r["citation_validity"]==1.0;assert r["production_accuracy_established"] is False


def test_verified_case_without_ground_truth_is_rejected(tmp_path:Path):
    row=auditable();row["ground_truth_sources"]=[]
    p=tmp_path/"x.jsonl";p.write_text(json.dumps(row)+"\n");r=evaluate_jsonl(p)
    assert r["verified_cases"]==0;assert r["invalid_verified_cases"][0]["reason"]=="verified_case_missing_ground_truth_sources"


def test_verified_case_without_review_hash_is_rejected_from_metrics(tmp_path:Path):
    row=auditable();row.pop("review_case_hash")
    p=tmp_path/"x.jsonl";p.write_text(json.dumps(row,ensure_ascii=False)+"\n",encoding="utf-8");r=evaluate_jsonl(p)
    assert r["verified_cases"]==0;assert r["invalid_verified_cases"][0]["reason"]=="verified_case_not_auditable"


def test_tampered_reviewed_claim_is_rejected_from_metrics(tmp_path:Path):
    row=auditable();row["claim"]="متن پس از review تغییر کرده"
    p=tmp_path/"x.jsonl";p.write_text(json.dumps(row,ensure_ascii=False)+"\n",encoding="utf-8");r=evaluate_jsonl(p)
    assert r["verified_cases"]==0;assert r["invalid_verified_cases"][0]["reason"]=="verified_case_not_auditable"
