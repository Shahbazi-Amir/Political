# Evals

`cases/` برای پرونده‌های سیاسی واقعی و human-reviewed است. `fixtures/` برای smoke/synthetic plumbing است و **نباید** به‌عنوان accuracy سیاسی گزارش شود.
Runner: `political-check --eval-jsonl path/to/cases.jsonl`.
اگر پرونده verified کافی نباشد، خروجی عمداً اعلام می‌کند که production accuracy از نظر آماری اثبات نشده است.
