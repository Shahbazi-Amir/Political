from __future__ import annotations
import argparse,json
from dataclasses import asdict,dataclass,field
from pathlib import Path
from typing import Any
from .benchmark_report import load_benchmark_report
from .dataset import validate_jsonl
from .dataset_manifest import build_dataset_manifest

@dataclass(frozen=True,slots=True)
class QualityGates:
    citation_id_integrity_min:float=.99
    citation_support_precision_min:float=.95
    primary_source_precision_min:float=.95
    false_high_confidence_rate_max:float=.03
    high_confidence_accuracy_min:float=.95
    source_chain_pairwise_f1_min:float=.90
    def evaluate(self,metrics:dict[str,Any]|None,*,sufficient_data:bool,require_semantic_metrics:bool=False)->tuple[str,list[str]]:
        if not sufficient_data:return "insufficient_data",["benchmark_dataset_insufficient"]
        if not metrics:return "missing",["benchmark_metrics_missing"]
        failures=[]
        def value(*keys):
            for key in keys:
                if metrics.get(key) is not None:return metrics.get(key)
            return None
        checks=(
            ("citation_id_integrity",value("citation_id_integrity","citation_validity"),lambda x:x>=self.citation_id_integrity_min),
            ("primary_source_precision",value("primary_source_precision","primary_source_precision_f1"),lambda x:x>=self.primary_source_precision_min),
            ("false_high_confidence_rate",value("false_high_confidence_acceptable_rate","false_high_confidence_rate"),lambda x:x<=self.false_high_confidence_rate_max),
            ("high_confidence_accuracy",value("high_confidence_acceptable_accuracy","high_confidence_accuracy"),lambda x:x>=self.high_confidence_accuracy_min),
        )
        for name,val,predicate in checks:
            if val is None:failures.append(f"{name}_missing")
            elif not predicate(float(val)):failures.append(f"{name}_gate_failed")
        # Semantic citation support and source-chain clustering are required when the audited benchmark exposes them.
        support=value("citation_support_precision")
        if support is None and require_semantic_metrics:failures.append("citation_support_precision_missing")
        elif support is not None and float(support)<self.citation_support_precision_min:failures.append("citation_support_precision_gate_failed")
        source_f1=value("source_chain_pairwise_f1")
        if source_f1 is None and require_semantic_metrics:failures.append("source_chain_pairwise_f1_missing")
        elif source_f1 is not None and float(source_f1)<self.source_chain_pairwise_f1_min:failures.append("source_chain_pairwise_f1_gate_failed")
        return ("pass" if not failures else "fail"),failures

@dataclass(slots=True)
class ReleaseReadiness:
    software_tests_pass:bool
    security_tests_pass:bool
    live_quick_pass:bool|None
    live_deep_pass:bool|None
    auditable_verified_cases:int
    dataset_gate_pass:bool
    benchmark_gate:str
    load_test_pass:bool|None
    production_ready:bool
    blockers:list[str]=field(default_factory=list)
    dataset_version:str|None=None
    dataset_sha256:str|None=None
    git_sha:str|None=None
    evidence_artifacts_consistent:bool|None=None
    def to_dict(self)->dict[str,Any]:return asdict(self)

def assess_release_readiness(dataset_path:str|Path,*,software_tests_pass:bool,security_tests_pass:bool,live_quick_pass:bool|None=None,live_deep_pass:bool|None=None,load_test_pass:bool|None=None,benchmark_metrics:dict[str,Any]|None=None,gates:QualityGates|None=None,require_live:bool=True,require_load_test:bool=True,required_reviewers:int=1)->ReleaseReadiness:
    validation=validate_jsonl(dataset_path,required_reviewers=required_reviewers);manifest=build_dataset_manifest(dataset_path,required_reviewers=required_reviewers);dataset_gate=validation.production_benchmark_ready
    gate_status,gate_failures=(gates or QualityGates()).evaluate(benchmark_metrics,sufficient_data=dataset_gate and bool(benchmark_metrics and benchmark_metrics.get("benchmark_sample_sufficient")),require_semantic_metrics=True)
    blockers=[]
    if not software_tests_pass:blockers.append("software_tests_failed")
    if not security_tests_pass:blockers.append("security_tests_failed")
    if not dataset_gate:blockers.append("dataset_not_production_ready")
    blockers.extend(gate_failures)
    if require_live:
        if live_quick_pass is not True:blockers.append("live_quick_not_passed")
        if live_deep_pass is not True:blockers.append("live_deep_not_passed")
    if require_load_test and load_test_pass is not True:blockers.append("load_test_not_passed")
    return ReleaseReadiness(software_tests_pass,security_tests_pass,live_quick_pass,live_deep_pass,validation.auditable_verified_cases,dataset_gate,gate_status,load_test_pass,not blockers and gate_status=="pass",list(dict.fromkeys(blockers)),manifest.dataset_version,manifest.canonical_content_sha256)

