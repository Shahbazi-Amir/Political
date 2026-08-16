from __future__ import annotations
import time,uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from .engine import FactCheckEngine
from .models import FactCheckResult
from .observability import MetricsSink,metric_from_result
from .output import render_persian
from .text import fingerprint
class FeedbackSink(Protocol):
    def add(self,result_id:str,claim:str,feedback_type:str,comment:str="")->None:...
@dataclass(slots=True)
class ApplicationResponse:
    result:FactCheckResult;text:str;result_id:str;request_id:str=""
class PoliticalApplication:
    def __init__(self,engine:FactCheckEngine,feedback:FeedbackSink|None=None,metrics:MetricsSink|None=None)->None:self.engine=engine;self.feedback=feedback;self.metrics=metrics
    @staticmethod
    def result_id(result:FactCheckResult)->str:return fingerprint(f"{result.normalized_claim}|{result.verdict.value}|{result.confidence:.3f}")[:20]
    def check(self,claim:str,*,deep:bool=False,refresh:bool=False,reference_date:datetime|None=None,request_id:str|None=None)->ApplicationResponse:
        mode="deep" if deep else "quick";request_id=request_id or uuid.uuid4().hex;started=time.perf_counter()
        if reference_date is None:result=self.engine.check(claim,mode=mode,refresh=refresh)
        else:result=self.engine.check(claim,mode=mode,refresh=refresh,reference_date=reference_date)
        latency=time.perf_counter()-started
        if self.metrics is not None:self.metrics.emit(metric_from_result(result,request_id,mode=mode,latency_seconds=latency))
        return ApplicationResponse(result,render_persian(result),self.result_id(result),request_id)
    @staticmethod
    def sources(result:FactCheckResult)->str:
        cited={e.evidence_id:e for e in result.evidence if e.evidence_id in result.citation_ids}
        if not cited:return "منبع استنادی معتبری برای این نتیجه ثبت نشده است."
        lines=["منابع استنادی:"]
        for eid,e in cited.items():role=e.source_role.value;primary="primary" if e.primary_assessment.is_primary else "non-primary";lines.append(f"• {eid} — {e.title} — {e.url} — {role}/{primary}")
        return "\n".join(lines)
    @staticmethod
    def why(result:FactCheckResult)->str:
        lines=[f"نتیجه: {result.verdict.value}",f"اطمینان: {round(result.confidence*100)}٪",f"قدرت شواهد: {result.evidence_strength}"]
        if result.key_points:lines.append("دلایل اصلی:");lines.extend(f"• {x}" for x in result.key_points[:6])
        if result.missing_evidence:lines.append("کمبود شواهد:");lines.extend(f"• {x}" for x in result.missing_evidence[:6])
        if result.uncertainty:lines.append("عدم قطعیت: "+result.uncertainty)
        diag=result.diagnostics
        if diag:lines.append("تشخیص: "+f"independent={diag.get('independent_source_groups','?')}، "+f"conflict={diag.get('conflict_detected',False)}، "+f"critic={diag.get('critic_used',False)}")
        return "\n".join(lines)
    def submit_feedback(self,result:FactCheckResult,feedback_type:str,comment:str="")->str:
        if self.feedback is None:raise RuntimeError("feedback store is not configured")
        rid=self.result_id(result);self.feedback.add(rid,result.claim,feedback_type,comment);return rid
