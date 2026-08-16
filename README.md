# Political Core

هستهٔ evidence-first برای صحت‌سنجی خبر، ادعا، نقل‌قول و استدلال سیاسی با تمرکز بر **کاهش پاسخ غلط با اعتماد بالا**، استقلال منابع و هزینهٔ پایین API.

## Pipeline

```text
input → atomic claims → entity/date normalization → claim-aware search planning
→ safe IP-pinned fetch → primary-source ownership assessment
→ provenance/copy-chain analysis → diverse evidence selection
→ Judge → optional Deep Critic → deterministic confidence guardrails
→ quote/temporal/negative-claim checks → verdict + citations + diagnostics
```

## Guardrailهای اصلی

- هر ورودی از حالت `UNVERIFIED` شروع می‌شود.
- Primary Document فقط با authority/issuer + document ownership signal پذیرفته می‌شود؛ `/decree/` یا `/law/` به‌تنهایی کافی نیست.
- evidence به atomic claimهای خودش متصل است؛ سند C1 نیاز C2 را خودکار پوشش نمی‌دهد.
- official statement به‌تنهایی حقیقت underlying contested claim نیست.
- copy/syndication روی دامنه‌های مختلف چند تأیید مستقل محسوب نمی‌شود. Graph می‌تواند link ضعیف را برای diagnostics نگه دارد، اما فقط provenance قوی به copy-chain قطعی وارد می‌شود تا single-linkage منابع مستقل را به‌اشتباه یکی نکند.
- quote exact/original باید روی همان evidence برقرار باشد.
- current-status freshness، negative-claim archive coverage و replacement search جداگانه کنترل می‌شوند.
- contradiction/citation فقط با IDهای واقعی پذیرفته می‌شود.
- fetcher روی IP عمومی validate‌شده pin می‌شود، redirect دوباره validate می‌شود و TLS hostname اصلی را verify می‌کند.
- failure موقت search/reasoning پاسخ ساختگی تولید نمی‌کند.
- feedback به‌صورت پیش‌فرض متن خام کاربر را ذخیره نمی‌کند.

## Quick / Deep

Quick budget محدود و حداکثر یک reasoning call دارد. Deep پوشش challenge/replacement/archive بیشتری دارد و حداکثر دو reasoning call (Judge + Critic) مصرف می‌کند.

## نصب و تست

```bash
python -m pip install -e '.[dev]'
python -m compileall -q political_core
python -m pytest -q -m "not live"
python -m political_core.cli --eval-jsonl evals/fixtures/smoke.jsonl
python -m political_core.dataset evals/cases/persian_political_review_queue.jsonl.gz --require-review-queue-ready
```

برای OpenAI:

```bash
python -m pip install -e '.[openai]'
```

## CLI

```bash
export SEARXNG_URL='https://your-searxng.example'
export OPENAI_API_KEY='...'
export OPENAI_MODEL='...'

political-check 'آیا این خبر درست است؟'
political-check --deep 'این ادعا را عمیق بررسی کن'
political-check --refresh 'این وضعیت فعلی را بدون cache بررسی کن'
```

## Application / Telegram

Business logic در core باقی می‌ماند. `PoliticalApplication` لایهٔ application مستقل از transport است و `TelegramAdapter` فقط command routing انجام می‌دهد: `/check`, `/deep`, `/source`, `/why`, `/feedback`.

## Evaluation dataset

`evals/cases/persian_political_review_queue.jsonl.gz` شامل ۱۰۰ پروندهٔ فارسی source-backed در ۱۶ دسته است. این فایل **review queue** است، نه benchmark تأییدشده؛ تا وقتی بازبینی انسانی مستقل انجام نشود، accuracy production را بالا نمی‌برد.

### بازبینی انسانی قابل ممیزی

```bash
python -m political_core.review export \
  evals/cases/persian_political_review_queue.jsonl.gz \
  review-decisions.jsonl

# reviewer فایل تصمیم‌ها را مستقل تکمیل می‌کند

python -m political_core.review apply \
  evals/cases/persian_political_review_queue.jsonl.gz \
  review-decisions.jsonl \
  evals/cases/persian_political_verified.jsonl.gz
```

هر تصمیم به SHA-256 محتوای review‌شده وصل است. تغییر claim/source/date/category/preparer پس از export باعث stale-review rejection می‌شود. `reviewer_id`, `reviewer_note` و `review_case_hash` برای audit نگه داشته می‌شوند. فقط caseهای auditable می‌توانند production benchmark را جلو ببرند. جزئیات در `docs/human-review.md`.

`political_core.benchmark` cost/calibration/ECE/Brier/false-high-confidence را محاسبه می‌کند و علاوه بر final-cache، hit/call واقعی search و fetch provider را گزارش می‌دهد. `political_core.primary_eval` precision/recall/F1 تشخیص primary را فقط روی reviewهای auditable می‌سنجد.

تا وقتی dataset کافی واقعاً independently human-reviewed نشده باشد برنامه باید صریحاً اعلام کند:

`Production political accuracy is not yet statistically established.`

## Live tests

```bash
RUN_LIVE_TESTS=1 \
SEARXNG_URL=... \
OPENAI_API_KEY=... \
OPENAI_MODEL=... \
python -m pytest -m live -q
```

Live suite quick و deep integrity را بدون hard-code کردن verdict سیاسی آزمایش می‌کند. CI عادی credentials را فرض نمی‌کند و live test بدون آن‌ها عمداً deselect/skip می‌شود.

## Cache / deployment

SQLite + WAL برای یک instance مناسب است. `CacheBackend` و `NamespacedCache` مسیر سازگاری برای Redis/PostgreSQL ایجاد می‌کنند، بدون افزودن dependency اجباری به core. Cost summary نرخ cache hit در search/fetch را جدا از final-result cache نگه می‌دارد.

## Privacy

`STORE_USER_CONTENT=false` پیش‌فرض است. FeedbackStore در حالت پیش‌فرض فقط fingerprint/metadata نگه می‌دارد.

## محدودیت‌های شناخته‌شده

- review queue صدتایی هنوز independently human-reviewed نشده است؛ بنابراین production accuracy عمداً false است.
- live end-to-end بدون credential واقعی SearxNG/OpenAI اجرا نمی‌شود.
- provenance و entity/timeline extraction همچنان heuristic هستند؛ weak provenance links به‌تنهایی منابع را merge نمی‌کنند، اما adversarial paraphrase یا پرونده‌های بسیار پیچیده می‌توانند به Deep/Human Review نیاز داشته باشند.
- SQLite برای multi-replica deployment جایگزین Redis/PostgreSQL نیست.
- reviewer identity/competence یک مسئلهٔ governance بیرون از این کد است؛ hash فقط ثابت می‌کند کدام نسخهٔ case review شده است.

جزئیات: `docs/production-validation.md`, `docs/human-review.md`, `docs/security.md`, `docs/evaluation.md`.
