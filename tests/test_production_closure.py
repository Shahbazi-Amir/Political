from __future__ import annotations
import json
from pathlib import Path
import pytest
from political_core.application import PoliticalApplication
from political_core.benchmark_report import build_benchmark_report
from political_core.cache_backend import RedisCache,build_cache_backend
from political_core.dataset import review_case_fingerprint
from political_core.dataset_manifest import build_dataset_manifest
from political_core.evals import evaluate_jsonl
from political_core.loadtest import run_load_test
from political_core.models import FactCheckResult,Verdict
from political_core.observability import JsonlMetricsSink,MemoryMetricsSink
from political_core.rate_limit import ConcurrencyLimiter,SlidingWindowRateLimiter
from political_core.readiness import QualityGates,assess_release_readiness
from political_core.review_governance import ReviewPolicy,adjudicate_review_conflict,evaluate_review_consensus,promote_consensus
from political_core.reviewer_identity import StaticReviewerRegistry
from political_core.telegram_adapter import TelegramAdapter
QUEUE=Path("evals/cases/persian_political_review_queue.jsonl.gz")
def case():return {"id":"c1","claim":"ادعا","language":"fa","claim_type":"event","category":"appointment","review_status":"human_required","candidate_verdict":"true","ground_truth_sources":["https://example.org/doc"],"ground_truth_notes":"primary doc","independent_human_review":False,"reviewed_at":None,"acceptable_verdicts":[],"tags":["appointment"],"preparer_id":"prep"}
def decision(c,reviewer,verdict="true",note="checked"):return {"case_id":c["id"],"case_fingerprint":review_case_fingerprint(c),"reviewer_id":reviewer,"reviewed_at":"2026-08-16T00:00:00Z","expected_verdict":verdict,"acceptable_verdicts":[verdict],"reviewer_note":note}
def registry():return StaticReviewerRegistry({"r1":{"roles":["reviewer"]},"r2":{"roles":["reviewer"]},"adj":{"roles":["adjudicator"]},"off":{"roles":["reviewer"],"active":False}})
def test_two_reviewer_consensus_is_auditable():
    c=case();ds=[decision(c,"r1"),decision(c,"r2")];p=ReviewPolicy(2,True);reg=registry();consensus=evaluate_review_consensus(c,ds,policy=p,identity_provider=reg);assert consensus.verified and consensus.reviewer_ids==["r1","r2"];promoted=promote_consensus(c,ds,policy=p,identity_provider=reg);assert promoted["review_status"]=="verified" and len(promoted["review_records"])==2 and promoted["review_case_hash"]==review_case_fingerprint(c)
def test_review_conflict_requires_distinct_adjudicator():
    c=case();ds=[decision(c,"r1","true"),decision(c,"r2","false")];p=ReviewPolicy(2,True);reg=registry();assert evaluate_review_consensus(c,ds,policy=p,identity_provider=reg).status=="review_conflict"
    with pytest.raises(ValueError):adjudicate_review_conflict(c,ds,decision(c,"r1","true"),policy=p,identity_provider=reg)
    out=adjudicate_review_conflict(c,ds,decision(c,"adj","true","adjudicated"),policy=p,identity_provider=reg);assert out["expected_verdict"]=="true" and out["adjudication_record"]["reviewer_id"]=="adj"
def test_reviewer_registry_rejects_unknown_inactive_and_preparer():
    c=case();reg=registry();p=ReviewPolicy(1,True);assert evaluate_review_consensus(c,[decision(c,"missing")],policy=p,identity_provider=reg).status=="invalid";assert evaluate_review_consensus(c,[decision(c,"off")],policy=p,identity_provider=reg).status=="invalid";reg.add("prep",roles={"reviewer"});assert evaluate_review_consensus(c,[decision(c,"prep")],policy=p,identity_provider=reg).status=="invalid"
