from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from political_core.cache import SQLiteCache
from political_core.engine import FactCheckEngine
from political_core.models import Evidence, ReasoningDecision, SearchResult, SourceKind, Verdict
from political_core.source_policy import SourcePolicy
from political_core.text import canonical_url, normalize_text


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
    def fetch_text(self, url, max_chars):
        return ("full primary evidence from " + url + " ") * 30


class CoreTests(unittest.TestCase):
    def test_persian_normalization(self):
        self.assertEqual(normalize_text("  علي\u200c رضا   كاظمي  "), "علی رضا کاظمی")

    def test_canonical_url_strips_tracking(self):
        self.assertEqual(
            canonical_url("https://Example.com/a/?utm_source=x&b=2&a=1#part"),
            "https://example.com/a?a=1&b=2",
        )

    def test_primary_document_can_support_high_confidence_single_source(self):
        search = FakeSearch([
            SearchResult("https://example.gov/laws/decree/7", "متن حکم", "snippet", source_kind=SourceKind.PRIMARY_DOCUMENT)
        ])
        reasoner = FakeReasoner(ReasoningDecision(
            verdict=Verdict.TRUE,
            confidence=0.94,
            summary="confirmed",
            citation_ids=["E1"],
        ))
        engine = FactCheckEngine(search, reasoner, fetcher=FakeFetcher())
        result = engine.check("فلان حکم صادر شده است")
        self.assertEqual(result.verdict, Verdict.TRUE)
        self.assertEqual(result.confidence, 0.94)

    def test_high_confidence_is_capped_without_independent_or_primary_evidence(self):
        search = FakeSearch([
            SearchResult("https://news-a.example/story", "A", "same report", source_kind=SourceKind.NEWSROOM),
        ])
        reasoner = FakeReasoner(ReasoningDecision(
            verdict=Verdict.TRUE,
            confidence=0.96,
            summary="claimed",
            citation_ids=["E1"],
        ))
        result = FactCheckEngine(search, reasoner).check("ادعا")
        self.assertLessEqual(result.confidence, 0.64)

    def test_invalid_model_citations_force_unverified(self):
        search = FakeSearch([SearchResult("https://a.example/x", "A", "evidence")])
        reasoner = FakeReasoner(ReasoningDecision(
            verdict=Verdict.TRUE,
            confidence=0.99,
            summary="bad citation",
            citation_ids=["E999"],
        ))
        result = FactCheckEngine(search, reasoner).check("ادعا")
        self.assertEqual(result.verdict, Verdict.UNVERIFIED)
        self.assertLessEqual(result.confidence, 0.30)

    def test_cache_prevents_repeat_search_and_reasoning(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = SQLiteCache(Path(tmp) / "cache.db")
            search = FakeSearch([SearchResult("https://a.example/x", "A", "evidence", source_kind=SourceKind.PRIMARY_DOCUMENT)])
            reasoner = FakeReasoner(ReasoningDecision(
                verdict=Verdict.TRUE,
                confidence=0.8,
                summary="ok",
                citation_ids=["E1"],
            ))
            engine = FactCheckEngine(search, reasoner, cache=cache)
            first = engine.check("خبر")
            second = engine.check("خبر")
            self.assertFalse(first.from_cache)
            self.assertTrue(second.from_cache)
            self.assertEqual(reasoner.calls, 1)

    def test_source_independence_prefers_different_domains(self):
        results = [
            SearchResult("https://one.example/a", "A", "long " * 100, source_kind=SourceKind.NEWSROOM),
            SearchResult("https://one.example/b", "B", "longer " * 100, source_kind=SourceKind.NEWSROOM),
            SearchResult("https://two.example/c", "C", "other " * 100, source_kind=SourceKind.NEWSROOM),
        ]
        reasoner = FakeReasoner(ReasoningDecision(
            verdict=Verdict.MISSING_CONTEXT,
            confidence=0.7,
            summary="mixed",
            citation_ids=["E1", "E2"],
        ))
        result = FactCheckEngine(FakeSearch(results), reasoner).check("ادعا")
        groups = [e.independence_key for e in result.evidence[:2]]
        self.assertEqual(len(set(groups)), 2)

    def test_source_policy_does_not_treat_unknown_media_as_truth(self):
        policy = SourcePolicy()
        item = SearchResult("https://unknown.example/story", "خبر", "متن")
        self.assertEqual(policy.classify(item), SourceKind.UNKNOWN)
        self.assertLess(policy.score(item, item.snippet), 0.7)


if __name__ == "__main__":
    unittest.main()
