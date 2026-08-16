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
    requests:int;successes:int;functional_failures:int;exceptions:int;concurrency:int;duration_seconds:float;throughput_rps:float;error_rate:float;p50_seconds:float|None;p95_seconds:float|None;p99_seconds:float|None;max_seconds:float|None;errors:dict[str,int]
    @property
    def failures(self)->int:return self.functional_failures+self.exceptions
    def to_dict(self)->dict[str,Any]:
        out=asdict(self);out["failures"]=self.failures;return out

def run_load_test(handler:Callable[[Any],Any],payloads:Iterable[Any],*,concurrency:int=10,success_predicate:Callable[[Any],bool]|None=None)->LoadTestResult:
    payloads=list(payloads);concurrency=max(1,int(concurrency));started=time.perf_counter();success_lat=[];all_lat=[];errors={};functional=exceptions=successes=0
    def one(payload):
        t0=time.perf_counter()
        try:
            response=handler(payload);ok=success_predicate(response) if success_predicate else True
            return "success" if ok else "functional_failure",time.perf_counter()-t0,None
        except Exception as exc:return "exception",time.perf_counter()-t0,f"{type(exc).__name__}: {exc}"
    with ThreadPoolExecutor(max_workers=concurrency) as pool:rows=[f.result() for f in as_completed([pool.submit(one,p) for p in payloads])]
    for status,latency,error in rows:
        all_lat.append(latency)
        if status=="success":successes+=1;success_lat.append(latency)
        elif status=="functional_failure":functional+=1
        else:exceptions+=1
        if error:errors[error]=errors.get(error,0)+1
    duration=time.perf_counter()-started;failures=functional+exceptions
    return LoadTestResult(len(rows),successes,functional,exceptions,concurrency,round(duration,6),round(len(rows)/duration,4) if duration else 0.0,round(failures/len(rows),6) if rows else 0.0,_percentile(success_lat,50),_percentile(success_lat,95),_percentile(success_lat,99),round(max(all_lat),6) if all_lat else None,errors)
