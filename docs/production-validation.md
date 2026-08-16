# Production validation status

این سند وضعیت واقعی hardening را ثبت می‌کند. معیار اصلی پروژه کاهش `wrong answer with high confidence` است؛ کمبود شواهد باید به verdict محافظه‌کارانه منجر شود و هر defect کشف‌شده regression test داشته باشد.

## پیاده‌سازی‌شده

- review queue فارسی ۱۰۰ پرونده‌ای در ۱۶ دسته با source provenance
- schema/category/source validation و جلوگیری از شمردن synthetic/machine-prepared به‌عنوان accuracy
- workflow بازبینی انسانی مستقل با case fingerprint، stale-review rejection، reviewer metadata و fail-closed batch apply
- production benchmark gating فقط روی reviewهای auditable
- calibration، Brier، ECE و false-high-confidence reporting
- cost summary شامل search/fetch provider calls و cache-hit rates، علاوه بر final cache
- primary-source precision helper که فقط reviewهای auditable را برای production metric می‌پذیرد
- provenance graph با attribution، quote/paragraph/shingle overlap و time؛ weak links برای diagnostics نگه داشته می‌شوند ولی زیر threshold قوی copy-chain را collapse نمی‌کنند
- entity aliases و role-aware timeline
- query cleanup و budget enforcement
- CacheBackend abstraction و SQLite/WAL
- application layer و Telegram transport adapter مستقل از business logic
- quick/deep live-test harness
- failure matrix برای search/reasoning/cache/network behavior

## وضعیت dataset

فایل `evals/cases/persian_political_review_queue.jsonl.gz` machine-prepared/source-backed است. وجود URL یا candidate verdict به معنی ground truth تأییدشده نیست.

برای benchmark production، case باید علاوه بر `review_status=verified` و `independent_human_review=true` دارای `reviewer_id`, `reviewer_note` و `review_case_hash` معتبر باشد. Hash از همان fieldsی محاسبه می‌شود که reviewer دیده است؛ تغییر بعدی claim/source/date/category/candidate verdict/preparer آن review را غیرقابل استفاده می‌کند.

در نبود reviewer انسانی مستقل، `verified_cases` و `auditable_verified_cases` نباید مصنوعی بالا برده شوند.

## معیار production

قبل از ادعای production accuracy همهٔ موارد زیر لازم است:

- حداقل ۱۰۰ case auditable verified
- حداقل ۵ case auditable verified در هر ۱۶ دستهٔ لازم
- ground-truth source غیرخالی و قابل بررسی
- independent human review
- citation integrity
- false-high-confidence rate و calibration report
- primary-source precision report
- source-independence evaluation
- cost/latency report روی workload واقعی

هیچ threshold عددی به‌تنهایی تضمین «حقیقت سیاسی» نیست؛ این‌ها حداقل شروط benchmark governance هستند.

## Live end-to-end

Live suite فقط زمانی اجرا می‌شود که محیط واقعاً دارای این مقادیر باشد:

```text
RUN_LIVE_TESTS=1
SEARXNG_URL
OPENAI_API_KEY
OPENAI_MODEL
```

Quick مسیر search → fetch → source assessment → provenance → Judge → guardrails را بررسی می‌کند. Deep علاوه بر آن Judge → Critic → reconciliation را تست می‌کند. verdict سیاسی در live test hard-code نشده است.

CI عادی بدون credential، live result جعل نمی‌کند و فقط deterministic/security/adversarial suite را اجرا می‌کند.

## اصل گزارش‌دهی

تا وقتی dataset auditable کافی وجود ندارد، خروجی evaluation باید صریحاً بگوید:

`Production political accuracy is not yet statistically established.`
