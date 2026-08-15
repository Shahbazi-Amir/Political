from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from political_core.cache import SQLiteCache
from political_core.claims import analyze_claims, plan_queries
from political_core.engine import FactCheckEngine
from political_core.models import EvidenceStance, ReasoningDecision, SearchResult, SourceKind, Verdict
from political_core.source_policy import SourcePolicy
from political_core.text import canonical_url, fingerprint, normalize_text


class FakeSearch:
    def __init__(self, results):
        self.results = results
        self.calls = 0
    def search(self, query, limit):
        self.calls += 1
        return self.results[:limit]


class FakeReasoner:
    def __init__(self, decision):
        self.decision = decision
        self.calls = 0
    def evaluate(self, claim, evidence):
        self.calls += 1
        return self.decision


class FakeFetcher:
    def fetch_text(self, url, max_chars, relevance_terms=None):
        return (("full primary evidence relevant to claim " + (relevance_terms or "") + " from " + url + ". ") * 15)[:max_chars]


class CoreTests(unittest.TestCase):
    def test_persian_normalization_and_digits(self):
        self.assertEqual(normalize_text("  علي\u200c رضا   كاظمي ۱۲۳ ٤٥ "), "علی رضا کاظمی 123 45")

    def test_fingerprint_ignores_simple_punctuation_variants(self):
        self.assertEqual(fingerprint("آیا خبر درست است؟"), fingerprint("آیا خبر درست است!"))

    def test_canonical_url_strips_tracking(self):
        self.assertEqual(canonical_url("https://Example.com/a/?utm_source=x&b=2&a=1#part"), "https://example.com/a?a=1&b=2")

    def test_claim_analysis_marks_negative_high_impact_and_appointment(self):
        claims = analyze_claims("هیچ حکم انتصابی برای آقای علی رضایی صادر نشده است")
        self.assertTrue(claims[0].is_negative)
        self.assertTrue(claims[0].high_impact)
        self.assertIn("appointment_or_replacement_document", claims[0].required_evidence)

    def test_deep_query_plan_contains_challenge(self):
        queries = plan_queries(analyze_claims("آیا این حکم انتصاب درست است؟"), 6)
        self.assertTrue(any(q.purpose == "challenge" for q in queries))
        self.assertTrue(any(q.purpose == "primary" for q in queries))

    def test_primary_document_can_support_high_confidence_single_source(self):
        search = FakeSearch([SearchResult("https://example.gov/laws/decree/7", "متن حکم", "snippet", source_kind=SourceKind.PRIMARY_DOCUMENT)])
        reasoner = FakeReasoner(ReasoningDecision(verdict=Verdict.TRUE, confidence=0.94, summary="confirmed", citation_ids=["E1"], evidence_stances={"E1": EvidenceStance.SUPPORTS}))
        result = FactCheckEngine(search, reasoner, fetcher=FakeFetcher()).check("فلان حکم صادر شده است")
        self.assertEqual(result.verdict, Verdict.TRUE)
        self.assertEqual(result.confidence, 0.94)
        self.assertEqual(result.evidence_strength, "high")

    def test_high_confidence_is_capped_without_independent_or_primary_evidence(self):
        search = FakeSearch([SearchResult("https://news-a.example/story", "A", "same report", source_kind=SourceKind.NEWSROOM)])
        reasoner = FakeReasoner(ReasoningDecision(verdict=Verdict.TRUE, confidence=0.96, summary="claimed", citation_ids=["E1"], evidence_stances={"E1": EvidenceStance.SUPPORTS}))
        result = FactCheckEngine(search, reasoner).check("ادعا")
        self.assertLessEqual(result.confidence, 0.62)

    def test_invalid_model_citations_force_unverified(self):
        search = FakeSearch([SearchResult("https://a.example/x", "A", "evidence")])
        reasoner = FakeReasoner(ReasoningDecision(verdict=Verdict.TRUE, confidence=0.99, summary="bad citation", citation_ids=["E999"]))
        result = FactCheckEngine(search, reasoner).check("ادعا")
        self.assertEqual(result.verdict, Verdict.UNVERIFIED)
        self.assertLessEqual(result.confidence, 0.25)

    def test_cache_prevents_repeat_search_and_reasoning(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = SQLiteCache(Path(tmp) / "cache.db")
            search = FakeSearch([SearchResult("https://a.example/law/x", "متن حکم", "evidence", source_kind=SourceKind.PRIMARY_DOCUMENT)])
            reasoner = FakeReasoner(ReasoningDecision(verdict=Verdict.TRUE, confidence=0.8, summary="ok", citation_ids=["E1"]))
            engine = FactCheckEngine(search, reasoner, cache=cache)
            first = engine.check("خبر")
            second = engine.check("خبر")
            self.assertFalse(first.from_cache)
            self.assertTrue(second.from_cache)
            self.assertEqual(reasoner.calls, 1)

    def test_source_policy_does_not_treat_unknown_media_as_truth(self):
        policy = SourcePolicy()
        item = SearchResult("https://unknown.example/story", "خبر", "متن")
        self.assertEqual(policy.classify(item), SourceKind.UNKNOWN)
        self.assertLess(policy.score(item, item.snippet), 0.7)


class ExtendedCoreTests(unittest.TestCase):
    def test_transliteration_variant_is_available_in_deep_plan(self):
        claims = analyze_claims('آیا آقای محمد رضایی منصوب شده است؟')
        queries = plan_queries(claims, 6)
        self.assertTrue(any(q.purpose == 'transliteration' for q in queries))

    def test_argument_and_framing_are_diagnostic_not_verdicts(self):
        from political_core.analysis import analyze_argument, analyze_framing
        self.assertIn('causal_or_inference_marker', analyze_argument('چون رسانه گفت، پس نتیجه درست است')['signals'])
        self.assertTrue(analyze_framing('این یک شکست سنگین بود')['has_framing_signal'])


if __name__ == "__main__":
    unittest.main()