def test_dataset_manifest_is_stable_for_same_bytes():
    a=build_dataset_manifest(QUEUE);b=build_dataset_manifest(QUEUE);assert a.sha256==b.sha256 and a.dataset_version==b.dataset_version and a.total_cases==100
def test_evaluator_accepts_gzip_dataset_without_claiming_accuracy():
    result=evaluate_jsonl(QUEUE);assert result["verified_cases"]==0 and result["production_accuracy_established"] is False
def test_readiness_is_fail_closed_until_real_world_gates_pass():
    result=assess_release_readiness(QUEUE,software_tests_pass=True,security_tests_pass=True,require_live=False,require_load_test=False);assert not result.production_ready and "dataset_not_production_ready" in result.blockers and result.benchmark_gate=="insufficient_data"
def test_quality_gate_targets():
    gates=QualityGates();good={"citation_validity":1.0,"primary_source_precision_f1":.98,"false_high_confidence_rate":.01,"high_confidence_accuracy":.98};bad={**good,"false_high_confidence_rate":.2};assert gates.evaluate(good,sufficient_data=True)[0]=="pass";assert gates.evaluate(bad,sufficient_data=True)[0]=="fail"
def test_benchmark_report_is_reproducible_metadata_wrapper():
    report=build_benchmark_report(QUEUE,git_sha="abc123",model_name="model",search_provider="searxng");assert report["git_sha"]=="abc123" and report["dataset"]["sha256"] and report["metrics"]["production_accuracy_established"] is False
def test_load_harness_reports_failures_and_percentiles():
    def handler(x):
        if x==3:raise RuntimeError("boom")
        return x
    result=run_load_test(handler,[1,2,3,4],concurrency=2);assert result.requests==4 and result.successes==3 and result.failures==1 and result.p95_seconds is not None and result.error_rate==.25
def test_sliding_rate_limit_and_concurrency_limit():
    limiter=SlidingWindowRateLimiter(2,10);assert limiter.allow("u",now=0) and limiter.allow("u",now=1) and not limiter.allow("u",now=2) and limiter.allow("u",now=11);concurrency=ConcurrencyLimiter(1)
    with concurrency.slot() as first:
        assert first
        with concurrency.slot() as second:assert not second
class FakeRedis:
    def __init__(self):self.rows={}
    def get(self,key):return self.rows.get(key)
    def set(self,key,value):self.rows[key]=value
    def delete(self,key):self.rows.pop(key,None)
def test_optional_redis_cache_has_no_hard_dependency():
    fake=FakeRedis();cache=RedisCache(client=fake);cache.set("x",{"v":1});assert cache.get("x",60)=={"v":1};cache.delete("x");assert cache.get("x",60) is None
    with pytest.raises(ValueError):build_cache_backend("unsupported")
class AppEngine:
    def __init__(self):self.calls=0
    def check(self,claim,mode="quick",refresh=False,reference_date=None):self.calls+=1;return FactCheckResult(claim,claim,Verdict.UNVERIFIED,.2,"not enough",[],"uncertain",[],[])
def test_application_observability_excludes_raw_claim(tmp_path):
    engine=AppEngine();memory=MemoryMetricsSink();app=PoliticalApplication(engine,metrics=memory);response=app.check("SUPER_SECRET_CLAIM",request_id="req-1");assert response.request_id=="req-1" and memory.rows[0].request_id=="req-1";path=tmp_path/"metrics.jsonl";sink=JsonlMetricsSink(path);sink.emit(memory.rows[0]);raw=path.read_text();assert "SUPER_SECRET_CLAIM" not in raw and "Authorization" not in raw and "req-1" in raw
def test_telegram_rate_limit_is_transport_only():
    engine=AppEngine();adapter=TelegramAdapter(PoliticalApplication(engine),rate_limiter=SlidingWindowRateLimiter(1,60));first=adapter.handle("u","/check ادعا");second=adapter.handle("u","/check ادعای دوم");assert "شناسه نتیجه" in first and "زیاد" in second and engine.calls==1
