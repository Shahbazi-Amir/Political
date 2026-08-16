from __future__ import annotations
import socket
from unittest.mock import patch
import pytest
from political_core.engine import FactCheckEngine
from political_core.fetch import validate_public_url
from political_core.models import EvidenceStance,ReasoningDecision,SearchResult,SourceKind,Verdict
class FakeSearch:
    def __init__(self,results):self.results=results
    def search(self,query,limit):return self.results[:limit]
class FakeReasoner:
    def __init__(self,d):self.d=d
    def evaluate(self,claim,evidence):return self.d
def test_exact_quote_secondary_only_is_not_enough():
    search=FakeSearch([SearchResult("https://news.example/q","گزارش",'او گفت «این جمله دقیق من است»',source_kind=SourceKind.NEWSROOM)]);d=ReasoningDecision(Verdict.TRUE,.92,"quote",citation_ids=["E1"],evidence_stances={"E1":EvidenceStance.SUPPORTS});r=FactCheckEngine(search,FakeReasoner(d)).check('او دقیقاً گفت «این جمله دقیق من است»');assert r.verdict==Verdict.UNVERIFIED;assert r.confidence<=.42
@patch("political_core.fetch.socket.getaddrinfo")
def test_ssrf_localhost_rejected(mocked):
    mocked.return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,"",("127.0.0.1",80))]
    with pytest.raises(ValueError):validate_public_url("http://example.test/x")
def test_literal_private_ip_rejected():
    with pytest.raises(ValueError):validate_public_url("http://127.0.0.1/x")
    with pytest.raises(ValueError):validate_public_url("http://10.0.0.1/x")
def test_url_userinfo_rejected():
    with pytest.raises(ValueError):validate_public_url("http://user:pass@example.com/x")
