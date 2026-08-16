# Production validation status

این سند وضعیت واقعی hardening را ثبت می‌کند. معیار اصلی پروژه کاهش `wrong answer with high confidence` است؛ کمبود شواهد باید به verdict محافظه‌کارانه منجر شود و هر defect کشف‌شده regression test داشته باشد.

## پیاده‌سازی‌شده

- review queue فارسی ۱۰۰ پرونده‌ای در ۱۶ دسته با source provenance
- schema/category/source validation و جلوگیری از شمردن synthetic/machine-prepared به‌عنوان accuracy
- workflow بازبینی انسانی مستقل با case fingerprint، stale-review rejection، reviewer metadata و fail-closed batch apply
- reviewer identity abstraction و registry کنترل‌شده برای deploymentها
- policy اختیاری دو-reviewer، تشخیص review conflict و adjudication با adjudicator مستقل
- production benchmark gating فقط روی reviewهای auditable
- dataset manifest شامل SHA-256، schema version و dataset version پایدار
- benchmark report شامل Git SHA، dataset hash/version، model/provider metadata و metrics
- calibration، Brier، ECE و false-high-confidence reporting
- machine-readable release readiness با حالت `insufficient_data` و blockerهای صریح
- cost summary شامل search/fetch provider calls و cache-hit rates، علاوه بر final cache
- primary-source precision helper که فقط reviewهای auditable را برای production metric می‌پذیرد
- provenance graph با attribution، quote/paragraph/shingle overlap و time؛ weak links برای diagnostics نگه داشته می‌شوند ولی زیر threshold قوی copy-chain را collapse نمی‌کنند
- entity aliases و role-aware timeline
- query cleanup و budget enforcement
- `CacheBackend` abstraction با SQLite/WAL و Redis اختیاری بدون dependency اجباری
- application layer و Telegram transport adapter مستقل از business logic
- per-user rate limiting و global concurrency limiting در transport layer
- structured observability بدون ذخیره raw claim یا secret در metric schema
- load-test harness با success/error rate و P50/P95/P99
- Quick/Deep live-test harness و workflow دستی مجزا برای live validation
- failure matrix برای search/reasoning/cache/network behavior

## وضعیت dataset

فایل `evals/cases/persian_political_review_queue.jsonl.gz` machine-prepared/source-backed است. وجود URL یا candidate verdict به معنی ground truth تأییدشده نیست.

برای benchmark production، case باید علاوه بر `review_status=verified` و `independent_human_review=true` دارای `reviewer_id`, `reviewer_note` و `review_case_hash` معتبر باشد. Hash از همان fieldsی محاسبه می‌شود که reviewer دیده است؛ تغییر بعدی claim/source/date/category/candidate verdict/preparer آن review را غیرقابل استفاده می‌کند.

در نبود reviewer انسانی مستقل، `verified_cases` و `auditable_verified_cases` نباید مصنوعی بالا برده شوند.

Dataset فعلی با manifest به‌صورت reproducible شناخته می‌شود؛ version پیش‌فرض از SHA-256 خود فایل ساخته می‌شود تا تغییر silent در dataset قابل تشخیص باشد.

## Reviewer governance

`political_core.review_governance` می‌تواند یک یا چند review مستقل را ارزیابی کند. در حالت دو-reviewer، reviewerها باید distinct باشند؛ disagreement به `review_conflict` می‌رود و وارد benchmark نمی‌شود. adjudicator در حالت strict باید از reviewerهای قبلی جدا باشد. `StaticReviewerRegistry` فقط یک implementation کنترل‌شده برای تست/deployment ساده است و جای authentication سازمانی، OIDC یا governance واقعی را نمی‌گیرد.

## معیار production

قبل از ادعای production accuracy همهٔ موارد زیر لازم است:

- حداقل ۱۰۰ case auditable verified
- حداقل ۵ case auditable verified در هر ۱۶ دستهٔ لازم
- ground-truth source غیرخالی و قابل بررسی
- independent human review و review audit معتبر
- citation integrity
- false-high-confidence rate و calibration report
- primary-source precision report
- source-independence evaluation
- cost/latency report روی workload واقعی
- Live Quick و Live Deep موفق
- load test مناسب deployment هدف

`political_core.readiness` این موارد را fail-closed ارزیابی می‌کند. وقتی dataset کافی نیست، benchmark gate برابر `insufficient_data` است؛ کمبود داده هرگز pass تلقی نمی‌شود.

Thresholdهای مهندسی فعلی برای gate قابل تنظیم‌اند و تضمین «حقیقت سیاسی» نیستند؛ پیش‌فرض‌ها citation validity >= 0.99، primary-source F1 >= 0.95، false-high-confidence <= 0.03 و high-confidence accuracy >= 0.95 هستند.

## Live end-to-end

Live suite فقط زمانی اجرا می‌شود که محیط واقعاً دارای این مقادیر باشد:

```text
RUN_LIVE_TESTS=1
SEARXNG_URL
OPENAI_API_KEY
OPENAI_MODEL
```

Quick مسیر search → fetch → source assessment → provenance → Judge → guardrails را بررسی می‌کند. Deep علاوه بر آن Judge → Critic → reconciliation را تست می‌کند. verdict سیاسی در live test hard-code نشده است.

Workflow `.github/workflows/live-validation.yml` فقط به‌صورت manual `workflow_dispatch` اجرا می‌شود تا paid validation روی هر push اتفاق نیفتد. اگر secretهای لازم تنظیم نشده باشند، run باید صریحاً SKIP را گزارش کند و نتیجهٔ live جعل نکند.

در اجرای validation مورخ 2026-08-16، workflow به‌درستی اجرا شد اما خود Quick/Deep live tests به علت نبود حداقل یکی از secretهای لازم SKIP شدند. این وضعیت PASS سیاسی محسوب نمی‌شود و readiness همچنان live را blocker نگه می‌دارد.

## Cache، load و observability

SQLite/WAL پیش‌فرض single-instance است. Redis یک backend اختیاری است و فقط در deploymentهایی که `CACHE_BACKEND=redis` و `REDIS_URL` دارند فعال می‌شود. Load harness برای تست کنترل‌شدهٔ cached/uncached workload وجود دارد؛ فشار زیاد روی provider عمومی نباید در CI عادی انجام شود.

Metrics عملیاتی request ID، mode، claim count، provider/cache counts، latency، verdict/confidence و error count را ثبت می‌کنند؛ raw claim و credential در schema metrics وجود ندارد.

## اصل گزارش‌دهی

تا وقتی dataset auditable کافی وجود ندارد، خروجی evaluation باید صریحاً بگوید:

`Production political accuracy is not yet statistically established.`

تا وقتی Live Quick/Deep و workload واقعی اجرا نشده‌اند، `production_ready` باید `false` باقی بماند.
