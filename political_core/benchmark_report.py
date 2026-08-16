from __future__ import annotations
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
from .dataset_manifest import build_dataset_manifest
from .evals import evaluate_jsonl

def build_benchmark_report(dataset_path:str|Path,*,git_sha:str,model_name:str|None=None,search_provider:str|None=None,configuration:dict[str,Any]|None=None)->dict[str,Any]:
    manifest=build_dataset_manifest(dataset_path);metrics=evaluate_jsonl(dataset_path)
    return {"report_schema_version":1,"generated_at":datetime.now(timezone.utc).isoformat(),"git_sha":git_sha,"dataset":manifest.to_dict(),"model_name":model_name,"search_provider":search_provider,"configuration":configuration or {},"metrics":metrics}
def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(prog="political-benchmark-report");parser.add_argument("dataset");parser.add_argument("--git-sha",required=True);parser.add_argument("--model");parser.add_argument("--search-provider");parser.add_argument("--output");args=parser.parse_args(argv)
    report=build_benchmark_report(args.dataset,git_sha=args.git_sha,model_name=args.model,search_provider=args.search_provider);encoded=json.dumps(report,ensure_ascii=False,indent=2)
    if args.output:Path(args.output).write_text(encoded+"\n",encoding="utf-8")
    print(encoded);return 0
if __name__=="__main__":raise SystemExit(main())
