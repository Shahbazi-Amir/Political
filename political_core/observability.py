from __future__ import annotations
import json,threading
from dataclasses import asdict,dataclass
from datetime import datetime,timezone
from pathlib import Path
from typing import Any,Protocol
from .models import FactCheckResult

@dataclass(slots=True)
class RequestMetric:
    request_id:str;timestamp:str;mode:str;claim_count:int;search_count:int;fetch_count:int;reasoning_calls:int;final_cache_hit:bool;search_cache_hits:int;fetch_cache_hits:int;latency_seconds:float|None;verdict:str;confidence:float;evidence_strength:str;independent_source_count:int;primary_source_count:int;error_count:int
    def to_dict(self)->dict[str,Any]:return asdict(self)
class MetricsSink(Protocol):
    def emit(self,metric:RequestMetric)->None:...
class MemoryMetricsSink:
    def __init__(self)->None:self.rows=[];self._lock=threading.Lock()
    def emit(self,metric:RequestMetric)->None:
        with self._lock:self.rows.append(metric)
class JsonlMetricsSink:
    def __init__(self,path:str|Path)->None:self.path=Path(path);self._lock=threading.Lock()
    def emit(self,metric:RequestMetric)->None:
        line=json.dumps(metric.to_dict(),ensure_ascii=False,separators=(",",":"))
        with self._lock:
            with self.path.open("a",encoding="utf-8") as handle:handle.write(line+"\n")
def metric_from_result(result:FactCheckResult,request_id:str,*,mode:str,latency_seconds:float|None=None)->RequestMetric:
    diagnostics=result.diagnostics or {};cost=result.cost_stats or {};search_stats=diagnostics.get("search_provider_stats",{}) if isinstance(diagnostics,dict) else {};fetch_stats=(result.analysis or {}).get("fetch_provider_stats",{}) if isinstance(result.analysis,dict) else {};cited=set(result.citation_ids);cited_evidence=[e for e in result.evidence if e.evidence_id in cited];errors=list(diagnostics.get("search_errors",[]))+list(diagnostics.get("fetch_errors",[]))+list(diagnostics.get("reasoning_errors",[]))
    return RequestMetric(request_id,datetime.now(timezone.utc).isoformat(),mode,len(result.atomic_claims),int(cost.get("search_queries",0) or 0),int(cost.get("pages_fetched",0) or 0),int(cost.get("reasoning_calls",0) or 0),bool(result.from_cache),int(search_stats.get("cache_hits",0) or 0),int(fetch_stats.get("cache_hits",0) or 0),round(float(latency_seconds),6) if latency_seconds is not None else None,result.verdict.value,float(result.confidence),str(result.evidence_strength),int(diagnostics.get("independent_source_groups",0) or 0),sum(1 for e in cited_evidence if e.primary_assessment.is_primary),len(errors))
