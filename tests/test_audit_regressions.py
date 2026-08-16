from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from political_core.cache import SQLiteCache
from political_core.cached_providers import CachedSearchProvider
from political_core.confidence import apply_guardrails
from political_core.contradictions import build_contradictions
from political_core.engine import FactCheckEngine
from political_core.entity import EntityAliasRegistry
from political_core.feedback import FeedbackStore
from political_core.fetch import _PinnedHTTPConnection
from political_core.models import (
    Budget,Claim,ClaimType,Contradiction,ContradictionType,DocumentState,Evidence,EvidenceStance,
    PrimarySourceAssessment,ReasoningDecision,SearchResult,SourceKind,SourceRole,Verdict,
)
from political_core.primary_source import AuthorityRegistry
from political_core.provenance import assess_independence,assign_source_chains
from political_core.quotes import verify_quotes
from political_core.temporal import jalali_to_gregorian,parse_date_text


class FakeSearch:
    def __init__(self,results):self.results=list(results);self.calls=0
    def search(self,q,limit):self.calls+=1;return self.results[:limit]
class FakeReasoner:
    def __init__(self,decision=None,broken=False):self.decision=decision;self.calls=0;self.broken=broken
    def evaluate(self,claim,evidence):
        self.calls+=1
        if self.broken:raise TimeoutError("temporary")
        return self.decision

def decision(conf=.8,citations=None,stances=None):
    return ReasoningDecision(Verdict.TRUE,conf,"ok",citation_ids=citations or ["E1"],evidence_stances=stances or {"E1":EvidenceStance.SUPPORTS})

def evidence(i:int,domain:str,text:str="evidence",**kw):
    return Evidence(f"E{i}",f"https://{domain}/{i}",text,domain,text,None,kw.pop("source_kind",SourceKind.NEWSROOM),kw.pop("quality_score",.7),domain,source_role=kw.pop("source_role",SourceRole.SECONDARY_REPORTING),**kw)


def test_authority_registry_applies_to_subdomains():
    reg=AuthorityRegistry({"example.gov":"Agency"});assert reg.authority_for("records.example.gov")=="Agency"


def test_dedupe_merges_purpose_and_claim_provenance():
    a=SearchResult("https://a.example/x","A","short",retrieval_purposes=["primary"],retrieval_claim_ids=["C1"])
    b=SearchResult("https://a.example/x?utm_source=z","A","a much longer snippet",retrieval_purposes=["challenge"],retrieval_claim_ids=["C2"])
    out=FactCheckEngine._dedupe([a,b]);assert len(out)==1;assert set(out[0].retrieval_purposes)=={"primary","challenge"};assert set(out[0].retrieval_claim_ids)=={"C1","C2"}


def test_primary_requirement_is_claim_targeted():
    c1=Claim("C1","x","x","X appointed",ClaimType.APPOINTMENT);c2=Claim("C2","x","x","Y appointed",ClaimType.APPOINTMENT)
    from political_core.claims import _requirements
    c1.evidence_requirements=_requirements(ClaimType.APPOINTMENT,"C1",False,False);c2.evidence_requirements=_requirements(ClaimType.APPOINTMENT,"C2",False,False)
    pa=PrimarySourceAssessment(True,.9,"issuer","issuer","decree",True)
    e=evidence(1,"official.gov",source_kind=SourceKind.PRIMARY_DOCUMENT,source_role=SourceRole.PRIMARY_DOCUMENT,primary_assessment=pa,retrieval_claim_ids=["C1"])
    engine=FactCheckEngine(FakeSearch([]),FakeReasoner())
    missing=engine._requirements([c1,c2],[e],[],[]);assert "C2:primary_document" in missing


def test_model_hallucinated_contradiction_ids_are_discarded():
    c=Claim("C1","x","x","x");e=[evidence(1,"a.example")];d=decision();d.contradictions=[Contradiction("C9","E1","E99",ContradictionType.DIRECT_FACT_CONFLICT,.9)]
    assert build_contradictions(d,e,[c])==[]


def test_cross_claim_support_and_contradiction_are_not_paired():
    c1=Claim("C1","x","x","a");c2=Claim("C2","x","x","b")
    a=evidence(1,"a.example",retrieval_claim_ids=["C1"]);b=evidence(2,"b.example",retrieval_claim_ids=["C2"])
    d=decision(citations=["E1","E2"],stances={"E1":EvidenceStance.SUPPORTS,"E2":EvidenceStance.CONTRADICTS})
    assert build_contradictions(d,[a,b],[c1,c2])==[]


