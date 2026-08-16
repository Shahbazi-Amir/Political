from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime,timezone
from typing import Any

from .analysis import analyze_argument,analyze_framing
from .cache import SQLiteCache
from .claims import analyze_claims,coverage_template,finalize_coverage,plan_queries
from .confidence import apply_guardrails
from .contradictions import build_contradictions
from .entity import EntityAliasRegistry
from .models import (
    Claim,ClaimResearchCoverage,ClaimType,Contradiction,ContradictionType,DocumentState,Evidence,
    EvidenceRequirement,EvidenceStance,FactCheckResult,Intent,PrimarySourceAssessment,QuoteMatchStatus,
    QuoteVerification,ReasoningDecision,RequirementType,SearchResult,SourceKind,SourceRole,TimelineEvent,Verdict,
    Budget,DateInfo,EntityRef,
)
from .provenance import assign_source_chains,independent_source_count
from .providers import Fetcher,ReasoningProvider,SearchProvider
from .quotes import verify_quotes
from .source_policy import SourcePolicy
from .temporal import FreshnessPolicy
from .text import canonical_url,domain_of,fingerprint,lexical_relevance,normalize_text
from .timeline import build_timeline


class FactCheckEngine:
    def __init__(
        self,
        search:SearchProvider,
        reasoner:ReasoningProvider,
        *,
        fetcher:Fetcher|None=None,
        cache:SQLiteCache|None=None,
        source_policy:SourcePolicy|None=None,
        quick_budget:Budget|None=None,
        deep_budget:Budget|None=None,
        freshness_policy:FreshnessPolicy|None=None,
        entity_registry:EntityAliasRegistry|None=None,
        decomposer=None,
    )->None:
        self.search=search;self.reasoner=reasoner;self.fetcher=fetcher;self.cache=cache
        self.source_policy=source_policy or SourcePolicy()
        self.quick_budget=quick_budget or Budget.quick();self.deep_budget=deep_budget or Budget.deep()
        self.freshness_policy=freshness_policy or FreshnessPolicy()
        self.entity_registry=entity_registry or EntityAliasRegistry()
        self.decomposer=decomposer

    def check(self,claim:str,*,mode:str="quick",refresh:bool=False,reference_date:datetime|None=None)->FactCheckResult:
        started=datetime.now(timezone.utc)
        budget=self.deep_budget if mode=="deep" else self.quick_budget
        normalized=normalize_text(claim)
        if not normalized:raise ValueError("claim is empty")
        atomic=analyze_claims(
            claim,reference_date=reference_date,registry=self.entity_registry,decomposer=self.decomposer,
            allow_model_decomposition=bool(mode=="deep" and self.decomposer),
        )
        ttl=self._cache_ttl(atomic,budget)
        ref_key=(reference_date or datetime.now(timezone.utc)).date().isoformat() if any(c.current_status or c.breaking_news for c in atomic) else "stable"
        cache_key=f"v5:{mode}:{ref_key}:{fingerprint(normalized)}"
        if self.cache and not refresh:
            cached=self.cache.get(cache_key,ttl)
            if cached:
                result=self._from_cache(cached);result.from_cache=True;return result

        planned=plan_queries(atomic,budget.max_queries,self.entity_registry)
        coverage=coverage_template(atomic,planned)
        covmap={c.claim_id:c for c in coverage}
        raw_results=[];search_errors=[]
        for query in planned:
            cov=covmap.get(query.claim_id or "")
            if cov:
                cov.executed_purposes.append(query.purpose)
            try:
                items=list(self.search.search(query.text,budget.results_per_query))
                raw_results.extend([
                    replace(item,retrieval_purposes=list(dict.fromkeys(list(item.retrieval_purposes)+[query.purpose])))
                    for item in items
                ])
                if cov:cov.successful_purposes.append(query.purpose)
            except Exception as exc:
                msg=f"{query.purpose}: {type(exc).__name__}: {exc}"
                search_errors.append(msg)
                if cov:cov.search_errors.append(msg)
        coverage=finalize_coverage(coverage,atomic)

        candidates=self._dedupe(raw_results)
        evidence,fetch_errors,fetch_count=self._build_evidence(candidates,budget,atomic)
        quote_checks=verify_quotes(atomic,evidence)
        diagnostics={
            "mode":mode,
            "queries":[{"text":q.text,"purpose":q.purpose,"claim_id":q.claim_id,"priority":q.priority} for q in planned],
            "search_errors":search_errors,"fetch_errors":fetch_errors,
            "total_urls":len(raw_results),"deduped_urls":len(candidates),
            "negative_claim":any(c.is_negative for c in atomic),"breaking_news":any(c.breaking_news for c in atomic),
            "current_status":any(c.current_status for c in atomic),
            "search_provider_stats":getattr(self.search,"stats",{}),
            "claim_coverage":[self._coverage_dict(c) for c in coverage],
        }

        if not evidence:
            result=FactCheckResult(
                claim,normalized,Verdict.UNVERIFIED,.04,"شواهد قابل اتکای کافی برای ارزیابی این ادعا پیدا نشد.",
                [],"جست‌وجو یا بازیابی منبع کافی نبود؛ نتیجه‌گیری قطعی مجاز نیست.",[],[],
                atomic_claims=atomic,evidence_strength="low",missing_evidence=self._requirements(atomic,[],coverage,quote_checks),
                coverage=coverage,quote_verifications=quote_checks,diagnostics=diagnostics,
                cost_stats=self._cost_stats(started,len(planned),fetch_count,0,{})
            )
            self._save(cache_key,result);return result

        reasoning_input=self._reasoning_claim(normalized,atomic,coverage)
        calls=0
        provider_errors=[]
        try:
            initial=self.reasoner.evaluate(reasoning_input,evidence);calls+=1
        except Exception as exc:
            provider_errors.append(f"judge: {type(exc).__name__}: {exc}")
            result=FactCheckResult(
                claim,normalized,Verdict.VERIFICATION_UNAVAILABLE,.05,
                "مدل داوری نتوانست بررسی را کامل کند.",[],
                "شواهد جمع‌آوری شد اما مرحله داوری قابل اتکا در دسترس نبود.",
                evidence,[],atomic_claims=atomic,evidence_strength="low",
                missing_evidence=self._requirements(atomic,evidence,coverage,quote_checks),coverage=coverage,
                quote_verifications=quote_checks,diagnostics={**diagnostics,"reasoning_errors":provider_errors},
                cost_stats=self._cost_stats(started,len(planned),fetch_count,calls,{})
            )
            self._save(cache_key,result);return result

        final_decision=initial
        critic_used=False
        if mode=="deep" and budget.max_reasoning_calls>=2:
            try:
                if hasattr(self.reasoner,"critique"):
                    critic=self.reasoner.critique(reasoning_input,evidence,initial)
                else:
                    critic=self.reasoner.evaluate(
                        reasoning_input+"\n\nCRITIC REVIEW: re-check the initial conclusion conservatively.",evidence
                    )
                calls+=1;critic_used=True
                final_decision=self._reconcile(initial,critic)
            except Exception as exc:
                provider_errors.append(f"critic: {type(exc).__name__}: {exc}")
                final_decision=replace(
                    initial,confidence=min(initial.confidence,.70),
                    uncertainty=(initial.uncertainty+" مرحله نقد دوم کامل نشد.").strip()
                )

        contradictions=build_contradictions(final_decision,evidence,atomic[0].claim_id if atomic else "C1")
        final_decision=replace(
            final_decision,contradictions=contradictions,
            conflict_detected=final_decision.conflict_detected or any(c.severity>=.6 and not c.resolved for c in contradictions),
        )
        final_decision,profile=apply_guardrails(
            final_decision,evidence,atomic,coverage=coverage,quote_verifications=quote_checks,freshness=self.freshness_policy
        )
        supporting=[e.evidence_id for e in evidence if e.stance==EvidenceStance.SUPPORTS]
        contradicting=[e.evidence_id for e in evidence if e.stance==EvidenceStance.CONTRADICTS]
        missing=list(dict.fromkeys(final_decision.missing_evidence+self._requirements(atomic,evidence,coverage,quote_checks)))
        timeline=build_timeline(atomic,evidence)
        diagnostics.update({
            "independent_source_groups":independent_source_count([e for e in evidence if e.evidence_id in final_decision.citation_ids]),
            "source_chains":len({e.source_chain_id for e in evidence if e.source_chain_id}),
            "conflict_detected":final_decision.conflict_detected,
            "conflict_resolution":final_decision.conflict_resolution,
            "deep_check_recommended":self._recommend_deep(mode,atomic,final_decision,profile.independent_sources,profile.primary_count,coverage),
            "critic_used":critic_used,"reasoning_errors":provider_errors,
        })
        usage=dict(initial.usage)
        if critic_used:
            usage=final_decision.usage or usage
        result=FactCheckResult(
            claim,normalized,final_decision.verdict,round(final_decision.confidence,3),final_decision.summary,
            final_decision.key_points,final_decision.uncertainty,evidence,final_decision.citation_ids,
            atomic_claims=atomic,evidence_strength=profile.strength,supporting_evidence_ids=supporting,
            contradicting_evidence_ids=contradicting,missing_evidence=missing,timeline=timeline,coverage=coverage,
            contradictions=contradictions,quote_verifications=quote_checks,diagnostics=diagnostics,
            cost_stats=self._cost_stats(started,len(planned),fetch_count,calls,usage),
            analysis={
                "argument":analyze_argument(normalized),"framing":analyze_framing(normalized),
                "fetch_provider_stats":getattr(self.fetcher,"stats",{}) if self.fetcher else {},
            },
        )
        self._save(cache_key,result);return result

    def _build_evidence(self,results:Sequence[SearchResult],budget:Budget,claims:Sequence[Claim]):
        full_claim=" ".join(c.atomic_text for c in claims)
        provisional=[];errors=[];fetches=0
        for result in results:
            excerpt=result.snippet.strip()
            relevance=lexical_relevance(full_claim,f"{result.title} {excerpt}")
            if self.fetcher and fetches<budget.max_fetches:
                try:
                    try:fetched=self.fetcher.fetch_text(result.url,budget.max_page_chars,full_claim)
                    except TypeError:fetched=self.fetcher.fetch_text(result.url,budget.max_page_chars)
                    fetches+=1
                    if fetched:
                        excerpt=fetched;relevance=max(relevance,lexical_relevance(full_claim,fetched))
                except Exception as exc:
                    fetches+=1;errors.append(f"{domain_of(result.url)}: {type(exc).__name__}: {exc}")
            if not excerpt:continue
            assessment=self.source_policy.primary_assessment(result,excerpt)
            kind=self.source_policy.classify(result,excerpt)
            role=self.source_policy.role(result,excerpt)
            scored=replace(result,source_kind=kind)
            score=self.source_policy.score(scored,excerpt,relevance)
            try:canon=canonical_url(result.url)
            except ValueError:continue
            state=self.source_policy.document_state(excerpt)
            if state in {DocumentState.RETRACTED,DocumentState.DELETED}:
                score*=.4
            elif state==DocumentState.SUPERSEDED:
                score*=.65
            proves=role in {SourceRole.OFFICIAL_PARTY_STATEMENT,SourceRole.PRIMARY_DOCUMENT}
            document_claim=any(c.claim_type in {ClaimType.APPOINTMENT,ClaimType.MEMBERSHIP,ClaimType.LEGAL,ClaimType.CONSTITUTIONAL,ClaimType.QUOTE} for c in claims)
            underlying=(
                assessment.is_primary and document_claim
                or role in {SourceRole.DIRECT_REPORTING,SourceRole.INDEPENDENT_REPORTING,SourceRole.SECONDARY_REPORTING}
            )
            if role==SourceRole.OFFICIAL_PARTY_STATEMENT and not document_claim:
                underlying=False
            provisional.append(Evidence(
                evidence_id="",url=result.url,canonical_url=canon,title=result.title,domain=domain_of(result.url),
                publisher=result.publisher,excerpt=excerpt[:budget.max_page_chars],published_at=result.published_at,
                updated_at=result.updated_at,source_kind=kind,source_role=role,quality_score=score,relevance_score=relevance,
                independence_key=self.source_policy.independence_key(result.url),cited_source=self.source_policy.cited_source_hint(result),
                document_state=state,correction_status="corrected" if state==DocumentState.CORRECTED else None,
                retraction_status="retracted" if state==DocumentState.RETRACTED else None,
                primary_assessment=assessment,proves_statement_made=proves,supports_underlying_fact=underlying,
                retrieval_purposes=list(result.retrieval_purposes),
            ))
        provisional=assign_source_chains(provisional)
        provisional.sort(key=lambda e:(e.primary_assessment.is_primary,e.quality_score+e.relevance_score*.18),reverse=True)

        selected=[];chosen=set()
        def take(item):
            if item.canonical_url in chosen or len(selected)>=budget.max_sources:return False
            selected.append(item);chosen.add(item.canonical_url);return True
        for item in provisional:
            if item.primary_assessment.is_primary:take(item)
        for purpose in ("challenge","negative_existence","replacement","freshness"):
            for item in provisional:
                if purpose in item.retrieval_purposes:
                    take(item);break
        for item in provisional:
            if item.canonical_url in chosen:continue
            if any(
                item.independence_key==x.independence_key or
                (item.source_chain_confidence>=.7 and x.source_chain_id==item.source_chain_id)
                for x in selected
            ):continue
            take(item)
        for item in provisional:take(item)
        return [replace(e,evidence_id=f"E{i}") for i,e in enumerate(selected,1)],errors,fetches

    @staticmethod
    def _dedupe(results:Sequence[SearchResult])->list[SearchResult]:
        by={}
        for item in results:
            try:key=canonical_url(item.url)
            except Exception:continue
            old=by.get(key)
            if old is None or len(item.snippet)>len(old.snippet):by[key]=item
        return list(by.values())

    @staticmethod
    def _reconcile(a:ReasoningDecision,b:ReasoningDecision)->ReasoningDecision:
        usage={}
        for src in (a.usage,b.usage):
            for k,v in src.items():
                if isinstance(v,(int,float)):usage[k]=usage.get(k,0)+v
        if a.verdict==b.verdict:
            return replace(
                b,confidence=min(a.confidence,b.confidence),
                citation_ids=list(dict.fromkeys(b.citation_ids or a.citation_ids)),
                evidence_stances={**a.evidence_stances,**b.evidence_stances},
                missing_evidence=list(dict.fromkeys(a.missing_evidence+b.missing_evidence)),usage=usage,
            )
        cautious={Verdict.UNVERIFIED,Verdict.INSUFFICIENT_EVIDENCE,Verdict.CONFLICTING_EVIDENCE,Verdict.OUTDATED}
        if b.verdict in cautious:
            return replace(b,confidence=min(a.confidence,b.confidence,.62),usage=usage)
        if a.verdict in cautious:
            return replace(a,confidence=min(a.confidence,b.confidence,.62),usage=usage)
        opposites={a.verdict,b.verdict}
        if Verdict.TRUE in opposites and Verdict.FALSE in opposites:
            return ReasoningDecision(
                Verdict.CONFLICTING_EVIDENCE,min(a.confidence,b.confidence,.55),
                b.summary or a.summary,list(dict.fromkeys(a.key_points+b.key_points)),
                (a.uncertainty+" "+b.uncertainty).strip(),list(dict.fromkeys(a.citation_ids+b.citation_ids)),
                True,"Judge and critic reached materially opposite conclusions.",
                {**a.evidence_stances,**b.evidence_stances},
                list(dict.fromkeys(a.missing_evidence+b.missing_evidence)),
                a.contradictions+b.contradictions,usage,
            )
        return replace(
            b,confidence=min(a.confidence,b.confidence,.68),conflict_detected=True,
            conflict_resolution=(b.conflict_resolution or "Judge and critic disagreed; conservative reconciliation applied."),
            usage=usage,
        )

    def _requirements(self,claims:Sequence[Claim],evidence:Sequence[Evidence],coverage:Sequence[ClaimResearchCoverage],
                      quotes:Sequence[QuoteVerification])->list[str]:
        primary=[e for e in evidence if e.primary_assessment.is_primary]
        independent=independent_source_count(evidence)
        covmap={c.claim_id:c for c in coverage}
        quote_map={q.claim_id:q for q in quotes}
        missing=[]
        for claim in claims:
            cov=covmap.get(claim.claim_id)
            for req in claim.evidence_requirements:
                ids=[]
                if req.requirement_type in {RequirementType.PRIMARY_DOCUMENT,RequirementType.LAW_TEXT,RequirementType.CONSTITUTIONAL_TEXT,
                                           RequirementType.OFFICIAL_MEMBERSHIP_RECORD}:
                    ids=[e.evidence_id for e in primary]
                elif req.requirement_type==RequirementType.INDEPENDENT_CORROBORATION:
                    ids=[e.evidence_id for e in evidence] if independent>=2 else []
                elif req.requirement_type==RequirementType.BROAD_ARCHIVE_SEARCH:
                    if cov and cov.archive_search_attempted:ids=["SEARCH_COVERAGE"]
                elif req.requirement_type==RequirementType.ABSENCE_LIMITATIONS:
                    ids=["POLICY"]
                elif req.requirement_type==RequirementType.RECENT_AUTHORITATIVE_RECORD:
                    ids=[e.evidence_id for e in evidence if not self.freshness_policy.evidence_is_stale(e,[claim]) and e.quality_score>=.65]
                elif req.requirement_type==RequirementType.REPLACEMENT_SEARCH:
                    if cov and cov.replacement_search_attempted:ids=["SEARCH_COVERAGE"]
                elif req.requirement_type==RequirementType.ORIGINAL_TRANSCRIPT:
                    q=quote_map.get(claim.claim_id)
                    if q and q.original_source_found and q.status in {QuoteMatchStatus.EXACT_MATCH,QuoteMatchStatus.NORMALIZED_MATCH}:
                        ids=q.evidence_ids
                req.satisfied=bool(ids);req.evidence_ids=ids
                if req.mandatory and not req.satisfied:
                    missing.append(f"{claim.claim_id}:{req.requirement_type.value}")
            if claim.is_negative:
                missing.append(f"{claim.claim_id}:absence_cannot_be_proven_by_search_failure_alone")
        return list(dict.fromkeys(missing))

    def _cache_ttl(self,claims:Sequence[Claim],budget:Budget)->int:
        target=self.freshness_policy.target_seconds(claims)
        return min(budget.cache_ttl_seconds,target) if any(c.current_status or c.breaking_news or c.high_impact for c in claims) else budget.cache_ttl_seconds

    @staticmethod
    def _reasoning_claim(normalized:str,claims:Sequence[Claim],coverage:Sequence[ClaimResearchCoverage])->str:
        cov={x.claim_id:x.coverage_score for x in coverage}
        atoms="\n".join(
            f"{c.claim_id}: {c.atomic_text} | type={c.claim_type.value} | negative={c.is_negative} | "
            f"current={c.current_status} | high_impact={c.high_impact} | search_coverage={cov.get(c.claim_id,0):.2f}"
            for c in claims
        )
        return f"ORIGINAL CLAIM:\n{normalized}\n\nATOMIC CLAIMS:\n{atoms}"

    @staticmethod
    def _recommend_deep(mode,claims,decision,independent,primary,coverage)->bool:
        if mode=="deep":return False
        low_cov=any(c.coverage_score<.75 for c in coverage)
        return bool(
            decision.conflict_detected or any(c.is_negative or c.high_impact or c.breaking_news or c.current_status for c in claims)
            or decision.confidence<.68 or (primary==0 and independent<2) or low_cov
        )

    @staticmethod
    def _cost_stats(started,queries,fetches,reasoning_calls,usage):
        duration=(datetime.now(timezone.utc)-started).total_seconds()
        return {
            "search_queries":queries,"pages_fetched":fetches,"reasoning_calls":reasoning_calls,
            "input_tokens":usage.get("input_tokens"),"output_tokens":usage.get("output_tokens"),
            "total_tokens":usage.get("total_tokens"),"estimated_cost":usage.get("estimated_cost"),
            "duration_seconds":round(duration,3),
        }

    @staticmethod
    def _coverage_dict(c:ClaimResearchCoverage)->dict[str,Any]:
        return {
            "claim_id":c.claim_id,"planned_purposes":c.planned_purposes,"executed_purposes":c.executed_purposes,
            "successful_purposes":c.successful_purposes,"coverage_score":c.coverage_score,
            "primary_search_attempted":c.primary_search_attempted,"challenge_search_attempted":c.challenge_search_attempted,
            "archive_search_attempted":c.archive_search_attempted,"replacement_search_attempted":c.replacement_search_attempted,
            "search_errors":c.search_errors,
        }

    def _save(self,key,result):
        if self.cache:self.cache.set(key,result.to_dict())

    @staticmethod
    def _from_cache(data:dict[str,Any])->FactCheckResult:
        def enum(cls,val,default):
            try:return cls(val)
            except Exception:return default
        evidence=[]
        for x in data.get("evidence",[]):
            pa=x.get("primary_assessment") or {}
            evidence.append(Evidence(
                evidence_id=x["evidence_id"],url=x["url"],title=x["title"],domain=x["domain"],excerpt=x["excerpt"],
                published_at=x.get("published_at"),source_kind=enum(SourceKind,x.get("source_kind"),SourceKind.UNKNOWN),
                quality_score=float(x.get("quality_score",0)),independence_key=x.get("independence_key",""),
                canonical_url=x.get("canonical_url",""),publisher=x.get("publisher"),updated_at=x.get("updated_at"),
                event_date=x.get("event_date"),retrieved_at=x.get("retrieved_at",""),
                source_role=enum(SourceRole,x.get("source_role"),SourceRole.UNKNOWN),relevance_score=float(x.get("relevance_score",0)),
                source_chain_id=x.get("source_chain_id",""),source_chain_confidence=float(x.get("source_chain_confidence",0)),
                source_chain_reason=x.get("source_chain_reason",""),cited_source=x.get("cited_source"),
                stance=enum(EvidenceStance,x.get("stance"),EvidenceStance.UNCLEAR),correction_status=x.get("correction_status"),
                retraction_status=x.get("retraction_status"),document_state=enum(DocumentState,x.get("document_state"),DocumentState.UNKNOWN),
                primary_assessment=PrimarySourceAssessment(**{k:pa.get(k,v) for k,v in {
                    "is_primary":False,"confidence":0.0,"issuer":None,"publisher":None,"document_type":None,
                    "authority_match":False,"originality_signals":[],"warning_signals":[],"reason":""
                }.items()}),
                proves_statement_made=bool(x.get("proves_statement_made")),supports_underlying_fact=bool(x.get("supports_underlying_fact")),
                retrieval_purposes=list(x.get("retrieval_purposes",[])),
            ))
        claims=[]
        for x in data.get("atomic_claims",[]):
            refs=[EntityRef(**r) for r in x.get("entity_refs",[])]
            dinfo=[DateInfo(**d) for d in x.get("date_info",[])]
            reqs=[]
            for r in x.get("evidence_requirements",[]):
                reqs.append(EvidenceRequirement(
                    enum(RequirementType,r.get("requirement_type"),RequirementType.INDEPENDENT_CORROBORATION),
                    r.get("claim_id",x.get("claim_id","C1")),bool(r.get("mandatory")),bool(r.get("preferred",True)),
                    bool(r.get("satisfied")),list(r.get("evidence_ids",[])),r.get("notes","")
                ))
            claims.append(Claim(
                x["claim_id"],x["original_text"],x["normalized_text"],x["atomic_text"],
                enum(ClaimType,x.get("claim_type"),ClaimType.UNKNOWN),enum(Intent,x.get("intent"),Intent.FACT_CHECK),
                list(x.get("entities",[])),refs,list(x.get("dates",[])),dinfo,list(x.get("dependencies",[])),
                list(x.get("required_evidence",[])),reqs,bool(x.get("is_negative")),bool(x.get("high_impact")),
                bool(x.get("current_status")),bool(x.get("breaking_news")),list(x.get("quoted_texts",[])),x.get("reference_date")
            ))
        coverage=[ClaimResearchCoverage(**c) for c in data.get("coverage",[])]
        quotes=[QuoteVerification(
            q["claim_id"],q["quote"],enum(QuoteMatchStatus,q.get("status"),QuoteMatchStatus.NOT_FOUND),
            list(q.get("evidence_ids",[])),bool(q.get("original_source_found")),float(q.get("confidence",0))
        ) for q in data.get("quote_verifications",[])]
        contradictions=[Contradiction(
            c["claim_id"],c["evidence_a"],c["evidence_b"],enum(ContradictionType,c.get("contradiction_type"),ContradictionType.DIRECT_FACT_CONFLICT),
            float(c.get("severity",.5)),bool(c.get("resolved")),c.get("resolution","")
        ) for c in data.get("contradictions",[])]
        timeline=[TimelineEvent(**t) for t in data.get("timeline",[])]
        return FactCheckResult(
            claim=data["claim"],normalized_claim=data["normalized_claim"],verdict=enum(Verdict,data.get("verdict"),Verdict.UNVERIFIED),
            confidence=float(data.get("confidence",0)),summary=data.get("summary",""),key_points=list(data.get("key_points",[])),
            uncertainty=data.get("uncertainty",""),evidence=evidence,citation_ids=list(data.get("citation_ids",[])),atomic_claims=claims,
            evidence_strength=data.get("evidence_strength","low"),supporting_evidence_ids=list(data.get("supporting_evidence_ids",[])),
            contradicting_evidence_ids=list(data.get("contradicting_evidence_ids",[])),missing_evidence=list(data.get("missing_evidence",[])),
            timeline=timeline,coverage=coverage,contradictions=contradictions,quote_verifications=quotes,
            from_cache=True,diagnostics=dict(data.get("diagnostics",{})),cost_stats=dict(data.get("cost_stats",{})),analysis=dict(data.get("analysis",{})),
        )
