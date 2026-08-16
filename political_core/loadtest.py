from __future__ import annotations
import math,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from dataclasses import asdict,dataclass
from typing import Any,Callable,Iterable

def _percentile(values:list[float],p:float)->float|None:
    if not values:return None
    values=sorted(values);rank=max(1,math.ceil((p/100.0)*len(values)))-1
    return round(values[min(rank,len(values)-1)],6)

@dataclass(slots=True)
class LoadTestResult:
    requests:int;successes:int;failures:int;concurrency:int;duration_seconds:float;error_rate:float;p50_seconds:float|None;p95_seconds:float|None;p99_seconds:float|None;max_seconds:float|None;errors:dict[str,int]
    def to_dict(self)->dict[str,Any]:return asdict(self)

def run_load_test(handler:Callable[[Any],Any],payloads:Iterable[Any],*,concurrency:int=10)->LoadTestResult:
    payloads=list(payloads);concurrency=max(1,int(concurrency));started=time.perf_counter();latencies=[];errors={}
    def one(payload):
        t0=time.perf_counter()
        try:handler(payload);return True,time.perf_counter()-t0,None
        except Exception as exc:return False,time.perf_counter()-t0,f"{type(exc).__name__}: {exc}"
    with ThreadPoolExecutor(max_workers=concurrency) as pool:rows=[f.result() for f in as_completed([pool.submit(one,p) for p in payloads])]
    for ok,latency,error in rows:
        latencies.append(latency)
        if not ok and error:errors[error]=errors.get(error,0)+1
    failures=sum(1 for ok,_,_ in rows if not ok);successes=len(rows)-failures;duration=time.perf_counter()-started
    return LoadTestResult(len(rows),successes,failures,concurrency,round(duration,6),round(failures/len(rows),6) if rows else 0.0,_percentile(latencies,50),_percentile(latencies,95),_percentile(latencies,99),round(max(latencies),6) if latencies else None,errors)
