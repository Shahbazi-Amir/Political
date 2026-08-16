# Evaluation policy

Accuracy سیاسی فقط از caseهایی محاسبه می‌شود که همهٔ شرایط زیر را داشته باشند:

- `review_status: verified` به‌صورت صریح وجود داشته باشد؛ missing status هرگز verified فرض نمی‌شود.
- `synthetic` نباشد.
- `expected_verdict` و `actual_verdict` معتبر باشند.
- `ground_truth_sources` غیرخالی باشد.

Case مصنوعی فقط برای smoke/regression است و وارد production accuracy نمی‌شود.

## Readiness

`benchmark_sample_sufficient` حداقل ۱۰۰ case verified و حداقل ۵ case در هر دستهٔ بحرانی زیر می‌خواهد:

`appointment`, `current_status`, `negative`, `quote`, `legal`, `breaking_news`, `copied_sources`, `conflicting_sources`.

حتی sample کافی به‌تنهایی `production_accuracy_established` نمی‌سازد. تمام caseهای verified باید `independent_human_review: true` نیز داشته باشند.

Metricهای اصلی:
- verdict / acceptable-verdict accuracy
- high-confidence accuracy
- false-high-confidence rate
- citation validity
- primary-source F1
- source-independence accuracy
- coverage
- latency/search/reasoning cost
- calibration bins

هدف اصلی کاهش **False High-Confidence Rate** است.
