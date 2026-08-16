from __future__ import annotations

import argparse,hashlib,json,os,time,uuid
from datetime import datetime,timezone
from pathlib import Path
from typing import Any

from .application import PoliticalApplication
from .dataset import is_auditable_verified_case,iter_jsonl
from .dataset_manifest import build_dataset_manifest
from .pricing import PricingPolicy
from .splits import SPLIT_POLICY_VERSION,case_split


def _canonical_hash(value:dict[str,Any])->str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()


def _prediction_from_result(case_id:str,result,elapsed:float,pricing:PricingPolicy|None=None,*,run_id:str|None=None)->dict[str,Any]:
    evidence_ids=[e.evidence_id for e in result.evidence]
    primary_ids=[e.evidence_id for e in result.evidence if e.primary_assessment.is_primary]
    groups={}
    for e in result.evidence:
        key=e.source_chain_id or e.independence_key or e.evidence_id
        groups.setdefault(key,[]).append(e.evidence_id)
    return {
        "case_id":case_id,"run_id":run_id,
        "actual_verdict":result.verdict.value,"confidence":float(result.confidence),
        "citation_ids":list(result.citation_ids),"available_evidence_ids":evidence_ids,"citation_required":bool(result.citation_ids),
        "predicted_primary_ids":primary_ids,"predicted_source_groups":list(groups.values()),
        "predicted_independent_sources":int((result.diagnostics or {}).get("independent_source_groups",0) or 0),
        "final_cache_hit":bool(result.from_cache),
        "search_queries":0 if result.from_cache else int((result.cost_stats or {}).get("search_queries",0) or 0),
        "fetch_calls":0 if result.from_cache else int((result.cost_stats or {}).get("pages_fetched",0) or 0),
        "reasoning_calls":0 if result.from_cache else int((result.cost_stats or {}).get("reasoning_calls",0) or 0),
        "input_tokens":0 if result.from_cache else (result.cost_stats or {}).get("input_tokens"),
        "output_tokens":0 if result.from_cache else (result.cost_stats or {}).get("output_tokens"),
        "estimated_cost":0.0 if result.from_cache else ((result.cost_stats or {}).get("estimated_cost") if (result.cost_stats or {}).get("estimated_cost") is not None else (pricing.estimate((result.cost_stats or {}).get("input_tokens"),(result.cost_stats or {}).get("output_tokens")) if pricing else None)),
        "latency_seconds":round(elapsed,6),
        "coverage_score":round(sum(c.coverage_score for c in result.coverage)/len(result.coverage),4) if result.coverage else 0.0,
        "search_provider_calls":0 if result.from_cache else int(((result.diagnostics or {}).get("search_provider_stats") or {}).get("provider_calls",0) or 0),
        "search_cache_hits":0 if result.from_cache else int(((result.diagnostics or {}).get("search_provider_stats") or {}).get("cache_hits",0) or 0),
        "fetch_provider_calls":0 if result.from_cache else int((((result.analysis or {}).get("fetch_provider_stats") or {}).get("provider_calls",0)) or 0),
        "fetch_cache_hits":0 if result.from_cache else int((((result.analysis or {}).get("fetch_provider_stats") or {}).get("cache_hits",0)) or 0),
        "error_type":None,
    }


def _manifest_path(output_path:Path)->Path:
    return Path(str(output_path)+".manifest.json")


def _load_completed_predictions(path:Path)->dict[str,dict[str,Any]]:
    rows={}
    if not path.exists():return rows
    for _,row in iter_jsonl(path):
        case_id=str(row.get("case_id") or "")
        if case_id and row.get("actual_verdict") and not row.get("error_type"):rows[case_id]=row
    return rows


