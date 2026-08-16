from __future__ import annotations
import tempfile
from pathlib import Path
from political_core.cache import SQLiteCache
from political_core.claims import analyze_claims,plan_queries
from political_core.engine import FactCheckEngine
from political_core.models import Budget,EvidenceStance,ReasoningDecision,SearchResult,SourceKind,Verdict
from political_core.primary_source import AuthorityRegistry
from political_core.source_policy import SourcePolicy
from political_core.text import canonical_url,normalize_text
class FakeSearch:
    def __init__(self,results):self.results=list(results);self.calls=[]
    def search(self,query,limit):self.calls.append(query);return self.results[:limit]
class FakeReasoner:
    def __init__(self,decision):self.decision=decision;self.calls=0
    def evaluate(self,claim,evidence):self.calls+=1;return self.decision
class DeepReasoner(FakeReasoner):
    def __init__(self,judge,critic):super().__init__(judge);self.critic_decision=critic;self.critic_calls=0
    def critique(self,claim,evidence,initial):self.critic_calls+=1;return self.critic_decision
def dec(verdict=Verdict.TRUE,conf=.9,citations=None,stances=None,**kwargs):return ReasoningDecision(verdict,conf,kwargs.get("summary","ok"),citation_ids=citations or ["E1"],evidence_stances=stances or {"E1":EvidenceStance.SUPPORTS},conflict_detected=kwargs.get("conflict_detected",False),uncertainty=kwargs.get("uncertainty",""))
def test_normalization_and_url():
    assert normalize_text("  علي\u200c رضا  كاظمي ۱۲۳ ")=="علی رضا کاظمی 123";assert canonical_url("https://Example.com/a/?utm_source=x&b=2&a=1#p")=="https://example.com/a?a=1&b=2"
def test_random_decree_path_is_not_primary():
    policy=SourcePolicy();r=SearchResult("https://random-blog.example/decree/123","متن حکم","متن حکم انتصاب آزمایشی",source_kind=SourceKind.PRIMARY_DOCUMENT);a=policy.primary_assessment(r,r.snippet);assert not a.is_primary;assert policy.classify(r,r.snippet)!=SourceKind.PRIMARY_DOCUMENT
def test_official_authority_plus_document_can_be_primary():
    reg=AuthorityRegistry({"records.agency.gov":"Agency"});policy=SourcePolicy(authority_registry=reg);r=SearchResult("https://records.agency.gov/decree/123","متن حکم انتصاب","حکم انتصاب رسمی و متن حکم");a=policy.primary_assessment(r,r.snippet);assert a.is_primary and a.authority_match;assert policy.classify(r,r.snippet)==SourceKind.PRIMARY_DOCUMENT
def test_official_site_news_story_not_primary():
    reg=AuthorityRegistry({"agency.gov":"Agency"});policy=SourcePolicy(authority_registry=reg);r=SearchResult("https://agency.gov/news/1","خبر روز","به گزارش خبرگزاری، رویدادی رخ داد");assert policy.classify(r,r.snippet)!=SourceKind.PRIMARY_DOCUMENT
def test_two_claim_quick_budget_covers_both_claims():
    claims=analyze_claims("محمدباقر ذوالقدر دبیر شورا بود؛ و نماینده رهبر هم بود");qs=plan_queries(claims,2);assert len(qs)==2;assert {q.claim_id for q in qs}=={"C1","C2"}
def test_appointment_gets_primary_priority():assert plan_queries(analyze_claims("فلانی با حکم رسمی منصوب شد"),1)[0].purpose=="primary"
def test_negative_gets_existence_priority():assert plan_queries(analyze_claims("هیچ حکم انتصابی برای او صادر نشده"),1)[0].purpose=="negative_existence"
def test_quote_gets_primary_priority():assert plan_queries(analyze_claims('او دقیقاً گفت «این جمله دقیق است»'),1)[0].purpose=="primary"
def test_negative_claim_without_primary_cannot_be_true():
    search=FakeSearch([SearchResult("https://news.example/x","گزارش","در آرشیو چیزی پیدا نشد",source_kind=SourceKind.NEWSROOM)]);result=FactCheckEngine(search,FakeReasoner(dec())).check("هیچ حکم انتصابی برای این فرد صادر نشده");assert result.verdict==Verdict.UNVERIFIED;assert result.confidence<=.48;assert any("absence_cannot_be_proven" in x for x in result.missing_evidence)
def test_cache_prevents_second_reasoning():
    with tempfile.TemporaryDirectory() as td:
        cache=SQLiteCache(Path(td)/"c.db");reg=AuthorityRegistry({"records.agency.gov":"Agency"});policy=SourcePolicy(authority_registry=reg);search=FakeSearch([SearchResult("https://records.agency.gov/decree/1","متن حکم","متن حکم انتصاب رسمی")]);reason=FakeReasoner(dec(conf=.8));engine=FactCheckEngine(search,reason,cache=cache,source_policy=policy);first=engine.check("حکم انتصاب صادر شد");second=engine.check("حکم انتصاب صادر شد");assert not first.from_cache and second.from_cache;assert reason.calls==1
