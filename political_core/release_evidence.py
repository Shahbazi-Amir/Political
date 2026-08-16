from __future__ import annotations
from datetime import datetime,timezone
from typing import Any

def ci_report(git_sha:str,*,software_tests_pass:bool,security_tests_pass:bool)->dict[str,Any]:
    return {"schema_version":1,"artifact_type":"ci","git_sha":git_sha,"generated_at":datetime.now(timezone.utc).isoformat(),"software_tests_pass":bool(software_tests_pass),"security_tests_pass":bool(security_tests_pass)}

def live_report(git_sha:str,*,configuration_available:bool,quick_status:str,deep_status:str)->dict[str,Any]:
    valid={"passed","failed","skipped"}
    if quick_status not in valid or deep_status not in valid:raise ValueError("invalid live status")
    return {"schema_version":1,"artifact_type":"live","git_sha":git_sha,"generated_at":datetime.now(timezone.utc).isoformat(),"configuration_available":bool(configuration_available),"quick":{"status":quick_status},"deep":{"status":deep_status}}

def load_report(git_sha:str,*,status:str,metrics:dict[str,Any]|None=None)->dict[str,Any]:
    if status not in {"passed","failed","skipped"}:raise ValueError("invalid load status")
    return {"schema_version":1,"artifact_type":"load","git_sha":git_sha,"generated_at":datetime.now(timezone.utc).isoformat(),"status":status,"metrics":metrics or {}}
