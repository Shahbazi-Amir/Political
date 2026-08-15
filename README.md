# Political Core

هستهٔ مستقل و Persian-first برای **صحت‌سنجی سیاسی evidence-first**؛ طراحی شده برای این‌که خبر یا ادعا را از ابتدا تأییدنشده بداند، منبع اولیه را ترجیح دهد، بازنشرها را تأیید مستقل حساب نکند و در نبود شواهد کافی با اطمینان بالا جواب ندهد.

## معماری

```text
input
→ intent + atomic claims
→ research plan (neutral / primary / challenge)
→ cache
→ search + safe fetch
→ evidence scoring
→ provenance / source-chain grouping
→ structured reasoning
→ deterministic confidence guardrails
→ citation validation
→ verdict + diagnostics
```

LLM اجازه ندارد URL یا منبع بسازد؛ فقط Evidence IDهایی مثل `E1` را cite می‌کند و core آن‌ها را validate می‌کند.

## Verdicts

`true` · `mostly_true` · `missing_context` · `misleading` · `mostly_false` · `false` · `unverified` · `insufficient_evidence` · `conflicting_evidence` · `outdated` · `opinion_not_fact` · `prediction`

## محافظت‌های اصلی

- خبر از ابتدا `UNVERIFIED` است.
- سند اصلی برای ادعاهای حقوقی/انتصاب/عضویت اولویت دارد.
- چند URL کپی‌شده یک تأیید مستقل محسوب نمی‌شوند.
- source reputation فقط prior است؛ هیچ رسانه‌ای whitelist حقیقت نیست.
- ادعای منفی با «در سرچ پیدا نشد» اثبات نمی‌شود.
- breaking news و high-impact claims بدون سند/استقلال کافی confidence cap دارند.
- تناقض حل‌نشده confidence را محدود می‌کند.
- citation جعلی مدل حذف و در صورت نبود citation معتبر verdict به `unverified` محدود می‌شود.
- محتوای وب data غیرقابل‌اعتماد است، نه instruction.
- fetcher در برابر SSRF، private IP، redirect به شبکه خصوصی، حجم زیاد و content-type نامجاز محافظت دارد.

## Quick و Deep

Quick پیش‌فرض برای بات:

```text
2 query
5 fetch
5 source
1 reasoning call
```

Deep:

```text
6 query
12 fetch
12 source
حداکثر 2 reasoning call در budget
```

نسخه فعلی engine عمداً در یک check معمولی فقط یک reasoning call انجام می‌دهد؛ budget دوم برای repair/escalation صریح آینده رزرو شده و loop نامحدود وجود ندارد.

## نصب

```bash
python -m pip install -e '.[dev]'
```

OpenAI adapter اختیاری:

```bash
python -m pip install -e '.[openai]'
```

## تنظیمات CLI

```bash
export SEARXNG_URL='https://your-searxng.example'
export OPENAI_API_KEY='...'
export OPENAI_MODEL='...'
```

مدل عمداً hard-code نشده تا انتخاب هزینه/کیفیت و تغییرات مدل‌ها دست اپراتور باشد.

## اجرا

```bash
political-check "آیا این ادعا درست است؟"
political-check --deep "آیا این ادعا درست است؟"
political-check --json "آیا این ادعا درست است؟"
```

اگر provider خارجی تنظیم نشده باشد CLI با خطای configuration واضح متوقف می‌شود و پاسخ ساختگی تولید نمی‌کند.

## Cost controls

تنظیم‌های اصلی محیط:

`QUICK_MAX_QUERIES`, `QUICK_MAX_FETCHES`, `QUICK_MAX_SOURCES`, `DEEP_MAX_QUERIES`, `DEEP_MAX_FETCHES`, `DEEP_MAX_SOURCES`, `CACHE_PATH`, `FETCH_TIMEOUT`, `MAX_RESPONSE_BYTES`, `STORE_USER_CONTENT`.

SQLite cache قبل از مصرف provider بررسی می‌شود. TTL برای breaking/current-status کوتاه‌تر است.

## Evaluation

Runner برای datasetهای curated به‌صورت JSONL:

```bash
political-check --eval-jsonl evals/my_cases.jsonl
```

Metrics فعلی شامل verdict accuracy، high-confidence accuracy، false-high-confidence rate و citation validity است. پروژه عمداً ground truth سیاسی ساختگی داخل repo نمی‌گذارد؛ dataset سیاسی باید با منبع و بازبینی انسانی curate شود.

## تست

```bash
python -m pytest
python -m compileall -q political_core
```

سناریوهای adversarial شامل خبرهای copy، citation جعلی، ادعای منفی، breaking/high-impact، تضاد منابع و SSRF هستند.

## مستندات

- `docs/architecture.md`
- `docs/fact-checking-policy.md`
- `docs/confidence-model.md`
- `docs/security.md`

## اتصال Telegram/Web

Core هیچ dependency تلگرامی ندارد. Adapter باید فقط `FactCheckEngine.check()` را صدا بزند و نتیجه را render کند؛ منطق صحت‌سنجی نباید داخل UI قرار بگیرد.
