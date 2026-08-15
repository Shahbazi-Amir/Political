from __future__ import annotations

from .models import FactCheckResult

_LABELS = {
    "true": "✅ درست", "mostly_true": "🟢 عمدتاً درست", "missing_context": "🟠 ناقص/بدون زمینه",
    "misleading": "🟡 گمراه‌کننده", "mostly_false": "🟠 عمدتاً نادرست", "false": "❌ نادرست",
    "unverified": "❓ تأییدنشده", "insufficient_evidence": "❓ شواهد ناکافی", "conflicting_evidence": "⚠️ شواهد متناقض",
    "outdated": "🕒 تاریخ‌گذشته", "opinion_not_fact": "💬 نظر، نه واقعیت قابل‌سنجش", "prediction": "🔮 پیش‌بینی",
}


def render_persian(result: FactCheckResult) -> str:
    lines = [f"نتیجه: {_LABELS.get(result.verdict.value, result.verdict.value)}", f"اطمینان: {round(result.confidence * 100)}٪", f"قدرت شواهد: {result.evidence_strength}", "", "اصل ماجرا:", result.summary]
    if result.key_points:
        lines.extend(["", "نکات کلیدی:"] + [f"- {x}" for x in result.key_points])
    if result.contradicting_evidence_ids:
        lines.extend(["", "شواهد مخالف:", ", ".join(result.contradicting_evidence_ids)])
    if result.missing_evidence:
        lines.extend(["", "چه چیزی هنوز کم است:"] + [f"- {x}" for x in result.missing_evidence[:6]])
    if result.uncertainty:
        lines.extend(["", "عدم قطعیت:", result.uncertainty])
    cited = [e for e in result.evidence if e.evidence_id in result.citation_ids]
    if cited:
        lines.extend(["", "منابع اصلی:"])
        for e in cited:
            lines.append(f"- {e.evidence_id}: {e.title} — {e.url}")
    if result.diagnostics.get("deep_check_recommended"):
        lines.extend(["", "بررسی عمیق‌تر برای این ادعا توصیه می‌شود."])
    return "\n".join(lines)