def run_benchmark(dataset_path:str|Path,application:PoliticalApplication,output_path:str|Path,*,mode:str="quick",required_reviewers:int=1,split:str|None="evaluation",resume:bool=True,pricing:PricingPolicy|None=None,git_sha:str|None=None,model_name:str|None=None,search_provider:str|None=None,configuration:dict[str,Any]|None=None)->dict[str,Any]:
    dataset_path=Path(dataset_path);output_path=Path(output_path);manifest=build_dataset_manifest(dataset_path,required_reviewers=required_reviewers)
    run_id=uuid.uuid4().hex;started=datetime.now(timezone.utc);git_sha=git_sha or os.getenv("GITHUB_SHA") or "unknown"
    config=configuration or {};config_fingerprint=_canonical_hash(config)
    run_identity={"dataset_canonical_sha256":manifest.canonical_content_sha256,"dataset_version":manifest.dataset_version,"mode":mode,"split":split,"split_policy_version":SPLIT_POLICY_VERSION,"required_reviewers":required_reviewers,"git_sha":git_sha,"model_name":model_name,"search_provider":search_provider,"configuration_fingerprint":config_fingerprint,"pricing_version":pricing.version if pricing else None}
    sidecar=_manifest_path(output_path)
    predictions={}
    if resume and output_path.exists():
        if not sidecar.exists():raise ValueError("unsafe_resume_without_prediction_manifest")
        prior=json.loads(sidecar.read_text(encoding="utf-8"))
        for key,value in run_identity.items():
            if prior.get(key)!=value:raise ValueError(f"resume_identity_mismatch:{key}")
        predictions=_load_completed_predictions(output_path)
    eligible=0;errors=0
    for _,case in iter_jsonl(dataset_path):
        if case.get("review_status")!="verified" or not is_auditable_verified_case(case,required_reviewers=required_reviewers):continue
        if split is not None and case_split(case)!=split:continue
        eligible+=1;case_id=str(case["id"])
        if case_id in predictions:continue
        t0=time.perf_counter()
        try:
            reference=None;raw=case.get("reference_date")
            if raw:
                normalized=str(raw).replace("Z","+00:00");reference=datetime.fromisoformat(normalized)
                if reference.tzinfo is None:reference=reference.replace(tzinfo=timezone.utc)
            response=application.check(str(case["claim"]),deep=mode=="deep",reference_date=reference)
            predictions[case_id]=_prediction_from_result(case_id,response.result,time.perf_counter()-t0,pricing,run_id=run_id)
        except Exception as exc:
            errors+=1;predictions[case_id]={"case_id":case_id,"run_id":run_id,"error_type":type(exc).__name__,"error_message":str(exc)[:300],"latency_seconds":round(time.perf_counter()-t0,6)}
    rows=[predictions[k] for k in sorted(predictions)]
    with output_path.open("w",encoding="utf-8") as handle:
        for row in rows:handle.write(json.dumps(row,ensure_ascii=False,separators=(",",":"))+"\n")
    run_manifest={"schema_version":2,"run_id":run_id,"started_at":started.isoformat(),"completed_at":datetime.now(timezone.utc).isoformat(),**run_identity,"eligible_cases":eligible,"successful_prediction_cases":sum(1 for r in rows if r.get("actual_verdict") and not r.get("error_type")),"error_cases":sum(1 for r in rows if r.get("error_type")),"prediction_path":str(output_path)}
    sidecar.write_text(json.dumps(run_manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return {**run_manifest,"prediction_cases":len(rows),"output":str(output_path),"manifest":str(sidecar)}


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(prog="political-benchmark-run");parser.add_argument("dataset");parser.add_argument("output");parser.add_argument("--mode",choices=["quick","deep"],default="quick");parser.add_argument("--required-reviewers",type=int,default=1);parser.add_argument("--split",default="evaluation");parser.add_argument("--no-resume",action="store_true");parser.add_argument("--git-sha");parser.add_argument("--model");parser.add_argument("--search-provider");parser.add_argument("--pricing-version");parser.add_argument("--input-cost-per-million",type=float);parser.add_argument("--output-cost-per-million",type=float);args=parser.parse_args(argv)
    from .cli import _engine
    app=PoliticalApplication(_engine())
    pricing=PricingPolicy(args.pricing_version,args.input_cost_per_million,args.output_cost_per_million) if args.pricing_version and args.input_cost_per_million is not None and args.output_cost_per_million is not None else None
    report=run_benchmark(args.dataset,app,args.output,mode=args.mode,required_reviewers=args.required_reviewers,split=args.split,resume=not args.no_resume,pricing=pricing,git_sha=args.git_sha,model_name=args.model,search_provider=args.search_provider)
    print(json.dumps(report,ensure_ascii=False,indent=2));return 0

if __name__=="__main__":raise SystemExit(main())
