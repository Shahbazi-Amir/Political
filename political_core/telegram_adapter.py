from __future__ import annotations
import time
from collections import OrderedDict
from dataclasses import dataclass,field
from .application import PoliticalApplication
from .models import FactCheckResult
from .rate_limit import ConcurrencyLimiter,SlidingWindowRateLimiter

@dataclass(slots=True,frozen=True)
class TelegramCommand:name:str;argument:str=""

def parse_command(text:str)->TelegramCommand:
    raw=(text or "").strip()
    if not raw.startswith("/"):return TelegramCommand("check",raw)
    head,*rest=raw.split(maxsplit=1);name=head[1:].split("@",1)[0].casefold();return TelegramCommand(name,rest[0].strip() if rest else "")

class _LastResultStore:
    def __init__(self,max_users:int=5000,ttl_seconds:float=3600)->None:self.max_users=max(1,int(max_users));self.ttl_seconds=max(1.0,float(ttl_seconds));self.rows:OrderedDict[str,tuple[float,FactCheckResult]]=OrderedDict()
    def set(self,user_id:str,result:FactCheckResult)->None:
        key=str(user_id);self.rows[key]=(time.monotonic(),result);self.rows.move_to_end(key)
        while len(self.rows)>self.max_users:self.rows.popitem(last=False)
    def get(self,user_id:str)->FactCheckResult|None:
        key=str(user_id);row=self.rows.get(key)
        if row is None:return None
        created,result=row
        if time.monotonic()-created>self.ttl_seconds:self.rows.pop(key,None);return None
        self.rows.move_to_end(key);return result
    def __len__(self)->int:return len(self.rows)

@dataclass(slots=True)
class TelegramAdapter:
    application:PoliticalApplication
    rate_limiter:SlidingWindowRateLimiter|None=None
    concurrency_limiter:ConcurrencyLimiter|None=None
    last_result_max_users:int=5000
    last_result_ttl_seconds:float=3600
    _last_result:_LastResultStore=field(init=False)
    def __post_init__(self)->None:self._last_result=_LastResultStore(self.last_result_max_users,self.last_result_ttl_seconds)
    def _remember(self,user_id:str,result:FactCheckResult)->None:self._last_result.set(user_id,result)
    def _last(self,user_id:str)->FactCheckResult|None:return self._last_result.get(user_id)
    def _run_check(self,user_id:str,cmd:TelegramCommand)->str:
        if self.rate_limiter is not None and not self.rate_limiter.allow(str(user_id)):return "تعداد درخواست‌های شما زیاد است؛ کمی بعد دوباره تلاش کن."
        try:
            if self.concurrency_limiter is None:response=self.application.check(cmd.argument,deep=cmd.name=="deep")
            else:
                with self.concurrency_limiter.slot(timeout=0.0) as acquired:
                    if not acquired:return "سامانه در حال حاضر مشغول است؛ کمی بعد دوباره تلاش کن."
                    response=self.application.check(cmd.argument,deep=cmd.name=="deep")
        except Exception:
            return "در حال حاضر امکان بررسی کامل منابع وجود ندارد؛ نتیجه قطعی ارائه نمی‌کنم."
        self._remember(user_id,response.result);return response.text+"\n\nشناسه نتیجه: "+response.result_id
    def handle(self,user_id:str,text:str)->str:
        cmd=parse_command(text)
        if cmd.name in {"start","help"}:return "دستورها: /check ادعا | /deep ادعا | /source | /why | /feedback TYPE [comment]\nTYPE: correct, wrong, partially_wrong, bad_source, missed_source, bad_verdict, bad_reasoning, outdated"
        if cmd.name in {"check","deep"}:
            if not cmd.argument:return "بعد از دستور، متن ادعا را بفرست."
            return self._run_check(user_id,cmd)
        if cmd.name=="source":
            result=self._last(user_id);return self.application.sources(result) if result else "ابتدا یک ادعا را بررسی کن."
        if cmd.name=="why":
            result=self._last(user_id);return self.application.why(result) if result else "ابتدا یک ادعا را بررسی کن."
        if cmd.name=="feedback":
            result=self._last(user_id)
            if result is None:return "ابتدا یک ادعا را بررسی کن."
            if not cmd.argument:return "نوع بازخورد را بعد از /feedback وارد کن."
            kind,*rest=cmd.argument.split(maxsplit=1)
            try:rid=self.application.submit_feedback(result,kind,rest[0] if rest else "")
            except ValueError as exc:return f"بازخورد نامعتبر: {exc}"
            except RuntimeError:return "ذخیره بازخورد در این اجرا فعال نیست."
            return f"بازخورد ثبت شد. شناسه نتیجه: {rid}"
        return "دستور ناشناخته است. /help را بفرست."
