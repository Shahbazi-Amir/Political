from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from .analysis import analyze_argument, analyze_framing
from .cache import SQLiteCache
from .claims import analyze_claims, plan_queries
from .confidence import apply_guardrails
from .models import (
    Budget,
    Claim,
    Evidence,
    EvidenceStance,
    FactCheckResult,
    ReasoningDecision,
    SearchResult,
    SourceKind,
    SourceRole,
    TimelineEvent,
    Verdict,
)
from .provenance import assign_source_chains, independent_source_count
from .providers import Fetcher, ReasoningProvider, SearchProvider
from .source_policy import SourcePolicy
from .text import canonical_url, domain_of, fingerprint, lexical_relevance, normalize_text


class FactCheckEngine:
    def __init__(
        self,
        search: SearchProvider,
        reasoner: ReasoningProvider,
        *,
        fetcher: Fetcher | None = None,
        cache: SQLiteCache | None = None,
        source_policy: SourcePolicy | None = None,
        quick_budget: Budget | None = None,
        deep_budget: Budget | None = None,
    ) -> None:
        self.search = search
        self.reasoner = reasoner
        self.fetcher = fetcher
        self.cache = cache
        self.source_policy = source_policy or SourcePolicy()
        self.quick_budget = quick_budget or Budget.quick()
        self.deep_budget = deep_budget or Budget.deep()

    def check(self, claim: str, *, mode: str = "quick", refresh: bool = False) -> FactCheckResult:
        started = datetime.now(timezone.utc)
        budget = self.deep_budget if mode == "deep" else self.quick_budget
        normalized = normalize_text(claim)
        if not normalized:
            raise ValueError("claim is empty")
        atomic_claims = analyze_claims(claim)
        ttl = self._cache_ttl(atomic_claims, budget)
        cache_key = f"v3:{mode}:{fingerprint(normalized)}"
        if self.cache and not refresh:
            cached = self.cache.get(cache_key, ttl)
            if cached:
                return self._from_cache(cached)

        planned = plan_queries(atomic_claims, budget.max_queries)
        raw_results: list[SearchResult] = []
        search_errors: list[str] = []
        for query in planned:
            try:
                raw_results.extend(self.search.search(query.text, budget.results_per_query))
            except Exception as exc:
                search_errors.append(f"{query.purpose}: {type(exc).__name__}: {exc}")

        candidates = self._dedupe(raw_results)
        evidence, fetch_errors = self._build_evidence(candidates, budget, atomic_claims)
        diagnostics: dict[str, Any] = {
            "mode": mode,
            "queries": [{"text": q.text, "purpose": q.purpose, "claim_id": q.claim_id} for q in planned],
            "search_errors": search_errors,
            "fetch_errors": fetch_errors,
            "total_urls": len(raw_results),
            "deduped_urls": len(candidates),
            "negative_claim": any(c.is_negative for c in atomic_claims),
            "breaking_news": any(c.breaking_news for c in atomic_claims),
            "current_status": any(c.current_status for c in atomic_claims),
            "search_provider_stats": getattr(self.search, "stats", {}),
        }

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
                atomic_claims=atomic_claims,
                evidence_strength="low",
                missing_evidence=self._required_missing(atomic_claims, []),
                diagnostics=diagnostics,
                cost_stats=self._cost_stats(started, len(planned), 0, 0, {}),
            )
            self._save(cache_key, result)
            return result

        reasoning_input = self._reasoning_claim(normalized, atomic_claims)
        decision = self.reasoner.evaluate(reasoning_input, evidence)
        decision, profile = apply_guardrails(decision, evidence, atomic_claims)
        supporting = [e.evidence_id for e in evidence if e.stance == EvidenceStance.SUPPORTS]
        contradicting = [e.evidence_id for e in evidence if e.stance == EvidenceStance.CONTRADICTS]
        missing = list(dict.fromkeys(decision.missing_evidence + self._required_missing(atomic_claims, evidence)))
        timeline = self._timeline(atomic_claims, evidence)
        diagnostics.update({
            "independent_source_groups": independent_source_count([e for e in evidence if e.evidence_id in decision.citation_ids]),
            "source_chains": len({e.source_chain_id for e in evidence if e.source_chain_id}),
            "conflict_detected": decision.conflict_detected or bool(contradicting),
            "conflict_resolution": decision.conflict_resolution,
            "deep_check_recommended": self._recommend_deep(mode, atomic_claims, decision, profile.independent_sources, profile.primary_count),
        })
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
            atomic_claims=atomic_claims,
            evidence_strength=profile.strength,
            supporting_evidence_ids=supporting,
            contradicting_evidence_ids=contradicting,
            missing_evidence=missing,
            timeline=timeline,
            diagnostics=diagnostics,
            cost_stats=self._cost_stats(started, len(planned), min(len(candidates), budget.max_fetches) if self.fetcher else 0, 1, decision.usage),
            analysis={"argument": analyze_argument(normalized), "framing": analyze_framing(normalized), "fetch_provider_stats": getattr(self.fetcher, "stats", {}) if self.fetcher else {}},
        )
        self._save(cache_key, result)
        return result

    @staticmethod
    def _cache_ttl(claims: Sequence[Claim], budget: Budget) -> int:
        if any(c.breaking_news for c in claims):
            return min(budget.cache_ttl_seconds, 10 * 60)
        if any(c.current_status for c in claims):
            return min(budget.cache_ttl_seconds, 30 * 60)
        if any(c.claim_type.value in {"constitutional", "legal", "historical", "timeline"} for c in claims):
            return max(budget.cache_ttl_seconds, 24 * 60 * 60)
        return budget.cache_ttl_seconds

    def _dedupe(self, results: Sequence[SearchResult]) -> list[SearchResult]:
        by_url: dict[str, SearchResult] = {}
        for item in results:
            try:
                key = canonical_url(item.url)
            except Exception:
                continue
            existing = by_url.get(key)
            if existing is None or len(item.snippet) > len(existing.snippet):
                by_url[key] = item
        return list(by_url.values())

    def _build_evidence(self, results: Sequence[SearchResult], budget: Budget, claims: Sequence[Claim]) -> tuple[list[Evidence], list[str]]:
        full_claim = " ".join(c.atomic_text for c in claims)
        provisional: list[Evidence] = []
        errors: list[str] = []
        fetches = 0
        for result in results:
            excerpt = result.snippet.strip()
            relevance = lexical_relevance(full_claim, f"{result.title} {excerpt}")
            if self.fetcher and fetches < budget.max_fetches:
                try:
                    try:
                        fetched = self.fetcher.fetch_text(result.url, budget.max_page_chars, full_claim)
                    except TypeError:
                        fetched = self.fetcher.fetch_text(result.url, budget.max_page_chars)
                    if fetched:
                        excerpt = fetched
                        relevance = max(relevance, lexical_relevance(full_claim, fetched))
                    fetches += 1
                except Exception as exc:
                    errors.append(f"{domain_of(result.url)}: {type(exc).__name__}: {exc}")
            if not excerpt:
                continue
            kind = self.source_policy.classify(result)
            role = self.source_policy.role(result, excerpt)
            scored_result = replace(result, source_kind=kind)
            score = self.source_policy.score(scored_result, excerpt, relevance)
            try:
                canon = canonical_url(result.url)
            except ValueError:
                continue
            provisional.append(Evidence(
                evidence_id="",
                url=result.url,
                canonical_url=canon,
                title=result.title,
                domain=domain_of(result.url),
                publisher=result.publisher,
                excerpt=excerpt[:budget.max_page_chars],
                published_at=result.published_at,
                updated_at=result.updated_at,
                source_kind=kind,
                source_role=role,
                quality_score=score,
                relevance_score=relevance,
                independence_key=self.source_policy.independence_key(result.url),
                cited_source=self.source_policy.cited_source_hint(result),
                correction_status="corrected" if any(x in excerpt.casefold() for x in ("اصلاحیه", "تصحیح", "correction")) else None,
                retraction_status="retracted" if any(x in excerpt.casefold() for x in ("پس گرفته شد", "حذف شد", "retracted", "withdrawn")) else None,
            ))

        provisional = assign_source_chains(provisional)
        provisional.sort(key=lambda e: (e.quality_score + e.relevance_score * 0.2, len(e.excerpt)), reverse=True)
        selected: list[Evidence] = []
        used_chains: set[str] = set()
        for item in provisional:
            key = item.source_chain_id or item.independence_key
            if key in used_chains:
                continue
            selected.append(item)
            used_chains.add(key)
            if len(selected) >= budget.max_sources:
                break
        if len(selected) < budget.max_sources:
            chosen = {e.canonical_url for e in selected}
            for item in provisional:
                if item.canonical_url in chosen:
                    continue
                if item.source_kind == SourceKind.PRIMARY_DOCUMENT or item.source_role == SourceRole.PRIMARY_DOCUMENT:
                    selected.append(item)
                elif len(selected) < min(budget.max_sources, 7):
                    selected.append(item)
                if len(selected) >= budget.max_sources:
                    break
        return [replace(e, evidence_id=f"E{i}") for i, e in enumerate(selected, 1)], errors

    @staticmethod
    def _reasoning_claim(normalized: str, claims: Sequence[Claim]) -> str:
        atoms = "\n".join(f"{c.claim_id}: {c.atomic_text} | type={c.claim_type.value} | negative={c.is_negative} | current={c.current_status}" for c in claims)
        return f"ORIGINAL CLAIM:\n{normalized}\n\nATOMIC CLAIMS:\n{atoms}"

    @staticmethod
    def _required_missing(claims: Sequence[Claim], evidence: Sequence[Evidence]) -> list[str]:
        missing: list[str] = []
        has_primary = any(e.source_kind == SourceKind.PRIMARY_DOCUMENT or e.source_role == SourceRole.PRIMARY_DOCUMENT for e in evidence)
        for claim in claims:
            for requirement in claim.required_evidence:
                if requirement in {"appointment_or_replacement_document", "constitutional_text", "law_or_primary_legal_text", "official_membership_record"} and not has_primary:
                    missing.append(f"{claim.claim_id}:{requirement}")
                if requirement == "broad_archive_search" and claim.is_negative:
                    missing.append(f"{claim.claim_id}:absence_cannot_be_proven_by_search_failure_alone")
        return list(dict.fromkeys(missing))

    @staticmethod
    def _timeline(claims: Sequence[Claim], evidence: Sequence[Evidence]) -> list[TimelineEvent]:
        if not any(c.claim_type.value in {"appointment", "membership", "timeline", "current_status"} for c in claims):
            return []
        events: list[TimelineEvent] = []
        for e in evidence:
            text = f"{e.title} {e.excerpt[:500]}"
            event_type = None
            for key, label in (("انتصاب", "appointment"), ("منصوب", "appointment"), ("عزل", "dismissal"), ("استعفا", "resignation"), ("تمدید", "renewal"), ("جایگزین", "replacement")):
                if key in text:
                    event_type = label
                    break
            if event_type and (e.published_at or e.event_date):
                events.append(TimelineEvent(entity="", role="", event_type=event_type, start_date=e.event_date or e.published_at,
                                            evidence_ids=[e.evidence_id], confidence=min(0.95, e.quality_score)))
        events.sort(key=lambda x: x.start_date or "")
        return events[:20]

    @staticmethod
    def _recommend_deep(mode: str, claims: Sequence[Claim], decision: ReasoningDecision, independent: int, primary: int) -> bool:
        if mode == "deep":
            return False
        return bool(decision.conflict_detected or any(c.is_negative or c.high_impact or c.breaking_news for c in claims) or decision.confidence < 0.68 or (primary == 0 and independent < 2))

    @staticmethod
    def _cost_stats(started: datetime, queries: int, fetches: int, reasoning_calls: int, usage: dict[str, Any]) -> dict[str, Any]:
        duration = (datetime.now(timezone.utc) - started).total_seconds()
        return {
            "search_queries": queries,
            "pages_fetched": fetches,
            "reasoning_calls": reasoning_calls,
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "estimated_cost": usage.get("estimated_cost"),
            "duration_seconds": round(duration, 3),
        }

    def _save(self, key: str, result: FactCheckResult) -> None:
        if self.cache:
            self.cache.set(key, result.to_dict())

    @staticmethod
    def _from_cache(data: dict[str, Any]) -> FactCheckResult:
        from .models import ClaimType, Intent, SourceRole
        evidence = []
        for item in data.get("evidence", []):
            evidence.append(Evidence(
                evidence_id=item["evidence_id"], url=item["url"], canonical_url=item.get("canonical_url", item["url"]), title=item["title"],
                domain=item["domain"], publisher=item.get("publisher"), excerpt=item["excerpt"], published_at=item.get("published_at"),
                updated_at=item.get("updated_at"), event_date=item.get("event_date"), retrieved_at=item.get("retrieved_at", ""),
                source_kind=SourceKind(item["source_kind"]), source_role=SourceRole(item.get("source_role", "unknown")),
                quality_score=float(item["quality_score"]), relevance_score=float(item.get("relevance_score", 0)),
                independence_key=item["independence_key"], source_chain_id=item.get("source_chain_id", ""), cited_source=item.get("cited_source"),
                stance=EvidenceStance(item.get("stance", "unclear")), correction_status=item.get("correction_status"), retraction_status=item.get("retraction_status"),
            ))
        claims = []
        for item in data.get("atomic_claims", []):
            claims.append(Claim(
                claim_id=item["claim_id"], original_text=item["original_text"], normalized_text=item["normalized_text"], atomic_text=item["atomic_text"],
                claim_type=ClaimType(item.get("claim_type", "unknown")), intent=Intent(item.get("intent", "fact_check")), entities=list(item.get("entities", [])),
                dates=list(item.get("dates", [])), dependencies=list(item.get("dependencies", [])), required_evidence=list(item.get("required_evidence", [])),
                is_negative=bool(item.get("is_negative")), high_impact=bool(item.get("high_impact")), current_status=bool(item.get("current_status")),
                breaking_news=bool(item.get("breaking_news")), quoted_texts=list(item.get("quoted_texts", [])),
            ))
        timeline = [TimelineEvent(**x) for x in data.get("timeline", [])]
        return FactCheckResult(
            claim=data["claim"], normalized_claim=data["normalized_claim"], verdict=Verdict(data["verdict"]), confidence=float(data["confidence"]),
            summary=data["summary"], key_points=list(data.get("key_points", [])), uncertainty=data.get("uncertainty", ""), evidence=evidence,
            citation_ids=list(data.get("citation_ids", [])), atomic_claims=claims, evidence_strength=data.get("evidence_strength", "low"),
            supporting_evidence_ids=list(data.get("supporting_evidence_ids", [])), contradicting_evidence_ids=list(data.get("contradicting_evidence_ids", [])),
            missing_evidence=list(data.get("missing_evidence", [])), timeline=timeline, from_cache=True,
            diagnostics=dict(data.get("diagnostics", {})), cost_stats=dict(data.get("cost_stats", {})), analysis=dict(data.get("analysis", {})),
        )
