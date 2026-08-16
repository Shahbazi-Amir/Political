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
- copy/syndication روی دامنه‌های مختلف چند تأیید مستقل محسوب نمی‌شود.
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

Business logic در core باقی می‌ماند. `PoliticalApplication` لایهٔ application مستقل از transport است و `TelegramAdapter` فقط command routing انجام می‌دهد:

`/check`, `/deep`, `/source`, `/why`, `/feedback`.

برای اتصال واقعی Telegram می‌توان adapter را پشت aiogram/python-telegram-bot یا webhook HTTP قرار داد بدون اینکه منطق fact-checking وارد bot handler شود.

## Evaluation

`evals/cases/persian_political_review_queue.jsonl.gz` شامل ۱۰۰ پروندهٔ فارسی source-backed در ۱۶ دسته است. این فایل review queue است، نه benchmark تأییدشده: همهٔ پرونده‌ها فعلاً `human_required` هستند و accuracy production را بالا نمی‌برند.

`political_core.dataset` schema/category coverage را validate می‌کند. `political_core.benchmark` cost/calibration/ECE/Brier/false-high-confidence را محاسبه می‌کند و `political_core.primary_eval` precision/recall/F1 تشخیص primary را فقط روی رکوردهای واقعاً human-reviewed می‌سنجد.

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

Live suite quick و deep integrity را بدون hard-code کردن verdict سیاسی آزمایش می‌کند.

## Cache / deployment

SQLite + WAL برای یک instance مناسب است. `CacheBackend` و `NamespacedCache` مسیر سازگاری برای Redis/PostgreSQL ایجاد می‌کنند، بدون افزودن dependency اجباری به core.

## Privacy

`STORE_USER_CONTENT=false` پیش‌فرض است. FeedbackStore در حالت پیش‌فرض فقط fingerprint/metadata نگه می‌دارد.

## محدودیت‌های شناخته‌شده

- review queue صدتایی هنوز human-reviewed نشده است.
- live end-to-end بدون credential واقعی اجرا نمی‌شود.
- provenance و entity/timeline extraction همچنان heuristic هستند و adversarial paraphrase یا پرونده‌های بسیار پیچیده می‌توانند به deep/human review نیاز داشته باشند.
- SQLite برای multi-replica deployment جایگزین Redis/PostgreSQL نیست.

جزئیات: `docs/production-validation.md`, `docs/security.md`, `docs/evaluation.md`.
