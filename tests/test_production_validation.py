from __future__ import annotations
import sqlite3
from pathlib import Path

from political_core.application import PoliticalApplication
from political_core.benchmark import calibration_report
from political_core.cache import SQLiteCache
from political_core.cache_backend import MemoryCache,NamespacedCache
from political_core.claims import analyze_claims,plan_queries
from political_core.dataset import validate_case,validate_jsonl
from political_core.engine import FactCheckEngine
from political_core.entity import extract_entities
from political_core.models import Evidence,EvidenceStance,FactCheckResult,ReasoningDecision,SearchResult,SourceKind,SourceRole,TimelineEvent,Verdict
from political_core.primary_source import AuthorityRegistry,PrimarySourceAssessor
from political_core.provenance import assign_source_chains,independent_source_count
from political_core.telegram_adapter import TelegramAdapter
from political_core.timeline import active_role_events,derive_current_roles


def ev(i,domain,text,**kw):
    return Evidence(f"E{i}",f"https://{domain}/{i}",text,domain,text,kw.pop("published_at",None),SourceKind.NEWSROOM,.7,domain,source_role=SourceRole.SECONDARY_REPORTING,**kw)


def test_review_queue_100_cases_and_16_categories():
    r=validate_jsonl(Path("evals/cases/persian_political_review_queue.jsonl.gz"))
    assert r.valid and r.total_cases==100 and r.review_queue_ready
    assert r.verified_cases==0 and not r.production_benchmark_ready
    assert len(r.category_counts)==16 and all(v>=5 for v in r.category_counts.values())


def test_verified_dataset_record_requires_real_human_review():
    case={"id":"x","claim":"ادعا","language":"fa","claim_type":"event","category":"appointment","review_status":"verified","expected_verdict":"true","ground_truth_sources":["https://example.org/doc"],"ground_truth_notes":"doc","independent_human_review":False,"reviewed_at":"2026-01-01","tags":["appointment"]}
    assert "verified_case_requires_independent_human_review" in validate_case(case)


def test_query_cleanup_and_budget():
    qs=plan_queries(analyze_claims("سلام، لطفاً آیا محمدباقر ذوالقدر با حکم رئیس‌جمهور دبیر شورای عالی امنیت ملی شد؟"),2)
    joined=" ".join(q.text for q in qs)
    assert len(qs)<=2 and "محمدباقر ذوالقدر" in joined and "لطفاً" not in joined
    assert plan_queries(analyze_claims("هیچ حکم انتصابی برای علی لاریجانی صادر نشده"),1)[0].purpose=="negative_existence"


def test_entity_aliases_and_location():
    refs=extract_entities("Mohammad Bagher Zolghadr در تهران درباره Iran صحبت کرد")
    assert any(x.canonical_name=="محمدباقر ذوالقدر" and x.entity_type=="person" for x in refs)
    assert any(x.canonical_name=="ایران" and x.entity_type=="country" for x in refs)
    assert any(x.canonical_name=="تهران" and x.entity_type=="location" for x in refs)


def test_timeline_preserves_distinct_simultaneous_roles():
    rows=[TimelineEvent("الف","دبیر شورای عالی امنیت ملی","appointment","P1","شورای عالی امنیت ملی","2024-01-01T00:00:00+00:00"),TimelineEvent("الف","نماینده در شورای عالی امنیت ملی","appointment","P1","شورای عالی امنیت ملی","2024-02-01T00:00:00+00:00"),TimelineEvent("الف","دبیر شورای عالی امنیت ملی","appointment","P1","شورای عالی امنیت ملی","2025-01-01T00:00:00+00:00")]
    roles=derive_current_roles(rows)["P1"]
    assert roles[0].end_date=="2025-01-01T00:00:00+00:00" and roles[1].end_date is None
    assert len(active_role_events(rows))==2


