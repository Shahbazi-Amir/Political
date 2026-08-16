from __future__ import annotations
from collections import Counter,defaultdict
from pathlib import Path
from typing import Any,Iterable
from .benchmark import calibration_report
from .dataset import REQUIRED_CATEGORIES,is_auditable_verified_case,iter_jsonl
from .models import Verdict
from .splits import case_split

def _avg(values):return round(sum(values)/len(values),4) if values else None

def _pairs(groups:Any)->set[tuple[str,str]]:
    out=set()
    if not isinstance(groups,list):return out
    for group in groups:
        if not isinstance(group,(list,tuple,set)):continue
        ids=sorted({str(x) for x in group if str(x)})
        for i,a in enumerate(ids):
            for b in ids[i+1:]:out.add((a,b))
    return out

def _pairwise_scores(pred_groups:Any,gold_groups:Any)->tuple[int,int,int]|None:
    if pred_groups is None or gold_groups is None:return None
    pred=_pairs(pred_groups);gold=_pairs(gold_groups)
    return len(pred&gold),len(pred-gold),len(gold-pred)

def _safe_ratio(a:int,b:int)->float|None:return round(a/b,4) if b else None

def _f1(p:float|None,r:float|None)->float|None:
    if p is None or r is None:return None
    return round(2*p*r/(p+r),4) if p+r else 0.0

def _load_predictions(path:str|Path)->tuple[dict[str,dict[str,Any]],list[dict[str,Any]]]:
    by_id={};errors=[]
    for line_no,row in iter_jsonl(path):
        case_id=str(row.get("case_id") or "")
        if not case_id:errors.append({"line":line_no,"reason":"prediction_missing_case_id"});continue
        if case_id in by_id:errors.append({"line":line_no,"case_id":case_id,"reason":"duplicate_prediction"});continue
        by_id[case_id]=row
    return by_id,errors

def _merge_prediction(case:dict[str,Any],prediction:dict[str,Any])->dict[str,Any]:
    # Ground-truth fields are copied from the immutable dataset. Prediction fields are namespaced logically
    # but flattened for backwards-compatible metric functions.
    row=dict(case)
    allowed=(
        "actual_verdict","confidence","citation_ids","available_evidence_ids","citation_required",
        "predicted_primary_ids","predicted_source_groups","predicted_independent_sources",
        "search_queries","reasoning_calls","latency_seconds","coverage_score","negative_overclaim",
        "quote_exact_predicted","citation_support_labels","input_tokens","output_tokens",
        "fetch_calls","search_provider_calls","fetch_provider_calls","search_cache_hits","fetch_cache_hits",
        "estimated_cost","error_type",
    )
    for key in allowed:
        if key in prediction:row[key]=prediction[key]
    return row

def evaluate_predictions(dataset_path:str|Path,predictions_path:str|Path,*,required_reviewers:int=1,split:str|None="evaluation")->dict[str,Any]:
    predictions,prediction_errors=_load_predictions(predictions_path);rows=[];missing=[]
    for _,case in iter_jsonl(dataset_path):
        if split is not None and case_split(case)!=split:continue
        if case.get("review_status")!="verified" or case.get("synthetic",False):continue
        if not is_auditable_verified_case(case,required_reviewers=required_reviewers):continue
        case_id=str(case.get("id") or "");pred=predictions.get(case_id)
        if pred is None:missing.append(case_id);continue
        rows.append(_merge_prediction(case,pred))
    result=evaluate_records(rows,required_reviewers=required_reviewers,records_are_joined=True)
    result["prediction_errors"]=prediction_errors;result["missing_predictions"]=missing;result["prediction_cases"]=len(predictions);result["evaluated_split"]=split
    return result

