from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from .cache import SQLiteCache
from .models import (
    Budget,
    Evidence,
    FactCheckResult,
    ReasoningDecision,
    SearchResult,
    SourceKind,
    Verdict,
)
from .providers import Fetcher, ReasoningProvider, SearchProvider
from .source_policy import SourcePolicy
from .text import build_queries, canonical_url, domain_of, fingerprint, normalize_text


class FactCheckEngine:
    def __init__(
        self,
        search: SearchProvider,
        reasoner: ReasoningProvider,
        *,
        fetcher: Fetcher | None = None,
        cache: SQLiteCache | None = None,
        source_policy: SourcePolicy | None = None,
    ) -> None:
        self.search = search
        self.reasoner = reasoner
        self.fetcher = fetcher
        self.cache = cache
        self.source_policy = source_policy or SourcePolicy()

    def check(self, claim: str, *, mode: str = "quick", refresh: bool = False) -> FactCheckResult:
        budget = Budget.deep() if mode == "deep" else Budget.quick()
        normalized = normalize_text(claim)
        if not normalized:
            raise ValueError("claim is empty")
        cache_key = f"v2:{mode}:{fingerprint(normalized)}"
        if self.cache and not refresh:
            cached = self.cache.get(cache_key, budget.cache_ttl_seconds)
            if cached:
                return self._from_cache(cached)

        queries = build_queries(normalized, budget.max_queries)
        raw_results: list[SearchResult] = []
        search_errors: list[str] = []
        for query in queries:
            try:
                raw_results.extend(self.search.search(query, budget.results_per_query))
            except Exception as exc:  # provider failure must not turn into a fabricated verdict
                search_errors.append(f"{type(exc).__name__}: {exc}")

        candidates = self._dedupe(raw_results)
        evidence, fetch_errors = self._build_evidence(candidates, budget)
        if not evidence:
            result = FactCheckResult(
                claim=claim,
                normalized_claim=normalized,
                verdict=Verdict.UNVERIFIED,
                confidence=0.05,
                summary="شواهد قابل اتکای کافی برای ارزیابی این ادعا پیدا نشد.",
                key_points=[],
                uncertainty="جست‌وجو یا بازیابی منبع کافی نبود؛ نتیجه‌گیری قطعی مجاز نیست.",
                evidence=[],
                citation_ids=[],
                diagnostics={"queries": queries, "search_errors": search_errors, "fetch_errors": fetch_errors},
            )
            self._save(cache_key, result)
            return result

        decision = self.reasoner.evaluate(normalized, evidence)
        decision = self._apply_epistemic_guardrails(decision, evidence)
        result = FactCheckResult(
            claim=claim,
            normalized_claim=normalized,
            verdict=decision.verdict,
            confidence=round(decision.confidence, 3),
            summary=decision.summary,
            key_points=decision.key_points,
            uncertainty=decision.uncertainty,
            evidence=evidence,
            citation_ids=decision.citation_ids,
            diagnostics={
                "queries": queries,
                "search_errors": search_errors,
                "fetch_errors": fetch_errors,
                "independent_source_groups": len({x.independence_key for x in evidence}),
                "conflict_detected": decision.conflict_detected,
                "conflict_resolution": decision.conflict_resolution,
            },
        )
        self._save(cache_key, result)
        return result

    def _dedupe(self, results: Sequence[SearchResult]) -> list[SearchResult]:
        by_url: dict[str, SearchResult] = {}
        for item in results:
            try:
                key = canonical_url(item.url)
            except Exception:
                continue
            if not key.startswith(("http://", "https://")):
                continue
            existing = by_url.get(key)
            if existing is None or len(item.snippet) > len(existing.snippet):
                by_url[key] = item
        return list(by_url.values())

    def _build_evidence(self, results: Sequence[SearchResult], budget: Budget) -> tuple[list[Evidence], list[str]]:
        provisional: list[tuple[float, SearchResult, str, SourceKind]] = []
        errors: list[str] = []
        fetches = 0
        for result in results:
            excerpt = result.snippet.strip()
            if self.fetcher and fetches < budget.max_fetches:
                try:
                    fetched = self.fetcher.fetch_text(result.url, budget.max_page_chars)
                    if fetched:
                        excerpt = fetched
                    fetches += 1
                except Exception as exc:
                    errors.append(f"{domain_of(result.url)}: {type(exc).__name__}: {exc}")
            kind = self.source_policy.classify(result)
            scored_result = replace(result, source_kind=kind)
            score = self.source_policy.score(scored_result, excerpt)
            if excerpt:
                provisional.append((score, scored_result, excerpt, kind))

        provisional.sort(key=lambda x: (x[0], len(x[2])), reverse=True)
        selected: list[tuple[float, SearchResult, str, SourceKind]] = []
        used_groups: set[str] = set()
        # First pass maximizes source independence.
        for item in provisional:
            group = self.source_policy.independence_key(item[1].url)
            if group in used_groups:
                continue
            selected.append(item)
            used_groups.add(group)
            if len(selected) >= budget.max_sources:
                break
        # Second pass can fill remaining slots with additional primary documents or context.
        if len(selected) < budget.max_sources:
            chosen_urls = {canonical_url(x[1].url) for x in selected}
            for item in provisional:
                if canonical_url(item[1].url) in chosen_urls:
                    continue
                selected.append(item)
                if len(selected) >= budget.max_sources:
                    break

        evidence: list[Evidence] = []
        for idx, (score, result, excerpt, kind) in enumerate(selected, start=1):
            evidence.append(
                Evidence(
                    evidence_id=f"E{idx}",
                    url=result.url,
                    title=result.title,
                    domain=domain_of(result.url),
                    excerpt=excerpt[: budget.max_page_chars],
                    published_at=result.published_at,
                    source_kind=kind,
                    quality_score=score,
                    independence_key=self.source_policy.independence_key(result.url),
                )
            )
        return evidence, errors

    @staticmethod
    def _apply_epistemic_guardrails(decision: ReasoningDecision, evidence: Sequence[Evidence]) -> ReasoningDecision:
        valid_ids = {x.evidence_id for x in evidence}
        citations = [x for x in decision.citation_ids if x in valid_ids]
        confidence = min(1.0, max(0.0, decision.confidence))
        verdict = decision.verdict

        cited = [x for x in evidence if x.evidence_id in citations]
        independent = len({x.independence_key for x in cited})
        has_primary = any(x.source_kind == SourceKind.PRIMARY_DOCUMENT for x in cited)
        only_weak = bool(cited) and all(x.source_kind in {SourceKind.UNKNOWN, SourceKind.SOCIAL} for x in cited)

        if not citations:
            return replace(
                decision,
                verdict=Verdict.UNVERIFIED,
                confidence=min(confidence, 0.30),
                citation_ids=[],
                uncertainty=(decision.uncertainty + " نتیجه بدون استناد معتبر بود و به حالت تأییدنشده محدود شد.").strip(),
            )
        if verdict in {Verdict.TRUE, Verdict.FALSE} and independent < 2 and not has_primary:
            confidence = min(confidence, 0.64)
        if only_weak:
            confidence = min(confidence, 0.52)
        if decision.conflict_detected and verdict in {Verdict.TRUE, Verdict.FALSE}:
            confidence = min(confidence, 0.70)
        # Extreme certainty is reserved for unusually direct evidence.
        if confidence > 0.95 and not has_primary:
            confidence = 0.95

        return replace(decision, confidence=confidence, citation_ids=citations)

    def _save(self, key: str, result: FactCheckResult) -> None:
        if self.cache:
            self.cache.set(key, result.to_dict())

    @staticmethod
    def _from_cache(data: dict[str, Any]) -> FactCheckResult:
        evidence = [
            Evidence(
                evidence_id=item["evidence_id"],
                url=item["url"],
                title=item["title"],
                domain=item["domain"],
                excerpt=item["excerpt"],
                published_at=item.get("published_at"),
                source_kind=SourceKind(item["source_kind"]),
                quality_score=float(item["quality_score"]),
                independence_key=item["independence_key"],
            )
            for item in data.get("evidence", [])
        ]
        return FactCheckResult(
            claim=data["claim"],
            normalized_claim=data["normalized_claim"],
            verdict=Verdict(data["verdict"]),
            confidence=float(data["confidence"]),
            summary=data["summary"],
            key_points=list(data.get("key_points", [])),
            uncertainty=data.get("uncertainty", ""),
            evidence=evidence,
            citation_ids=list(data.get("citation_ids", [])),
            from_cache=True,
            diagnostics=dict(data.get("diagnostics", {})),
        )
