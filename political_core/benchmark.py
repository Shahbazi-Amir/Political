from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .models import FactCheckResult

CALIBRATION_BINS = ((0.0,0.2),(0.2,0.4),(0.4,0.6),(0.6,0.8),(0.8,0.9),(0.9,1.000001))


@dataclass(slots=True)
class CostSummary:
    cases: int
    average_search_queries: float | None
    average_pages_fetched: float | None
    average_reasoning_calls: float | None
    average_input_tokens: float | None
    average_output_tokens: float | None
    average_total_tokens: float | None
    average_latency_seconds: float | None
    total_estimated_cost: float | None
    final_cache_hits: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "cases": self.cases,
            "average_search_queries": self.average_search_queries,
            "average_pages_fetched": self.average_pages_fetched,
            "average_reasoning_calls": self.average_reasoning_calls,
            "average_input_tokens": self.average_input_tokens,
            "average_output_tokens": self.average_output_tokens,
            "average_total_tokens": self.average_total_tokens,
            "average_latency_seconds": self.average_latency_seconds,
            "total_estimated_cost": self.total_estimated_cost,
            "final_cache_hits": self.final_cache_hits,
        }


def _avg(values: list[float]) -> float | None:
    return round(sum(values)/len(values), 4) if values else None


def summarize_costs(results: Iterable[FactCheckResult]) -> CostSummary:
    rows=list(results)
    def values(key: str) -> list[float]:
        out=[]
        for row in rows:
            value=row.cost_stats.get(key)
            if isinstance(value,(int,float)):
                out.append(float(value))
        return out
    costs=values("estimated_cost")
    return CostSummary(
        cases=len(rows),
        average_search_queries=_avg(values("search_queries")),
        average_pages_fetched=_avg(values("pages_fetched")),
        average_reasoning_calls=_avg(values("reasoning_calls")),
        average_input_tokens=_avg(values("input_tokens")),
        average_output_tokens=_avg(values("output_tokens")),
        average_total_tokens=_avg(values("total_tokens")),
        average_latency_seconds=_avg(values("duration_seconds")),
        total_estimated_cost=round(sum(costs),6) if costs else None,
        final_cache_hits=sum(1 for row in rows if row.from_cache),
    )


def calibration_report(records: Iterable[Mapping[str, Any]], *, high_confidence: float=.8) -> dict[str, Any]:
    rows=[]
    for record in records:
        if "confidence" not in record:
            continue
        confidence=max(0.0,min(1.0,float(record["confidence"])))
        expected=record.get("expected_verdict")
        actual=record.get("actual_verdict")
        accepted=set(record.get("acceptable_verdicts") or ([expected] if expected is not None else []))
        if not accepted or actual is None:
            continue
        correct=actual in accepted
        rows.append((confidence,correct))
    if not rows:
        return {
            "cases":0,"brier_score":None,"expected_calibration_error":None,
            "false_high_confidence_rate":None,"bins":{},
        }

    bins={}
    ece=0.0
    for lo,hi in CALIBRATION_BINS:
        bucket=[x for x in rows if lo<=x[0]<hi]
        if not bucket:
            continue
        mean_conf=sum(x[0] for x in bucket)/len(bucket)
        accuracy=sum(1 for _,ok in bucket if ok)/len(bucket)
        label=f"{lo:.1f}-{min(1.0,hi):.1f}"
        bins[label]={
            "n":len(bucket),
            "mean_confidence":round(mean_conf,4),
            "accuracy":round(accuracy,4),
            "gap":round(abs(mean_conf-accuracy),4),
        }
        ece += len(bucket)/len(rows)*abs(mean_conf-accuracy)

    brier=sum((conf-(1.0 if ok else 0.0))**2 for conf,ok in rows)/len(rows)
    high=[ok for conf,ok in rows if conf>=high_confidence]
    false_high=sum(1 for ok in high if not ok)/len(high) if high else None
    return {
        "cases":len(rows),
        "brier_score":round(brier,4),
        "expected_calibration_error":round(ece,4),
        "false_high_confidence_rate":round(false_high,4) if false_high is not None else None,
        "bins":bins,
    }