def _read_evidence(path:str|Path,expected_type:str)->dict[str,Any]:
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data,dict) or not data.get("git_sha") or int(data.get("schema_version",0))<1:raise ValueError(f"invalid {expected_type} evidence artifact")
    return data

def assess_from_artifacts(dataset_path:str|Path,*,ci_report:str|Path,benchmark_report:str|Path,live_report:str|Path,load_report:str|Path,gates:QualityGates|None=None,required_reviewers:int=1)->ReleaseReadiness:
    ci=_read_evidence(ci_report,"ci");bench=load_benchmark_report(benchmark_report);live=_read_evidence(live_report,"live");load=_read_evidence(load_report,"load")
    manifest=build_dataset_manifest(dataset_path,required_reviewers=required_reviewers)
    shas={str(ci["git_sha"]),str(bench["git_sha"]),str(live["git_sha"]),str(load["git_sha"])}
    consistent=len(shas)==1 and bench["dataset"].get("canonical_content_sha256")==manifest.canonical_content_sha256
    metrics=bench["metrics"]
    prediction_artifact_present=bool(bench.get("prediction_artifact"))
    result=assess_release_readiness(dataset_path,
        software_tests_pass=ci.get("software_tests_pass") is True,
        security_tests_pass=ci.get("security_tests_pass") is True,
        live_quick_pass=(live.get("quick") or {}).get("status")=="passed",
        live_deep_pass=(live.get("deep") or {}).get("status")=="passed",
        load_test_pass=load.get("status")=="passed",
        benchmark_metrics=metrics,gates=gates,required_reviewers=required_reviewers)
    result.git_sha=next(iter(shas)) if len(shas)==1 else None;result.evidence_artifacts_consistent=consistent
    if not consistent:
        result.production_ready=False;result.blockers=list(dict.fromkeys(result.blockers+["release_evidence_mismatch"]))
    if not prediction_artifact_present:
        result.production_ready=False;result.blockers=list(dict.fromkeys(result.blockers+["benchmark_prediction_artifact_missing"]))
    return result

def _tri(value:str)->bool|None:
    value=value.casefold()
    if value in {"pass","true","yes","1"}:return True
    if value in {"fail","false","no","0"}:return False
    return None

def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(prog="political-readiness");parser.add_argument("--dataset",required=True);parser.add_argument("--benchmark-json");parser.add_argument("--ci-report");parser.add_argument("--live-report");parser.add_argument("--load-report");parser.add_argument("--software-tests",default="unknown");parser.add_argument("--security-tests",default="unknown");parser.add_argument("--live-quick",default="unknown");parser.add_argument("--live-deep",default="unknown");parser.add_argument("--load-test",default="unknown");parser.add_argument("--required-reviewers",type=int,default=1);parser.add_argument("--unsafe-manual-evidence",action="store_true");parser.add_argument("--no-require-live",action="store_true");parser.add_argument("--no-require-load-test",action="store_true");parser.add_argument("--require-ready",action="store_true");args=parser.parse_args(argv)
    artifact_paths=[args.ci_report,args.benchmark_json,args.live_report,args.load_report]
    if all(artifact_paths):
        result=assess_from_artifacts(args.dataset,ci_report=args.ci_report,benchmark_report=args.benchmark_json,live_report=args.live_report,load_report=args.load_report,required_reviewers=args.required_reviewers)
    else:
        if not args.unsafe_manual_evidence:
            print(json.dumps({"production_ready":False,"blockers":["production_readiness_requires_versioned_evidence_artifacts"],"note":"Use --unsafe-manual-evidence only for smoke/development checks."},ensure_ascii=False,indent=2));return 4 if args.require_ready else 0
        metrics=None
        if args.benchmark_json:
            raw=json.loads(Path(args.benchmark_json).read_text(encoding="utf-8"));metrics=raw.get("metrics",raw) if isinstance(raw,dict) else None
        result=assess_release_readiness(args.dataset,software_tests_pass=_tri(args.software_tests) is True,security_tests_pass=_tri(args.security_tests) is True,live_quick_pass=_tri(args.live_quick),live_deep_pass=_tri(args.live_deep),load_test_pass=_tri(args.load_test),benchmark_metrics=metrics,require_live=not args.no_require_live,require_load_test=not args.no_require_load_test,required_reviewers=args.required_reviewers)
    print(json.dumps(result.to_dict(),ensure_ascii=False,indent=2));return 4 if args.require_ready and not result.production_ready else 0
if __name__=="__main__":raise SystemExit(main())
