from __future__ import annotations
import json
from pathlib import Path
import pytest
from political_core.review import apply_review_decision,apply_review_file,case_fingerprint,export_review_templates,review_template


def case(case_id="c1", preparer="machine-a"):
    return {
        "id":case_id,"claim":"یک ادعای سیاسی","language":"fa","claim_type":"event","category":"appointment",
        "reference_date":"2026-08-16","candidate_verdict":"true","expected_verdict":None,"acceptable_verdicts":[],
        "ground_truth_sources":["https://example.gov/doc/1"],"ground_truth_notes":"منبع برای بازبینی آماده است",
        "review_status":"machine_prepared","independent_human_review":False,"reviewed_at":None,
        "tags":["appointment"],"preparer_id":preparer,
    }


def decision(c, **kw):
    out={"case_id":c["id"],"case_fingerprint":case_fingerprint(c),"reviewer_id":"human-b","reviewed_at":"2026-08-16T08:00:00+03:30","expected_verdict":"true","acceptable_verdicts":["true","mostly_true"],"reviewer_note":"منبع اصلی و متن ادعا مستقل بررسی شد."}
    out.update(kw);return out


def test_fingerprint_changes_when_ground_truth_changes():
    a=case();b=case();b["ground_truth_sources"]=["https://example.gov/doc/2"]
    assert case_fingerprint(a)!=case_fingerprint(b)


def test_review_template_is_non_authoritative():
    c=case();t=review_template(c)
    assert t["case_id"]==c["id"] and t["case_fingerprint"]==case_fingerprint(c)
    assert t["reviewer_id"]=="" and t["reviewer_note"]==""


def test_independent_reviewer_required():
    c=case(preparer="alice")
    with pytest.raises(ValueError,match="reviewer_must_be_independent"):
        apply_review_decision(c,decision(c,reviewer_id="ALICE"))


def test_stale_fingerprint_rejected():
    c=case();d=decision(c);c["claim"]="ادعای تغییر کرده"
    with pytest.raises(ValueError,match="stale_or_wrong_case_fingerprint"):
        apply_review_decision(c,d)


def test_apply_records_reviewer_and_hash():
    c=case();out=apply_review_decision(c,decision(c))
    assert out["review_status"]=="verified" and out["independent_human_review"] is True
    assert out["reviewer_id"]=="human-b" and out["review_case_hash"]==case_fingerprint(c)
    assert out["expected_verdict"]=="true"


def test_batch_review_is_atomic_on_validation_error(tmp_path:Path):
    source=tmp_path/"source.jsonl";decisions=tmp_path/"decisions.jsonl";output=tmp_path/"output.jsonl"
    c=case();source.write_text(json.dumps(c,ensure_ascii=False)+"\n",encoding="utf-8")
    decisions.write_text(json.dumps(decision(c,case_fingerprint="bad"),ensure_ascii=False)+"\n",encoding="utf-8")
    report=apply_review_file(source,decisions,output)
    assert not report.ok and report.applied==0 and not output.exists()


def test_export_and_apply_roundtrip(tmp_path:Path):
    source=tmp_path/"source.jsonl";templates=tmp_path/"templates.jsonl";decisions=tmp_path/"decisions.jsonl";output=tmp_path/"out.jsonl"
    c=case();source.write_text(json.dumps(c,ensure_ascii=False)+"\n",encoding="utf-8")
    summary=export_review_templates(source,templates);assert summary["templates"]==1
    t=json.loads(templates.read_text(encoding="utf-8"));t.update(decision(c))
    decisions.write_text(json.dumps(t,ensure_ascii=False)+"\n",encoding="utf-8")
    report=apply_review_file(source,decisions,output)
    assert report.ok and report.applied==1
    promoted=json.loads(output.read_text(encoding="utf-8"))
    assert promoted["review_status"]=="verified" and promoted["reviewer_id"]=="human-b"


def test_verified_without_audit_metadata_not_production_eligible(tmp_path:Path):
    from political_core.dataset import validate_jsonl
    c=case();c.update({"review_status":"verified","expected_verdict":"true","acceptable_verdicts":["true"],"independent_human_review":True,"reviewed_at":"2026-08-16T08:00:00+03:30","ground_truth_notes":"human checked"})
    p=tmp_path/"verified.jsonl";p.write_text(json.dumps(c,ensure_ascii=False)+"\n",encoding="utf-8")
    report=validate_jsonl(p)
    assert report.valid and report.verified_cases==1 and report.auditable_verified_cases==0
    assert report.review_audit_failures==["c1"] and not report.production_benchmark_ready
