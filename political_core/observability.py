from __future__ import annotations
import json,threading
from collections import deque
from dataclasses import asdict,dataclass
from datetime import datetime,timezone
from pathlib import Path
from typing import Any,Protocol
from .models import FactCheckResult

@dataclass(slots=True)
class RequestMetric:
    request_id:str;timestamp:str;mode:str;success:bool;claim_count:int;search_count:int;fetch_count:int;reasoning_calls:int;final_cache_hit:bool;search_cache_hits:int;fetch_cache_hits:int;latency_seconds:float|None;verdict:str|None;confidence:float|None;evidence_strength:str|None;independent_source_count:int;primary_source_count:int;error_count:int;error_type:str|None=None;error_stage:str|None=None
    def to_dict(self)->dict[str,Any]:return asdict(self)

class MetricsSink(Protocol):
    def emit(self,metric:RequestMetric)->None:...

class MemoryMetricsSink:
    def __init__(self,max_entries:int=10000)->None:self.rows=deque(maxlen=max(1,int(max_entries)));self._lock=threading.Lock()
    def emit(self,metric:RequestMetric)->None:
        with self._lock:self.rows.append(metric)

class JsonlMetricsSink:
    def __init__(self,path:str|Path,*,max_bytes:int|None=None)->None:self.path=Path(path);self._lock=threading.Lock();self.max_bytes=max_bytes
    def _rotate(self):
        if self.max_bytes and self.path.exists() and self.path.stat().st_size>=self.max_bytes:
            rotated=self.path.with_suffix(self.path.suffix+".1")
            if rotated.exists():rotated.unlink()
            self.path.replace(rotated)
    def emit(self,metric:RequestMetric)->None:
        line=json.dumps(metric.to_dict(),ensure_ascii=False,separators=(",",":"))
        with self._lock:
            self._rotate()
            with self.path.open("a",encoding="utf-8") as handle:handle.write(line+"\n")

def metric_from_result(result:FactCheckResult,request_id:str,*,mode:str,latency_seconds:float|None=None)->RequestMetric:
    diagnostics=result.diagnostics or {};cost=result.cost_stats or {};search_stats=diagnostics.get("search_provider_stats",{}) if isinstance(diagnostics,dict) else {};fetch_stats=(result.analysis or {}).get("fetch_provider_stats",{}) if isinstance(result.analysis,dict) else {};cited=set(result.citation_ids);cited_evidence=[e for e in result.evidence if e.evidence_id in cited];errors=list(diagnostics.get("search_errors",[]))+list(diagnostics.get("fetch_errors",[]))+list(diagnostics.get("reasoning_errors",[]))
    if result.from_cache:
        search_hits=search_calls=fetch_hits=fetch_calls=0
    else:
        search_hits=int(search_stats.get("cache_hits",0) or 0);search_calls=int(search_stats.get("provider_calls",0) or 0);fetch_hits=int(fetch_stats.get("cache_hits",0) or 0);fetch_calls=int(fetch_stats.get("provider_calls",0) or 0)
    return RequestMetric(request_id,datetime.now(timezone.utc).isoformat(),mode,True,len(result.atomic_claims),search_calls,fetch_calls,int(cost.get("reasoning_calls",0) or 0),bool(result.from_cache),search_hits,fetch_hits,round(float(latency_seconds),6) if latency_seconds is not None else None,result.verdict.value,float(result.confidence),str(result.evidence_strength),int(diagnostics.get("independent_source_groups",0) or 0),sum(1 for e in cited_evidence if e.primary_assessment.is_primary),len(errors))

def metric_from_error(request_id:str,*,mode:str,latency_seconds:float,error_type:str,error_stage:str="verification")->RequestMetric:
    return RequestMetric(request_id,datetime.now(timezone.utc).isoformat(),mode,False,0,0,0,0,False,0,0,round(float(latency_seconds),6),None,None,None,0,0,1,error_type,error_stage)
