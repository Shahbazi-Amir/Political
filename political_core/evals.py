from __future__ import annotations
from collections import Counter,defaultdict
from pathlib import Path
from .benchmark import calibration_report
from .dataset import REQUIRED_CATEGORIES,is_auditable_verified_case,iter_jsonl
from .models import Verdict

def _avg(values):return round(sum(values)/len(values),4) if values else None
def _set_f1(pred:set[str],gold:set[str])->float|None:
    if not gold and not pred:return 1.0
    if not gold or not pred:return 0.0
    tp=len(pred&gold);precision=tp/len(pred);recall=tp/len(gold);return 2*precision*recall/(precision+recall) if precision+recall else 0.0
def evaluate_jsonl(path:str|Path)->dict:
    rows=list(iter_jsonl(path));valid_verdicts={v.value for v in Verdict};verified=[];invalid=[]
    for line_no,r in rows:
        if r.get("review_status")!="verified" or r.get("synthetic",False):continue
        expected=r.get("expected_verdict");actual=r.get("actual_verdict")
        if expected not in valid_verdicts or actual not in valid_verdicts:invalid.append({"line":line_no,"reason":"invalid_or_missing_verdict"});continue
        if not r.get("ground_truth_sources"):invalid.append({"line":line_no,"reason":"verified_case_missing_ground_truth_sources"});continue
        if not is_auditable_verified_case(r):invalid.append({"line":line_no,"reason":"verified_case_not_auditable"});continue
        verified.append(r)
    if not verified:return {"total_cases":len(rows),"verified_cases":0,"invalid_verified_cases":invalid,"benchmark_sample_sufficient":False,"production_accuracy_established":False,"note":"Production political accuracy is not yet statistically established."}
    correct=acceptable=high_total=high_correct=false_high=citation_ok=0;bins=defaultdict(lambda:{"n":0,"correct":0});searches=[];reasoning=[];latencies=[];coverages=[];primary_scores=[];independence_scores=[];tags=Counter()
    for r in verified:
        actual=r["actual_verdict"];expected=r["expected_verdict"];accepted=set(r.get("acceptable_verdicts") or [expected]);is_correct=actual==expected;is_acceptable=actual in accepted;correct+=is_correct;acceptable+=is_acceptable;conf=min(1,max(0,float(r.get("confidence",0))))
        if conf>=.8:high_total+=1;high_correct+=is_acceptable;false_high+=int(not is_acceptable)
        if conf<.2:label="0.0-0.2"
        elif conf<.4:label="0.2-0.4"
        elif conf<.6:label="0.4-0.6"
        elif conf<.8:label="0.6-0.8"
        elif conf<.9:label="0.8-0.9"
        else:label="0.9-1.0"
        bins[label]["n"]+=1;bins[label]["correct"]+=is_acceptable;cited=set(r.get("citation_ids",[]));available=set(r.get("available_evidence_ids",[]));required=bool(r.get("citation_required",bool(cited)));citation_ok+=int(cited.issubset(available) and (not required or bool(cited)))
        if "predicted_primary_ids" in r or "expected_primary_ids" in r:primary_scores.append(_set_f1(set(r.get("predicted_primary_ids",[])),set(r.get("expected_primary_ids",[]))))
        if r.get("predicted_independent_sources") is not None and r.get("expected_independent_sources") is not None:
            pred=int(r["predicted_independent_sources"]);gold=int(r["expected_independent_sources"]);independence_scores.append(1.0 if pred==gold else max(0.0,1-abs(pred-gold)/max(1,gold)))
        for key,target in (("search_queries",searches),("reasoning_calls",reasoning),("latency_seconds",latencies),("coverage_score",coverages)):
            if r.get(key) is not None:target.append(float(r[key]))
        category=r.get("category")
        if category:tags[category]+=1
        tags.update(set(r.get("tags",[])))
    n=len(verified);calibration={k:{"n":v["n"],"accuracy":round(v["correct"]/v["n"],4)} for k,v in bins.items() if v["n"]};category_ready=all(tags.get(tag,0)>=5 for tag in REQUIRED_CATEGORIES);sample_ready=n>=100 and category_ready;cal=calibration_report(verified)
    return {"total_cases":len(rows),"verified_cases":n,"invalid_verified_cases":invalid,"benchmark_sample_sufficient":sample_ready,"critical_tag_counts":{k:tags.get(k,0) for k in REQUIRED_CATEGORIES},"production_accuracy_established":sample_ready,"verdict_accuracy":round(correct/n,4),"acceptable_verdict_accuracy":round(acceptable/n,4),"high_confidence_accuracy":round(high_correct/high_total,4) if high_total else None,"high_confidence_predictions":high_total,"false_high_confidence_count":false_high,"false_high_confidence_rate":round(false_high/high_total,4) if high_total else None,"citation_validity":round(citation_ok/n,4),"primary_source_precision_f1":_avg([x for x in primary_scores if x is not None]),"source_independence_accuracy":_avg(independence_scores),"coverage_rate":_avg(coverages),"average_search_queries":_avg(searches),"average_reasoning_calls":_avg(reasoning),"average_latency":_avg(latencies),"brier_score":cal["brier_score"],"expected_calibration_error":cal["expected_calibration_error"],"calibration_bins":calibration,"note":None if sample_ready else "Production political accuracy is not yet statistically established."}
