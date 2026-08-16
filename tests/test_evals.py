from __future__ import annotations
import json
from pathlib import Path
from political_core.evals import evaluate_jsonl
def test_unreviewed_dataset_does_not_claim_accuracy(tmp_path:Path):
    p=tmp_path/"x.jsonl";p.write_text(json.dumps({"claim":"x","review_status":"human_required","expected_verdict":"true"})+"\n");r=evaluate_jsonl(p);assert r["production_accuracy_established"] is False;assert r["verified_cases"]==0
def test_false_high_confidence_metric(tmp_path:Path):
    rows=[{"review_status":"verified","expected_verdict":"true","actual_verdict":"false","confidence":.9,"citation_ids":["E1"],"available_evidence_ids":["E1"]},{"review_status":"verified","expected_verdict":"true","actual_verdict":"true","confidence":.9,"citation_ids":["E1"],"available_evidence_ids":["E1"]}];p=tmp_path/"x.jsonl";p.write_text("\n".join(json.dumps(x) for x in rows));r=evaluate_jsonl(p);assert r["false_high_confidence_rate"]==.5;assert r["citation_validity"]==1.0
