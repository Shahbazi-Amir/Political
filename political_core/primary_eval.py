from __future__ import annotations
from collections.abc import Iterable,Mapping
from typing import Any
from .dataset import is_auditable_verified_case

def primary_source_metrics(records:Iterable[Mapping[str,Any]],*,required_reviewers:int=1)->dict[str,Any]:
    tp=fp=fn=tn=0;reviewed=0;structural_verified=0;rejected_audit=0
    for row in records:
        if row.get("review_status")=="verified" and row.get("independent_human_review") is True:structural_verified+=1
        if not is_auditable_verified_case(dict(row),required_reviewers=required_reviewers):
            if row.get("review_status")=="verified":rejected_audit+=1
            continue
        if "expected_primary" not in row or "actual_primary" not in row:continue
        reviewed+=1;expected=bool(row["expected_primary"]);actual=bool(row["actual_primary"])
        if expected and actual:tp+=1
        elif not expected and actual:fp+=1
        elif expected and not actual:fn+=1
        else:tn+=1
    precision=tp/(tp+fp) if tp+fp else None;recall=tp/(tp+fn) if tp+fn else None;f1=(2*precision*recall/(precision+recall)) if precision is not None and recall is not None and precision+recall else None
    return {"reviewed_cases":reviewed,"structural_verified_cases":structural_verified,"rejected_non_auditable_verified":rejected_audit,"tp":tp,"fp":fp,"fn":fn,"tn":tn,"precision":round(precision,4) if precision is not None else None,"recall":round(recall,4) if recall is not None else None,"f1":round(f1,4) if f1 is not None else None,"sample_sufficient":reviewed>=50,"production_precision_established":False}