def test_exact_quote_in_secondary_does_not_borrow_original_status_from_partial_official():
    c=Claim("C1","x","x","او گفت «جمله دقیق من این است»",ClaimType.QUOTE,quoted_texts=["جمله دقیق من این است"])
    secondary=evidence(1,"news.example","جمله دقیق من این است",retrieval_claim_ids=["C1"])
    official=evidence(2,"official.gov","جمله دقیق من متفاوت بود",source_role=SourceRole.OFFICIAL_PARTY_STATEMENT,primary_assessment=PrimarySourceAssessment(False,.5,"Agency","Agency",None,True),retrieval_claim_ids=["C1"])
    q=verify_quotes([c],[secondary,official])[0];assert q.status.value=="exact_match";assert q.original_source_found is False;assert q.evidence_ids==["E1"]


def test_invalid_jalali_month_day_is_rejected():
    with pytest.raises(ValueError):jalali_to_gregorian(1405,7,31)
    assert not any(x.raw_text=="31 مهر 1405" for x in parse_date_text("31 مهر 1405"))


def test_jalali_year_start_uses_actual_nowruz_date():
    rows=parse_date_text("سال 1403");year=next(x for x in rows if x.raw_text=="1403");assert year.parsed_datetime.startswith("2024-03-20")


def test_assess_independence_groups_cross_domain_chain():
    items=assign_source_chains([evidence(1,"a.example","same copied political report "*12,cited_source="wire-x"),evidence(2,"b.example","same copied political report "*12,cited_source="wire-x")])
    a=assess_independence(items);assert a.conservative_count==1


def test_retracted_contradiction_does_not_poison_active_support():
    c=Claim("C1","x","x","claim")
    active=evidence(1,"a.example");old=evidence(2,"b.example",document_state=DocumentState.RETRACTED)
    d=decision(conf=.9,citations=["E1","E2"],stances={"E1":EvidenceStance.SUPPORTS,"E2":EvidenceStance.CONTRADICTS});d.conflict_detected=True
    fixed,_=apply_guardrails(d,[active,old],[c]);assert fixed.confidence>.38


def test_corrupt_cache_row_is_evicted(tmp_path:Path):
    db=tmp_path/"c.db";cache=SQLiteCache(db)
    with sqlite3.connect(db) as conn:conn.execute("INSERT OR REPLACE INTO fact_cache VALUES(?,?,?)",("bad",9999999999,"{bad"))
    assert cache.get("bad",9999999999) is None


def test_feedback_does_not_store_user_text_by_default(tmp_path:Path):
    db=tmp_path/"f.db";store=FeedbackStore(db);store.add("r1","متن خصوصی کاربر","wrong","توضیح خصوصی")
    with sqlite3.connect(db) as conn:row=conn.execute("SELECT claim,claim_hash,comment FROM feedback").fetchone()
    assert row[0]=="" and row[1] and row[2]==""


def test_cached_search_bypass_forces_provider_call(tmp_path:Path):
    inner=FakeSearch([SearchResult("https://a.example/1","A","one")]);cached=CachedSearchProvider(inner,SQLiteCache(tmp_path/"c.db"),999)
    cached.search("q",5);cached.search("q",5);assert inner.calls==1
    cached.bypass_cache=True;cached.search("q",5);assert inner.calls==2


def test_verification_unavailable_is_not_cached(tmp_path:Path):
    search=FakeSearch([SearchResult("https://a.example/1","A","evidence",source_kind=SourceKind.NEWSROOM)]);reason=FakeReasoner(broken=True);engine=FactCheckEngine(search,reason,cache=SQLiteCache(tmp_path/"c.db"))
    engine.check("ادعا");engine.check("ادعا");assert reason.calls==2


def test_pinned_http_connection_uses_validated_ip():
    seen=[]
    class Sock:pass
    with patch("political_core.fetch.socket.create_connection",side_effect=lambda target,*a,**k:(seen.append(target) or Sock())):
        conn=_PinnedHTTPConnection("example.com","93.184.216.34",80,1);conn.connect()
    assert seen==[("93.184.216.34",80)]
