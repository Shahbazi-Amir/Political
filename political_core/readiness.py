from __future__ import annotations
import argparse,json
from dataclasses import asdict,dataclass,field
from pathlib import Path
from typing import Any
from .dataset import validate_jsonl
from .dataset_manifest import build_dataset_manifest

@dataclass(frozen=True,slots=True)
class QualityGates:
    citation_validity_min:float=.99
    primary_source_precision_f1_min:float=.95
    false_high_confidence_rate_max:float=.03
    high_confidence_accuracy_min:float=.95
    def evaluate(self,metrics:dict[str,Any]|None,*,sufficient_data:bool)->tuple[str,list[str]]:
        if not sufficient_data:return "insufficient_data",["benchmark_dataset_insufficient"]
        if not metrics:return "missing",["benchmark_metrics_missing"]
        failures=[];checks=(("citation_validity",metrics.get("citation_validity"),lambda x:x>=self.citation_validity_min),("primary_source_precision_f1",metrics.get("primary_source_precision_f1"),lambda x:x>=self.primary_source_precision_f1_min),("false_high_confidence_rate",metrics.get("false_high_confidence_rate"),lambda x:x<=self.false_high_confidence_rate_max),("high_confidence_accuracy",metrics.get("high_confidence_accuracy"),lambda x:x>=self.high_confidence_accuracy_min))
        for name,value,predicate in checks:
            if value is None:failures.append(f"{name}_missing")
            elif not predicate(float(value)):failures.append(f"{name}_gate_failed")
        return ("pass" if not failures else "fail"),failures

@dataclass(slots=True)
class ReleaseReadiness:
    software_tests_pass:bool;security_tests_pass:bool;live_quick_pass:bool|None;live_deep_pass:bool|None;auditable_verified_cases:int;dataset_gate_pass:bool;benchmark_gate:str;load_test_pass:bool|None;production_ready:bool;blockers:list[str]=field(default_factory=list);dataset_version:str|None=None;dataset_sha256:str|None=None
    def to_dict(self)->dict[str,Any]:return asdict(self)

def assess_release_readiness(dataset_path:str|Path,*,software_tests_pass:bool,security_tests_pass:bool,live_quick_pass:bool|None=None,live_deep_pass:bool|None=None,load_test_pass:bool|None=None,benchmark_metrics:dict[str,Any]|None=None,gates:QualityGates|None=None,require_live:bool=True,require_load_test:bool=True)->ReleaseReadiness:
    validation=validate_jsonl(dataset_path);manifest=build_dataset_manifest(dataset_path);dataset_gate=validation.production_benchmark_ready;gate_status,gate_failures=(gates or QualityGates()).evaluate(benchmark_metrics,sufficient_data=dataset_gate);blockers=[]
    if not software_tests_pass:blockers.append("software_tests_failed")
    if not security_tests_pass:blockers.append("security_tests_failed")
    if not dataset_gate:blockers.append("dataset_not_production_ready")
    blockers.extend(gate_failures)
    if require_live:
        if live_quick_pass is not True:blockers.append("live_quick_not_passed")
        if live_deep_pass is not True:blockers.append("live_deep_not_passed")
    if require_load_test and load_test_pass is not True:blockers.append("load_test_not_passed")
    return ReleaseReadiness(software_tests_pass,security_tests_pass,live_quick_pass,live_deep_pass,validation.auditable_verified_cases,dataset_gate,gate_status,load_test_pass,not blockers and gate_status=="pass",list(dict.fromkeys(blockers)),manifest.dataset_version,manifest.sha256)

def _tri(value:str)->bool|None:
    value=value.casefold()
    if value in {"pass","true","yes","1"}:return True
    if value in {"fail","false","no","0"}:return False
    return None
def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(prog="political-readiness");parser.add_argument("--dataset",required=True);parser.add_argument("--benchmark-json");parser.add_argument("--software-tests",default="pass");parser.add_argument("--security-tests",default="pass");parser.add_argument("--live-quick",default="unknown");parser.add_argument("--live-deep",default="unknown");parser.add_argument("--load-test",default="unknown");parser.add_argument("--no-require-live",action="store_true");parser.add_argument("--no-require-load-test",action="store_true");parser.add_argument("--require-ready",action="store_true");args=parser.parse_args(argv);metrics=json.loads(Path(args.benchmark_json).read_text(encoding="utf-8")) if args.benchmark_json else None;result=assess_release_readiness(args.dataset,software_tests_pass=_tri(args.software_tests) is True,security_tests_pass=_tri(args.security_tests) is True,live_quick_pass=_tri(args.live_quick),live_deep_pass=_tri(args.live_deep),load_test_pass=_tri(args.load_test),benchmark_metrics=metrics,require_live=not args.no_require_live,require_load_test=not args.no_require_load_test);print(json.dumps(result.to_dict(),ensure_ascii=False,indent=2));return 4 if args.require_ready and not result.production_ready else 0
if __name__=="__main__":raise SystemExit(main())
