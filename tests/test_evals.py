from __future__ import annotations

import json
from pathlib import Path

from political_core.evals import evaluate_jsonl


def test_unreviewed_dataset_does_not_claim_accuracy(tmp_path:Path):
    p=tmp_path/"x.jsonl";p.write_text(json.dumps({"claim":"x","review_status":"human_required","expected_verdict":"true"})+"\n")
    r=evaluate_jsonl(p);assert r["production_accuracy_established"] is False;assert r["verified_cases"]==0


def test_missing_review_status_never_defaults_to_verified(tmp_path:Path):
    p=tmp_path/"x.jsonl";p.write_text(json.dumps({"expected_verdict":"true","actual_verdict":"true","ground_truth_sources":["doc"]})+"\n")
    r=evaluate_jsonl(p);assert r["verified_cases"]==0


def test_false_high_confidence_metric(tmp_path:Path):
    rows=[
        {"review_status":"verified","ground_truth_sources":["doc-a"],"expected_verdict":"true","actual_verdict":"false","confidence":.9,"citation_ids":["E1"],"available_evidence_ids":["E1"]},
        {"review_status":"verified","ground_truth_sources":["doc-b"],"expected_verdict":"true","actual_verdict":"true","confidence":.9,"citation_ids":["E1"],"available_evidence_ids":["E1"]},
    ]
    p=tmp_path/"x.jsonl";p.write_text("\n".join(json.dumps(x) for x in rows));r=evaluate_jsonl(p)
    assert r["false_high_confidence_rate"]==.5;assert r["citation_validity"]==1.0;assert r["production_accuracy_established"] is False


def test_verified_case_without_ground_truth_is_rejected(tmp_path:Path):
    row={"review_status":"verified","expected_verdict":"true","actual_verdict":"true","confidence":.8}
    p=tmp_path/"x.jsonl";p.write_text(json.dumps(row)+"\n");r=evaluate_jsonl(p)
    assert r["verified_cases"]==0;assert r["invalid_verified_cases"][0]["reason"]=="verified_case_missing_ground_truth_sources"
