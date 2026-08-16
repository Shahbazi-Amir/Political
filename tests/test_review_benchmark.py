from __future__ import annotations
from political_core.benchmark import summarize_costs
from political_core.models import FactCheckResult,Verdict


def result(*,cached=False,search_hits=0,search_calls=0,fetch_hits=0,fetch_calls=0):
    return FactCheckResult(
        "ادعا","ادعا",Verdict.TRUE,.8,"ok",[],"",[],[],from_cache=cached,
        diagnostics={"search_provider_stats":{"cache_hits":search_hits,"provider_calls":search_calls}},
        analysis={"fetch_provider_stats":{"cache_hits":fetch_hits,"provider_calls":fetch_calls}},
        cost_stats={"search_queries":2,"pages_fetched":1,"reasoning_calls":1,"input_tokens":100,"output_tokens":20,"total_tokens":120,"duration_seconds":.5,"estimated_cost":.001},
    )


def test_cost_summary_includes_provider_cache_efficiency():
    summary=summarize_costs([result(search_hits=2,search_calls=1,fetch_hits=1,fetch_calls=1),result(cached=True,search_hits=1,search_calls=0)])
    data=summary.to_dict()
    assert data["final_cache_hits"]==1
    assert data["search_cache_hits"]==3 and data["search_provider_calls"]==1 and data["search_cache_hit_rate"]==.75
    assert data["fetch_cache_hits"]==1 and data["fetch_provider_calls"]==1 and data["fetch_cache_hit_rate"]==.5
    assert data["average_reasoning_calls"]==1.0 and data["total_estimated_cost"]==.002
