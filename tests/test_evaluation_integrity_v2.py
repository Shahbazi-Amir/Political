from __future__ import annotations
import gzip,json
from pathlib import Path
import pytest

from political_core.application import PoliticalApplication
from political_core.benchmark_report import build_benchmark_report,load_benchmark_report
from political_core.benchmark_runner import run_benchmark
from political_core.dataset import is_auditable_verified_case,review_case_fingerprint,validate_jsonl
from political_core.dataset_manifest import build_dataset_manifest
from political_core.evals import evaluate_records
from political_core.models import FactCheckResult,Verdict
from political_core.readiness import assess_from_artifacts
from political_core.release_evidence import ci_report,live_report,load_report
from political_core.review import apply_review_decision
from political_core.review_governance import ReviewPolicy,adjudicate_review_conflict,promote_consensus

REVIEWED_AT="2026-08-16T00:00:00+00:00"

def base_case(case_id="c1",category="appointment"):
    return {"id":case_id,"claim":"ادعا","language":"fa","claim_type":"event","category":category,"review_status":"human_required","candidate_verdict":"true","ground_truth_sources":["https://example.org/doc"],"ground_truth_notes":"checked source","independent_human_review":False,"reviewed_at":None,"acceptable_verdicts":[],"tags":[category],"preparer_id":"prep","split":"evaluation"}

def decision(case,reviewer="r1",verdict="true",acceptable=None,note="checked"):
    return {"case_id":case["id"],"case_fingerprint":review_case_fingerprint(case),"reviewer_id":reviewer,"reviewed_at":REVIEWED_AT,"expected_verdict":verdict,"acceptable_verdicts":acceptable or [verdict],"reviewer_note":note}

def test_category_not_double_counted_through_tags():
    row={"category":"appointment","tags":["appointment"],"expected_verdict":"true","actual_verdict":"true","confidence":.7,"citation_ids":[],"available_evidence_ids":[]}
    result=evaluate_records([row],records_are_joined=True)
    assert result["critical_category_counts"]["appointment"]==1

def test_category_minimum_cannot_be_satisfied_by_double_counting():
    rows=[]
    categories=("appointment","dismissal","membership","current_status","constitutional","legal","quote","negative_claim","breaking_news_like","copied_sources","conflicting_sources","official_statement_vs_fact","outdated_claim","misleading","missing_context","causal_argument")
    for category in categories:
        for i in range(3):
            rows.append({"category":category,"tags":[category],"expected_verdict":"true","actual_verdict":"true","confidence":.7,"citation_ids":[],"available_evidence_ids":[]})
    for i in range(60):
        rows.append({"category":"appointment","tags":["appointment"],"expected_verdict":"true","actual_verdict":"true","confidence":.7,"citation_ids":[],"available_evidence_ids":[]})
    result=evaluate_records(rows,records_are_joined=True)
    assert len(rows)>100 and result["critical_category_counts"]["dismissal"]==3 and result["benchmark_sample_sufficient"] is False

def test_review_timestamp_must_be_valid_and_timezone_aware():
    c=base_case()
    bad=decision(c);bad["reviewed_at"]="banana"
    with pytest.raises(ValueError):apply_review_decision(c,bad)
    bad=decision(c);bad["reviewed_at"]="2026-08-16T00:00:00"
    with pytest.raises(ValueError):apply_review_decision(c,bad)
    bad=decision(c);bad["reviewed_at"]="2999-01-01T00:00:00+00:00"
    with pytest.raises(ValueError):apply_review_decision(c,bad)

def test_two_reviewer_policy_rejects_single_review():
    c=base_case();single=apply_review_decision(c,decision(c))
    assert is_auditable_verified_case(single)
    assert not is_auditable_verified_case(single,required_reviewers=2)

def test_review_record_tampering_invalidates_audit():
    c=base_case();out=promote_consensus(c,[decision(c,"r1"),decision(c,"r2")],policy=ReviewPolicy(2))
    assert is_auditable_verified_case(out,required_reviewers=2)
    out["review_records"][0]["reviewer_note"]="tampered"
    assert not is_auditable_verified_case(out,required_reviewers=2)

def test_adjudication_tampering_invalidates_audit():
    c=base_case();rows=[decision(c,"r1","true"),decision(c,"r2","false")]
    out=adjudicate_review_conflict(c,rows,decision(c,"adj","true",note="adjudicated"),policy=ReviewPolicy(2))
    assert is_auditable_verified_case(out,required_reviewers=2)
    out["adjudication_record"]["expected_verdict"]="false"
    assert not is_auditable_verified_case(out,required_reviewers=2)

def test_acceptable_verdict_consensus_uses_intersection():
    c=base_case();rows=[decision(c,"r1","true",["true","mostly_true"]),decision(c,"r2","true",["true","missing_context"])]
    out=promote_consensus(c,rows,policy=ReviewPolicy(2))
    assert out["acceptable_verdicts"]==["true"]

