from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
def _iter_cases(path:str|Path):
    with open(path,encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if line:yield json.loads(line)
def _avg(values):return round(sum(values)/len(values),4) if values else None
def _set_f1(pred:set[str],gold:set[str])->float|None:
    if not gold and not pred:return 1.0
    if not gold or not pred:return 0.0
    tp=len(pred&gold);precision=tp/len(pred);recall=tp/len(gold);return 2*precision*recall/(precision+recall) if precision+recall else 0.0
def evaluate_jsonl(path:str|Path)->dict:
    rows=list(_iter_cases(path));verified=[r for r in rows if r.get("review_status","verified")=="verified" and r.get("expected_verdict") and not r.get("synthetic",False)]
    if not verified:return {"total_cases":len(rows),"verified_cases":0,"production_accuracy_established":False,"note":"Production political accuracy is not yet statistically established."}
    correct=acceptable=high_total=high_correct=false_high=citation_ok=0;bins=defaultdict(lambda:{"n":0,"correct":0});searches=[];reasoning=[];latencies=[];coverages=[];primary_scores=[];independence_scores=[]
    for r in verified:
        actual=r.get("actual_verdict");expected=r.get("expected_verdict");accepted=set(r.get("acceptable_verdicts") or [expected]);is_correct=actual==expected;is_acceptable=actual in accepted;correct+=is_correct;acceptable+=is_acceptable;conf=float(r.get("confidence",0))
        if conf>=.8:high_total+=1;high_correct+=is_acceptable;false_high+=int(not is_acceptable)
        b=min(9,int(conf*10));label=f"{b/10:.1f}-{(b+1)/10:.1f}";bins[label]["n"]+=1;bins[label]["correct"]+=is_acceptable
        cited=set(r.get("citation_ids",[]));available=set(r.get("available_evidence_ids",[]));citation_ok+=int(cited.issubset(available))
        if "predicted_primary_ids" in r or "expected_primary_ids" in r:primary_scores.append(_set_f1(set(r.get("predicted_primary_ids",[])),set(r.get("expected_primary_ids",[]))))
        if r.get("predicted_independent_sources") is not None and r.get("expected_independent_sources") is not None:
            pred=int(r["predicted_independent_sources"]);gold=int(r["expected_independent_sources"]);independence_scores.append(1.0 if pred==gold else max(0.0,1-abs(pred-gold)/max(1,gold)))
        for key,target in (("search_queries",searches),("reasoning_calls",reasoning),("latency_seconds",latencies),("coverage_score",coverages)):
            if r.get(key) is not None:target.append(float(r[key]))
    n=len(verified);calibration={k:{"n":v["n"],"accuracy":round(v["correct"]/v["n"],4)} for k,v in sorted(bins.items()) if v["n"]}
    return {"total_cases":len(rows),"verified_cases":n,"production_accuracy_established":n>=30,"verdict_accuracy":round(correct/n,4),"acceptable_verdict_accuracy":round(acceptable/n,4),"high_confidence_accuracy":round(high_correct/high_total,4) if high_total else None,"false_high_confidence_rate":round(false_high/high_total,4) if high_total else None,"citation_validity":round(citation_ok/n,4),"primary_source_precision_f1":_avg([x for x in primary_scores if x is not None]),"source_independence_accuracy":_avg(independence_scores),"coverage_rate":_avg(coverages),"average_search_queries":_avg(searches),"average_reasoning_calls":_avg(reasoning),"average_latency":_avg(latencies),"calibration_bins":calibration,"note":None if n>=30 else "Production political accuracy is not yet statistically established."}