def test_primary_precision_rejects_mirror_and_issuer_mismatch():
    a=PrimarySourceAssessor(AuthorityRegistry({"records.example.gov":"Agency","agency.example.gov":"Agency"}))
    good=SearchResult("https://records.example.gov/decree/1","متن حکم","حکم انتصاب",source_kind=SourceKind.PRIMARY_DOCUMENT,issuer_hint="Agency",document_type_hint="decree")
    assert a.assess(good,good.snippet).is_primary
    mirror=SearchResult("https://agency.example.gov/news/1","متن حکم","به گزارش خبرگزاری دیگر، متن حکم انتصاب",source_kind=SourceKind.PRIMARY_DOCUMENT,issuer_hint="Agency",document_type_hint="decree")
    assert not a.assess(mirror,mirror.snippet).is_primary
    wrong=SearchResult("https://records.example.gov/decree/2","متن حکم","حکم انتصاب",source_kind=SourceKind.PRIMARY_DOCUMENT,issuer_hint="Other Ministry",document_type_hint="decree")
    assert not a.assess(wrong,wrong.snippet).is_primary


def test_cross_domain_near_verbatim_is_one_source_chain():
    p="این گزارش سیاسی شامل جزئیات یکسان و جمله‌های مشخص درباره یک رویداد عمومی است و برای تشخیص بازنشر طول کافی دارد. "
    rows=assign_source_chains([ev(1,"alpha.example",p*2,published_at="2026-01-01T10:00:00+00:00"),ev(2,"beta.example",p*2,published_at="2026-01-01T11:00:00+00:00")])
    assert rows[0].source_chain_id==rows[1].source_chain_id and independent_source_count(rows)==1


def test_cache_backend_defensive_and_namespaced():
    c=MemoryCache(1);c.set("a",{"x":[1]});v=c.get("a",60);v["x"].append(2);assert c.get("a",60)=={"x":[1]}
    inner=MemoryCache();a=NamespacedCache(inner,"a");b=NamespacedCache(inner,"b");a.set("x",{"v":1});b.set("x",{"v":2});assert a.get("x",60)!=b.get("x",60)


def test_calibration_false_high_confidence():
    r=calibration_report([{"confidence":.95,"actual_verdict":"false","expected_verdict":"true"},{"confidence":.9,"actual_verdict":"true","expected_verdict":"true"}])
    assert r["false_high_confidence_rate"]==.5 and r["expected_calibration_error"] is not None


class SearchDown:
    def search(self,q,limit):raise RuntimeError("down")
class SearchOne:
    def search(self,q,limit):return [SearchResult("https://news.example/x","خبر","شاهد",source_kind=SourceKind.NEWSROOM)]
class Reason:
    def __init__(self,fail=False):self.fail=fail
    def evaluate(self,claim,evidence):
        if self.fail:raise TimeoutError("timeout")
        return ReasoningDecision(Verdict.TRUE,.9,"ok",citation_ids=["E1"],evidence_stances={"E1":EvidenceStance.SUPPORTS})


def test_failure_matrix_and_corrupt_cache(tmp_path):
    r=FactCheckEngine(SearchDown(),Reason()).check("ادعا");assert r.verdict==Verdict.UNVERIFIED
    r=FactCheckEngine(SearchOne(),Reason(True)).check("ادعا");assert r.verdict==Verdict.VERIFICATION_UNAVAILABLE
    db=tmp_path/"c.db";cache=SQLiteCache(db);cache.set("x",{"ok":1})
    with sqlite3.connect(db) as conn:conn.execute("UPDATE fact_cache SET payload='bad' WHERE cache_key='x'")
    assert cache.get("x",60) is None


class AppEngine:
    def __init__(self):self.modes=[]
    def check(self,claim,mode="quick",refresh=False):
        self.modes.append(mode);return FactCheckResult(claim,claim,Verdict.TRUE,.8,"ok",[],"",[],[])


def test_telegram_adapter_has_no_fact_check_business_logic():
    engine=AppEngine();adapter=TelegramAdapter(PoliticalApplication(engine))
    assert "شناسه نتیجه" in adapter.handle("u","/check ادعا") and engine.modes[-1]=="quick"
    adapter.handle("u","/deep ادعا");assert engine.modes[-1]=="deep"
