from __future__ import annotations
from .models import FactCheckResult,Verdict
_LABELS={Verdict.TRUE:"✅ درست",Verdict.MOSTLY_TRUE:"🟢 عمدتاً درست",Verdict.MISSING_CONTEXT:"🟠 ناقص/بدون زمینه",Verdict.MISLEADING:"🟡 گمراه‌کننده",Verdict.MOSTLY_FALSE:"🟠 عمدتاً نادرست",Verdict.FALSE:"❌ نادرست",Verdict.UNVERIFIED:"❓ قابل تأیید نیست",Verdict.INSUFFICIENT_EVIDENCE:"❓ شواهد ناکافی",Verdict.CONFLICTING_EVIDENCE:"⚠️ شواهد متناقض",Verdict.OUTDATED:"🕒 تاریخ‌گذشته",Verdict.OPINION_NOT_FACT:"💬 نظر، نه واقعیت",Verdict.PREDICTION:"🔮 پیش‌بینی",Verdict.VERIFICATION_UNAVAILABLE:"⚠️ بررسی در دسترس نبود"}
def render_persian(result:FactCheckResult)->str:
    lines=[f"نتیجه: {_LABELS.get(result.verdict,result.verdict.value)}",f"اطمینان: {round(result.confidence*100)}٪",f"قدرت شواهد: {result.evidence_strength}","","اصل ماجرا:",result.summary]
    if result.key_points:lines+=["","نکات اصلی:"]+[f"• {x}" for x in result.key_points]
    if result.contradicting_evidence_ids:lines+=["",f"شواهد مخالف: {', '.join(result.contradicting_evidence_ids)}"]
    if result.missing_evidence:lines+=["","چه چیزی هنوز کم است؟"]+[f"• {x}" for x in result.missing_evidence[:8]]
    if result.uncertainty:lines+=["","عدم قطعیت:",result.uncertainty]
    if result.coverage:
        low=[c for c in result.coverage if c.coverage_score<.75]
        if low:lines+=["","پوشش تحقیق:"]+[f"• {c.claim_id}: {round(c.coverage_score*100)}٪" for c in low]
    cited={e.evidence_id:e for e in result.evidence if e.evidence_id in result.citation_ids}
    if cited:
        lines+=["","منابع:"]
        for eid,e in cited.items():lines.append(f"{eid} — {e.title} — {e.url}")
    return "\n".join(lines)