def test_canonical_dataset_hash_ignores_gzip_metadata(tmp_path):
    row=base_case()
    raw=(json.dumps(row,ensure_ascii=False,separators=(",",":"))+"\n").encode()
    a=tmp_path/"a.jsonl.gz";b=tmp_path/"b.jsonl.gz"
    with gzip.GzipFile(filename=str(a),mode="wb",mtime=1) as h:h.write(raw)
    with gzip.GzipFile(filename=str(b),mode="wb",mtime=2) as h:h.write(raw)
    ma=build_dataset_manifest(a);mb=build_dataset_manifest(b)
    assert ma.file_sha256!=mb.file_sha256
    assert ma.canonical_content_sha256==mb.canonical_content_sha256
    assert ma.dataset_version==mb.dataset_version

def test_source_record_changes_review_fingerprint():
    c=base_case();c["ground_truth_source_records"]=[{"url":"https://example.org/doc","canonical_url":"https://example.org/doc","retrieved_at":REVIEWED_AT,"content_sha256":"a"*64}]
    first=review_case_fingerprint(c);c["ground_truth_source_records"][0]["content_sha256"]="b"*64
    assert review_case_fingerprint(c)!=first

class FakeEngine:
    def check(self,claim,mode="quick",refresh=False,reference_date=None):
        return FactCheckResult(claim,claim,Verdict.TRUE,.8,"ok",[],"",[],[])

def test_benchmark_runner_keeps_ground_truth_immutable_and_predictions_separate(tmp_path):
    c=base_case();verified=apply_review_decision(c,decision(c));dataset=tmp_path/"dataset.jsonl";pred=tmp_path/"pred.jsonl"
    dataset.write_text(json.dumps(verified,ensure_ascii=False)+"\n",encoding="utf-8");before=dataset.read_bytes()
    report=run_benchmark(dataset,PoliticalApplication(FakeEngine()),pred,split="evaluation")
    assert dataset.read_bytes()==before and report["prediction_cases"]==1
    row=json.loads(pred.read_text(encoding="utf-8"))
    assert row["case_id"]=="c1" and "expected_verdict" not in row and "claim" not in row

def test_benchmark_report_schema_is_loadable(tmp_path):
    dataset=Path("evals/cases/persian_political_review_queue.jsonl.gz");path=tmp_path/"report.json"
    report=build_benchmark_report(dataset,git_sha="abc");path.write_text(json.dumps(report),encoding="utf-8")
    loaded=load_benchmark_report(path);assert loaded["git_sha"]=="abc" and loaded["schema_version"]==2

def test_release_evidence_must_share_git_sha(tmp_path):
    dataset=Path("evals/cases/persian_political_review_queue.jsonl.gz")
    bench=build_benchmark_report(dataset,git_sha="A")
    paths={}
    for name,data in {
        "ci":ci_report("A",software_tests_pass=True,security_tests_pass=True),
        "bench":bench,
        "live":live_report("B",configuration_available=True,quick_status="passed",deep_status="passed"),
        "load":load_report("A",status="passed"),
    }.items():
        p=tmp_path/f"{name}.json";p.write_text(json.dumps(data),encoding="utf-8");paths[name]=p
    result=assess_from_artifacts(dataset,ci_report=paths["ci"],benchmark_report=paths["bench"],live_report=paths["live"],load_report=paths["load"])
    assert result.production_ready is False and result.evidence_artifacts_consistent is False and "release_evidence_mismatch" in result.blockers

def test_production_dataset_gate_requires_source_snapshots(tmp_path):
    c=base_case();verified=apply_review_decision(c,decision(c));p=tmp_path/"one.jsonl"
    p.write_text(json.dumps(verified,ensure_ascii=False)+"\n",encoding="utf-8")
    report=validate_jsonl(p)
    assert report.auditable_verified_cases==1 and report.source_snapshot_verified_cases==0
    verified["ground_truth_source_records"]=[{"url":"https://example.org/doc","canonical_url":"https://example.org/doc","retrieved_at":REVIEWED_AT,"content_sha256":"a"*64}]
    # Source snapshot fields are part of the reviewed fingerprint, so adding them after review invalidates audit.
    p.write_text(json.dumps(verified,ensure_ascii=False)+"\n",encoding="utf-8")
    report=validate_jsonl(p)
    assert report.auditable_verified_cases==0

def test_benchmark_report_with_predictions_requires_matching_run_manifest(tmp_path):
    c=base_case();verified=apply_review_decision(c,decision(c));dataset=tmp_path/"dataset.jsonl";pred=tmp_path/"pred.jsonl"
    dataset.write_text(json.dumps(verified,ensure_ascii=False)+"\n",encoding="utf-8")
    run_benchmark(dataset,PoliticalApplication(FakeEngine()),pred,split="evaluation",git_sha="abc")
    report=build_benchmark_report(dataset,git_sha="abc",predictions_path=pred)
    assert report["prediction_artifact"]["run_id"] and report["metrics"]["prediction_cases"]==1
    with pytest.raises(ValueError,match="Git SHA mismatch"):
        build_benchmark_report(dataset,git_sha="other",predictions_path=pred)