def test_breaking_high_impact_capped():
    search=FakeSearch([SearchResult("https://news.example/x","خبر فوری حمله","لحظاتی پیش حمله رخ داد",source_kind=SourceKind.NEWSROOM)]);r=FactCheckEngine(search,FakeReasoner(dec(conf=.99))).check("خبر فوری: همین الان حمله نظامی انجام شده");assert r.confidence<=.52;assert r.diagnostics["deep_check_recommended"]
def test_deep_mode_uses_judge_and_critic():
    reg=AuthorityRegistry({"records.agency.gov":"Agency"});policy=SourcePolicy(authority_registry=reg);search=FakeSearch([SearchResult("https://records.agency.gov/decree/1","متن حکم","متن حکم انتصاب رسمی")]);reason=DeepReasoner(dec(conf=.9),dec(conf=.7));r=FactCheckEngine(search,reason,source_policy=policy).check("فلانی منصوب شد",mode="deep");assert reason.calls==1 and reason.critic_calls==1;assert r.cost_stats["reasoning_calls"]==2;assert r.diagnostics["critic_used"] is True
def test_deep_disagreement_is_conservative():
    reg=AuthorityRegistry({"records.agency.gov":"Agency"});policy=SourcePolicy(authority_registry=reg);search=FakeSearch([SearchResult("https://records.agency.gov/decree/1","متن حکم","متن حکم انتصاب رسمی")]);reason=DeepReasoner(dec(Verdict.TRUE,.9),dec(Verdict.FALSE,.8));r=FactCheckEngine(search,reason,source_policy=policy).check("فلانی منصوب شد",mode="deep");assert r.verdict==Verdict.CONFLICTING_EVIDENCE;assert r.confidence<=.55
def test_reasoner_failure_never_hallucinates():
    class Broken:
        def evaluate(self,claim,evidence):raise TimeoutError("boom")
    r=FactCheckEngine(FakeSearch([SearchResult("https://news.example/x","A","evidence",source_kind=SourceKind.NEWSROOM)]),Broken()).check("ادعا");assert r.verdict==Verdict.VERIFICATION_UNAVAILABLE;assert r.confidence<=.05
def test_official_statement_does_not_prove_underlying_attack():
    reg=AuthorityRegistry({"defense.gov":"Defense"});policy=SourcePolicy(authority_registry=reg);search=FakeSearch([SearchResult("https://defense.gov/statement/1","بیانیه رسمی","بیانیه: عملیات نظامی کاملاً موفق بود")]);r=FactCheckEngine(search,FakeReasoner(dec(conf=.95)),source_policy=policy).check("در حمله نظامی همه اهداف نابود شدند");assert r.confidence<=.52;assert r.verdict!=Verdict.TRUE
def test_low_coverage_caps_multiclaim_confidence():
    search=FakeSearch([SearchResult("https://news.example/x","A","evidence",source_kind=SourceKind.NEWSROOM)]);engine=FactCheckEngine(search,FakeReasoner(dec(conf=.95)),quick_budget=Budget(1,8,5,0,1,5000,60));r=engine.check("فلانی دبیر بود؛ فلانی نماینده هم بود");assert min(c.coverage_score for c in r.coverage)<.5;assert r.confidence<=.50
def test_retracted_evidence_cannot_keep_high_confidence():
    reg=AuthorityRegistry({"records.agency.gov":"Agency"});policy=SourcePolicy(authority_registry=reg);search=FakeSearch([SearchResult("https://records.agency.gov/decree/1","متن حکم","متن حکم انتصاب رسمی - این سند retracted شده است")]);r=FactCheckEngine(search,FakeReasoner(dec(conf=.95)),source_policy=policy).check("فلانی منصوب شد");assert r.confidence<=.38;assert r.verdict!=Verdict.TRUE
def test_challenge_result_is_kept_when_budget_allows():
    class PurposeSearch:
        def search(self,query,limit):
            if "تکذیب" in query or "نادرست" in query:return [SearchResult("https://challenge.example/x","تکذیب مستقل","این ادعا تکذیب شد",source_kind=SourceKind.NEWSROOM)]
            return [SearchResult("https://support.example/x","گزارش","این ادعا گزارش شد",source_kind=SourceKind.NEWSROOM)]
    reason=FakeReasoner(ReasoningDecision(Verdict.CONFLICTING_EVIDENCE,.6,"mixed",citation_ids=["E1","E2"],conflict_detected=True,evidence_stances={"E1":EvidenceStance.SUPPORTS,"E2":EvidenceStance.CONTRADICTS}));engine=FactCheckEngine(PurposeSearch(),reason,deep_budget=Budget(6,8,5,0,2,5000,60));r=engine.check("خبر سیاسی گزارش شده است",mode="deep");assert any("challenge" in e.retrieval_purposes for e in r.evidence)
