from __future__ import annotations
import argparse,json,uuid
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
from .dataset_manifest import build_dataset_manifest,file_sha256
from .evals import evaluate_jsonl,evaluate_predictions

REPORT_SCHEMA_VERSION=2

def build_benchmark_report(dataset_path:str|Path,*,git_sha:str,predictions_path:str|Path|None=None,model_name:str|None=None,search_provider:str|None=None,configuration:dict[str,Any]|None=None,required_reviewers:int=1,split:str|None="evaluation",pricing_version:str|None=None)->dict[str,Any]:
    manifest=build_dataset_manifest(dataset_path,required_reviewers=required_reviewers)
    prediction_artifact=None
    if predictions_path:
        predictions_path=Path(predictions_path);sidecar=Path(str(predictions_path)+".manifest.json")
        if not sidecar.exists():raise ValueError("prediction manifest is required for benchmark reports")
        run_manifest=json.loads(sidecar.read_text(encoding="utf-8"))
        if run_manifest.get("dataset_canonical_sha256")!=manifest.canonical_content_sha256:raise ValueError("prediction dataset hash mismatch")
        if str(run_manifest.get("git_sha"))!=str(git_sha):raise ValueError("prediction Git SHA mismatch")
        if run_manifest.get("split")!=split:raise ValueError("prediction split mismatch")
        metrics=evaluate_predictions(dataset_path,predictions_path,required_reviewers=required_reviewers,split=split)
        prediction_artifact={"path":str(predictions_path),"file_sha256":file_sha256(predictions_path),"manifest_path":str(sidecar),"manifest_file_sha256":file_sha256(sidecar),"run_id":run_manifest.get("run_id")}
    else:
        metrics=evaluate_jsonl(dataset_path,required_reviewers=required_reviewers)
    return {
        "schema_version":REPORT_SCHEMA_VERSION,"run_id":uuid.uuid4().hex,"generated_at":datetime.now(timezone.utc).isoformat(),
        "git_sha":git_sha,"dataset":manifest.to_dict(),"evaluated_split":split,"split_policy_version":manifest.split_policy_version,
        "model_name":model_name,"search_provider":search_provider,"pricing_version":pricing_version,
        "prediction_artifact":prediction_artifact,
        "configuration":configuration or {},"metrics":metrics,
    }

def load_benchmark_report(path:str|Path)->dict[str,Any]:
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data,dict) or data.get("schema_version")!=REPORT_SCHEMA_VERSION:raise ValueError("unsupported benchmark report schema")
    for key in ("git_sha","dataset","metrics"):
        if key not in data:raise ValueError(f"benchmark report missing {key}")
    dataset=data["dataset"]
    if not isinstance(dataset,dict) or not dataset.get("canonical_content_sha256") or not dataset.get("dataset_version"):raise ValueError("benchmark report missing dataset identity")
    if not isinstance(data["metrics"],dict):raise ValueError("benchmark report metrics must be an object")
    for key in ("citation_id_integrity","citation_support_precision","primary_source_precision","false_high_confidence_acceptable_rate","high_confidence_acceptable_accuracy","source_chain_pairwise_f1"):
        value=data["metrics"].get(key)
        if value is not None and not isinstance(value,(int,float)):raise ValueError(f"benchmark metric {key} must be numeric or null")
    return data

def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(prog="political-benchmark-report");parser.add_argument("dataset");parser.add_argument("--git-sha",required=True);parser.add_argument("--predictions");parser.add_argument("--model");parser.add_argument("--search-provider");parser.add_argument("--pricing-version");parser.add_argument("--required-reviewers",type=int,default=1);parser.add_argument("--split",default="evaluation");parser.add_argument("--output");args=parser.parse_args(argv)
    report=build_benchmark_report(args.dataset,git_sha=args.git_sha,predictions_path=args.predictions,model_name=args.model,search_provider=args.search_provider,required_reviewers=args.required_reviewers,split=args.split,pricing_version=args.pricing_version);encoded=json.dumps(report,ensure_ascii=False,indent=2)
    if args.output:Path(args.output).write_text(encoded+"\n",encoding="utf-8")
    print(encoded);return 0
if __name__=="__main__":raise SystemExit(main())