def evaluate_records(rows:Iterable[dict[str,Any]],*,required_reviewers:int=1,records_are_joined:bool=False)->dict[str,Any]:
    rows=list(rows);valid_verdicts={v.value for v in Verdict};verified=[];invalid=[]
    for line_no,r in enumerate(rows,1):
        if not records_are_joined:
            if r.get("review_status")!="verified" or r.get("synthetic",False):continue
            if not r.get("ground_truth_sources"):invalid.append({"line":line_no,"reason":"verified_case_missing_ground_truth_sources"});continue
            if not is_auditable_verified_case(r,required_reviewers=required_reviewers):invalid.append({"line":line_no,"reason":"verified_case_not_auditable"});continue
        expected=r.get("expected_verdict");actual=r.get("actual_verdict")
        if expected not in valid_verdicts or actual not in valid_verdicts:invalid.append({"line":line_no,"reason":"invalid_or_missing_verdict"});continue
        verified.append(r)
    if not verified:
        return {
            "total_cases":len(rows),"verified_cases":0,"invalid_verified_cases":invalid,
            "benchmark_sample_sufficient":False,"benchmark_metrics_available":False,
            "production_accuracy_established":False,
            "note":"Production political accuracy is not yet statistically established.",
        }

    exact=acceptable=high_total=high_exact=high_acceptable=false_high_exact=false_high_acceptable=0
    citation_id_ok=0;category_counts=Counter();searches=[];reasoning=[];latencies=[];coverages=[]
    primary_tp=primary_fp=primary_fn=0;pair_tp=pair_fp=pair_fn=0;group_count_errors=[]
    citation_support_true=citation_support_total=0;negative_overclaim=[];quote_tp=quote_fp=0;fetches=[];search_provider=[];fetch_provider=[];search_hits=[];fetch_hits=[];costs=[];input_tokens=[];output_tokens=[]
    for r in verified:
        actual=r["actual_verdict"];expected=r["expected_verdict"];accepted=set(r.get("acceptable_verdicts") or [expected]);is_exact=actual==expected;is_acceptable=actual in accepted
        exact+=is_exact;acceptable+=is_acceptable;conf=min(1,max(0,float(r.get("confidence",0))))
        if conf>=.8:
            high_total+=1;high_exact+=is_exact;high_acceptable+=is_acceptable
            false_high_exact+=int(not is_exact);false_high_acceptable+=int(not is_acceptable)
        cited=set(str(x) for x in r.get("citation_ids",[]));available=set(str(x) for x in r.get("available_evidence_ids",[]));required=bool(r.get("citation_required",bool(cited)))
        citation_id_ok+=int(cited.issubset(available) and (not required or bool(cited)))
        support_labels=r.get("citation_support_labels")
        if isinstance(support_labels,dict):
            for eid in cited:
                if eid in support_labels:
                    citation_support_total+=1;citation_support_true+=int(bool(support_labels[eid]))
        if "predicted_primary_ids" in r and "expected_primary_ids" in r:
            pred=set(str(x) for x in r.get("predicted_primary_ids",[]));gold=set(str(x) for x in r.get("expected_primary_ids",[]))
            primary_tp+=len(pred&gold);primary_fp+=len(pred-gold);primary_fn+=len(gold-pred)
        pair=_pairwise_scores(r.get("predicted_source_groups"),r.get("expected_source_groups"))
        if pair:
            tp,fp,fn=pair;pair_tp+=tp;pair_fp+=fp;pair_fn+=fn
        if r.get("predicted_independent_sources") is not None and r.get("expected_independent_sources") is not None:
            group_count_errors.append(abs(int(r["predicted_independent_sources"])-int(r["expected_independent_sources"])))
        for key,target in (("search_queries",searches),("reasoning_calls",reasoning),("latency_seconds",latencies),("coverage_score",coverages),("fetch_calls",fetches),("search_provider_calls",search_provider),("fetch_provider_calls",fetch_provider),("search_cache_hits",search_hits),("fetch_cache_hits",fetch_hits),("estimated_cost",costs),("input_tokens",input_tokens),("output_tokens",output_tokens)):
            if r.get(key) is not None:target.append(float(r[key]))
        category=str(r.get("category") or "")
        if category:category_counts[category]+=1
        if category=="negative_claim" and r.get("negative_overclaim") is not None:negative_overclaim.append(bool(r["negative_overclaim"]))
        if category=="quote" and r.get("quote_exact_expected") is not None and r.get("quote_exact_predicted") is not None:
            pred=bool(r["quote_exact_predicted"]);gold=bool(r["quote_exact_expected"])
            quote_tp+=int(pred and gold);quote_fp+=int(pred and not gold)

    n=len(verified);category_ready=all(category_counts.get(tag,0)>=5 for tag in REQUIRED_CATEGORIES);sample_ready=n>=100 and category_ready;cal=calibration_report(verified)
    pprec=_safe_ratio(primary_tp,primary_tp+primary_fp);prec=_safe_ratio(primary_tp,primary_tp+primary_fn)
    sprec=_safe_ratio(pair_tp,pair_tp+pair_fp);srec=_safe_ratio(pair_tp,pair_tp+pair_fn)
    quote_precision=_safe_ratio(quote_tp,quote_tp+quote_fp)
    return {
        "total_cases":len(rows),"verified_cases":n,"invalid_verified_cases":invalid,
        "benchmark_sample_sufficient":sample_ready,"benchmark_metrics_available":True,
        "critical_category_counts":{k:category_counts.get(k,0) for k in REQUIRED_CATEGORIES},
        # Deprecated compatibility field: readiness, not sample size, decides production validity.
        "production_accuracy_established":False,
        "verdict_exact_accuracy":round(exact/n,4),"verdict_accuracy":round(exact/n,4),
        "verdict_acceptable_accuracy":round(acceptable/n,4),"acceptable_verdict_accuracy":round(acceptable/n,4),
        "high_confidence_exact_accuracy":round(high_exact/high_total,4) if high_total else None,
        "high_confidence_acceptable_accuracy":round(high_acceptable/high_total,4) if high_total else None,
        "high_confidence_accuracy":round(high_acceptable/high_total,4) if high_total else None,
        "high_confidence_predictions":high_total,
        "false_high_confidence_exact_rate":round(false_high_exact/high_total,4) if high_total else None,
        "false_high_confidence_acceptable_rate":round(false_high_acceptable/high_total,4) if high_total else None,
        "false_high_confidence_rate":round(false_high_acceptable/high_total,4) if high_total else None,
        "citation_id_integrity":round(citation_id_ok/n,4),
        "citation_validity":round(citation_id_ok/n,4),
        "citation_support_precision":_safe_ratio(citation_support_true,citation_support_total),
        "primary_source_tp":primary_tp,"primary_source_fp":primary_fp,"primary_source_fn":primary_fn,
        "primary_source_precision":pprec,"primary_source_recall":prec,"primary_source_f1":_f1(pprec,prec),
        "primary_source_precision_f1":_f1(pprec,prec),
        "source_chain_pairwise_precision":sprec,"source_chain_pairwise_recall":srec,"source_chain_pairwise_f1":_f1(sprec,srec),
        "independent_group_count_mae":_avg(group_count_errors),
        "coverage_rate":_avg(coverages),"average_search_queries":_avg(searches),"average_fetch_calls":_avg(fetches),"average_reasoning_calls":_avg(reasoning),"average_latency":_avg(latencies),
        "average_search_provider_calls":_avg(search_provider),"average_fetch_provider_calls":_avg(fetch_provider),"average_search_cache_hits":_avg(search_hits),"average_fetch_cache_hits":_avg(fetch_hits),
        "average_input_tokens":_avg(input_tokens),"average_output_tokens":_avg(output_tokens),"total_estimated_cost":round(sum(costs),8) if costs else None,
        "negative_claim_overclaim_rate":round(sum(negative_overclaim)/len(negative_overclaim),4) if negative_overclaim else None,
        "quote_exact_precision":quote_precision,
        "brier_score":cal["brier_score"],"expected_calibration_error":cal["expected_calibration_error"],"calibration_bins":cal["bins"],
        "note":None if sample_ready else "Production political accuracy is not yet statistically established.",
    }

def evaluate_jsonl(path:str|Path,*,required_reviewers:int=1)->dict:
    return evaluate_records([r for _,r in iter_jsonl(path)],required_reviewers=required_reviewers)
