from __future__ import annotations

from dataclasses import dataclass, field

from .application import PoliticalApplication
from .models import FactCheckResult


@dataclass(slots=True, frozen=True)
class TelegramCommand:
    name:str
    argument:str=""


def parse_command(text:str)->TelegramCommand:
    raw=(text or "").strip()
    if not raw.startswith("/"):
        return TelegramCommand("check",raw)
    head,*rest=raw.split(maxsplit=1)
    name=head[1:].split("@",1)[0].casefold()
    return TelegramCommand(name,rest[0].strip() if rest else "")


@dataclass(slots=True)
class TelegramAdapter:
    """Dependency-free command adapter; wire it to aiogram/python-telegram-bot externally."""
    application:PoliticalApplication
    _last_result:dict[str,FactCheckResult]=field(default_factory=dict)

    def _remember(self,user_id:str,result:FactCheckResult)->None:
        self._last_result[str(user_id)]=result

    def _last(self,user_id:str)->FactCheckResult|None:
        return self._last_result.get(str(user_id))

    def handle(self,user_id:str,text:str)->str:
        cmd=parse_command(text)
        if cmd.name in {"start","help"}:
            return (
                "دستورها: /check ادعا | /deep ادعا | /source | /why | "
                "/feedback TYPE [comment]\n"
                "TYPE: correct, wrong, partially_wrong, bad_source, missed_source, "
                "bad_verdict, bad_reasoning, outdated"
            )
        if cmd.name in {"check","deep"}:
            if not cmd.argument:
                return "بعد از دستور، متن ادعا را بفرست."
            response=self.application.check(cmd.argument,deep=cmd.name=="deep")
            self._remember(user_id,response.result)
            return response.text+"\n\nشناسه نتیجه: "+response.result_id
        if cmd.name=="source":
            result=self._last(user_id)
            return self.application.sources(result) if result else "ابتدا یک ادعا را بررسی کن."
        if cmd.name=="why":
            result=self._last(user_id)
            return self.application.why(result) if result else "ابتدا یک ادعا را بررسی کن."
        if cmd.name=="feedback":
            result=self._last(user_id)
            if result is None:return "ابتدا یک ادعا را بررسی کن."
            if not cmd.argument:return "نوع بازخورد را بعد از /feedback وارد کن."
            kind,*rest=cmd.argument.split(maxsplit=1)
            try:
                rid=self.application.submit_feedback(result,kind,rest[0] if rest else "")
            except ValueError as exc:
                return f"بازخورد نامعتبر: {exc}"
            except RuntimeError:
                return "ذخیره بازخورد در این اجرا فعال نیست."
            return f"بازخورد ثبت شد. شناسه نتیجه: {rid}"
        return "دستور ناشناخته است. /help را بفرست."
