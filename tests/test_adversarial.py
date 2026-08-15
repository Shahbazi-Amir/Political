from __future__ import annotations

import socket
import unittest
from unittest.mock import patch

from political_core.engine import FactCheckEngine
from political_core.fetch import validate_public_url
from political_core.models import Evidence, EvidenceStance, ReasoningDecision, SearchResult, SourceKind, SourceRole, Verdict
from political_core.provenance import assign_source_chains, independent_source_count

class FakeSearch:
    def __init__(self, results): self.results = results
    def search(self, query, limit): return self.results[:limit]
class FakeReasoner:
    def __init__(self, decision): self.decision = decision
    def evaluate(self, claim, evidence): return self.decision

def ev(i, domain, text, cited=None):
    return Evidence(evidence_id=f"E{i}", url=f"https://{domain}/{i}", canonical_url=f"https://{domain}/{i}", title=text, domain=domain, excerpt=text * 5, published_at=None, source_kind=SourceKind.NEWSROOM, source_role=SourceRole.SECONDARY_REPORTING, quality_score=.7, relevance_score=.5, independence_key=domain, cited_source=cited)

class AdversarialTests(unittest.TestCase):
    def test_cross_domain_copies_are_one_source_chain(self):
        items = assign_source_chains([ev(1, "a.example", "خبر مشترک بسیار مشابه درباره رویداد سیاسی", "wire-x"), ev(2, "b.example", "خبر مشترک بسیار مشابه درباره رویداد سیاسی", "wire-x")])
        self.assertEqual(items[0].source_chain_id, items[1].source_chain_id)
        self.assertEqual(independent_source_count(items), 1)

    def test_many_copies_do_not_unlock_high_confidence(self):
        results = [SearchResult(f"https://site{i}.example/story", f"copy {i}", "same wire report event details " * 8, source_kind=SourceKind.NEWSROOM, cited_source="wire-x") for i in range(1, 6)]
        reasoner = FakeReasoner(ReasoningDecision(verdict=Verdict.TRUE, confidence=.99, summary="too sure", citation_ids=["E1", "E2", "E3"], evidence_stances={"E1": EvidenceStance.SUPPORTS, "E2": EvidenceStance.SUPPORTS, "E3": EvidenceStance.SUPPORTS}))
        result = FactCheckEngine(FakeSearch(results), reasoner).check("یک رویداد سیاسی رخ داده است")
        self.assertLessEqual(result.confidence, .58)
        self.assertEqual(result.diagnostics["independent_source_groups"], 1)

    def test_negative_claim_without_primary_cannot_be_declared_true(self):
        results = [SearchResult("https://news.example/story", "گزارش", "در آرشیو چیزی پیدا نشد", source_kind=SourceKind.NEWSROOM)]
        reasoner = FakeReasoner(ReasoningDecision(verdict=Verdict.TRUE, confidence=.9, summary="none exists", citation_ids=["E1"], evidence_stances={"E1": EvidenceStance.SUPPORTS}))
        result = FactCheckEngine(FakeSearch(results), reasoner).check("هیچ حکم انتصابی برای این فرد صادر نشده است")
        self.assertEqual(result.verdict, Verdict.UNVERIFIED)
        self.assertLessEqual(result.confidence, .58)
        self.assertTrue(any("absence_cannot_be_proven" in x for x in result.missing_evidence))

    def test_breaking_high_impact_claim_is_capped_without_primary_or_independence(self):
        results = [SearchResult("https://news.example/story", "خبر فوری حمله", "لحظاتی پیش حمله رخ داد", source_kind=SourceKind.NEWSROOM)]
        reasoner = FakeReasoner(ReasoningDecision(verdict=Verdict.TRUE, confidence=.98, summary="attack", citation_ids=["E1"], evidence_stances={"E1": EvidenceStance.SUPPORTS}))
        result = FactCheckEngine(FakeSearch(results), reasoner).check("خبر فوری: همین الان حمله نظامی انجام شده است")
        self.assertLessEqual(result.confidence, .55)
        self.assertTrue(result.diagnostics["deep_check_recommended"])

    def test_conflicting_evidence_blocks_binary_certainty(self):
        results = [SearchResult("https://a.example/one", "A", "supports event", source_kind=SourceKind.NEWSROOM), SearchResult("https://b.example/two", "B", "denies event", source_kind=SourceKind.NEWSROOM)]
        reasoner = FakeReasoner(ReasoningDecision(verdict=Verdict.TRUE, confidence=.92, summary="conflict", citation_ids=["E1", "E2"], conflict_detected=True, evidence_stances={"E1": EvidenceStance.SUPPORTS, "E2": EvidenceStance.CONTRADICTS}))
        result = FactCheckEngine(FakeSearch(results), reasoner).check("ادعا")
        self.assertEqual(result.verdict, Verdict.CONFLICTING_EVIDENCE)
        self.assertLessEqual(result.confidence, .65)

    @patch("political_core.fetch.socket.getaddrinfo")
    def test_ssrf_localhost_is_rejected(self, mocked):
        mocked.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]
        with self.assertRaises(ValueError): validate_public_url("http://example.test/x")

if __name__ == "__main__": unittest.main()
