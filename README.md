# Political Core

هستهٔ evidence-first برای صحت‌سنجی خبر، ادعا، نقل‌قول و استدلال سیاسی با تمرکز بر **کاهش پاسخ غلط با اعتماد بالا**، استقلال منابع و هزینهٔ پایین API.

## اصل سیستم
هر ورودی در شروع `UNVERIFIED` است. سیستم بین واقعیت/رویداد، ادعای رسمی، گزارش رسانه‌ای، سند اولیه، استنباط/framing، نظر و پیش‌بینی فرق می‌گذارد. رسمی بودن منبع فقط هویت صادرکننده را قوی‌تر می‌کند؛ به‌تنهایی هر ادعای آن منبع را حقیقت نمی‌کند.

## Pipeline
```text
input → claim decomposition → entity/date normalization → claim-aware search planning
→ claim-level search coverage → safe IP-pinned fetch → primary-source authority assessment
→ source provenance / copy-chain analysis → diverse evidence selection
→ Judge → optional Deep Critic → deterministic confidence guardrails
→ quote / temporal / negative-claim checks → verdict + citations + diagnostics
```

## مهم‌ترین guardrailها
- URL مثل `/decree/` یا `/law/` به‌تنهایی Primary Source نمی‌سازد.
- Primary Document باید هم document signal و هم issuer-authority match داشته باشد؛ authority registry روی subdomainهای همان نهاد هم اعمال می‌شود.
- Evidence به atomic claimهایی که آن را پیدا کرده‌اند متصل می‌شود؛ سند C1 الزام C2 را خودکار برآورده نمی‌کند.
- چند بازنشر از یک wire/press release چند تأیید مستقل نیست، حتی اگر روی چند دامنه باشند.
- ادعای منفی با «در سرچ پیدا نشد» اثبات نمی‌شود و negative/freshness search به‌دروغ primary-search شمرده نمی‌شود.
- current-status بر اساس freshness کوتاه‌تر بررسی می‌شود؛ تاریخ آیندهٔ نامعقول stale/anomalous تلقی می‌شود.
- تاریخ شمسی/جلالی، اعتبار روز ماه و عبارت‌های نسبی پشتیبانی می‌شوند.
- نقل‌قول دقیق فقط وقتی original محسوب می‌شود که همان best-match روی منبع اولیه/issuer-owned باشد.
- official statement می‌تواند ثابت کند «این نهاد چنین گفت»، نه لزوماً واقعیت underlying claim.
- contradictionهای مدل فقط با Evidence ID و Claim ID واقعی پذیرفته می‌شوند.
- citation فقط از Evidence IDهای واقعی قابل استفاده است.
- Deep mode واقعاً Judge + Critic دارد.
- failure مدل یا سرچ باعث hallucinated answer نمی‌شود و failure گذرای reasoning در final-result cache ذخیره نمی‌شود.
- `--refresh` cache نهایی، search cache و fetch cache را دور می‌زند.

## Quick / Deep
Quick: budget محدود سرچ، چند fetch محدود، حداکثر ۱ reasoning call.
Deep: coverage بیشتر، challenge/replacement/archive search، Judge + Critic، حداکثر ۲ reasoning call.

## نصب
```bash
python -m pip install -e '.[dev]'
python -m pytest -q
```
برای OpenAI: `python -m pip install -e '.[openai]'`

## CLI
```bash
export SEARXNG_URL='https://your-searxng.example'
export OPENAI_API_KEY='...'
export OPENAI_MODEL='...'
political-check 'آیا این خبر درست است؟'
political-check --deep 'این ادعا را عمیق بررسی کن'
political-check --refresh 'این وضعیت فعلی را بدون cache بررسی کن'
```
Issuer registry اختیاری: `POLITICAL_AUTHORITY_DOMAINS='example.gov=Example Agency,official.example=Institution'`. این truth whitelist نیست؛ فقط مالک/صادرکننده سند را مشخص می‌کند.

Cache settings اختیاری:
```text
SEARCH_CACHE_TTL=300
FETCH_CACHE_TTL=600
CACHE_MAX_ROWS=20000
```
برای current/breaking claim، final-result TTL مستقل و کوتاه‌تر اعمال می‌شود.

## Privacy / Feedback
`STORE_USER_CONTENT=false` سیاست پیش‌فرض است. `FeedbackStore` نیز به‌طور پیش‌فرض متن claim/comment را نگه نمی‌دارد و فقط fingerprint و نوع feedback ذخیره می‌کند؛ ذخیره متن باید صریحاً opt-in شود.

## Live tests
```bash
RUN_LIVE_TESTS=1 SEARXNG_URL=... OPENAI_API_KEY=... OPENAI_MODEL=... python -m pytest -m live -q
```
Live test verdict سیاسی را ground truth جعل نمی‌کند؛ فقط integrity مسیر واقعی را بررسی می‌کند.

## Evaluation
`political-check --eval-jsonl evals/cases/your_verified_cases.jsonl`
Metricها شامل verdict accuracy، high-confidence accuracy، false-high-confidence rate، citation validity، primary-source F1، source-independence، coverage، هزینه و calibration bins هستند.
فقط caseهایی که **صریحاً** `review_status=verified` و `ground_truth_sources` معتبر دارند وارد accuracy می‌شوند. sample readiness حداقل ۱۰۰ case و پوشش دسته‌های بحرانی می‌خواهد؛ production accuracy علاوه بر آن independent human review می‌خواهد.
تا وقتی dataset واقعی و human-reviewed کافی نداریم برنامه صریحاً اعلام می‌کند: `Production political accuracy is not yet statistically established.`

## امنیت
Fetcher به IP عمومی validate‌شده pin می‌شود و TLS hostname اصلی را verify می‌کند تا پنجرهٔ DNS-rebinding بین validation و connect بسته شود. همچنین private IP/localhost blocking، redirect re-validation، size/MIME limits، prompt-injection boundary و no-secret-in-repo وجود دارد.

## محدودیت‌های شناخته‌شده
- provenance هنوز heuristic است؛ adversarial paraphrase بسیار حرفه‌ای ممکن است source-chain را پنهان کند.
- entity extraction و transliteration فارسی deterministic/heuristic هستند و NER کامل زبانی نیستند.
- timeline از متن استخراج می‌شود و برای پرونده‌های پیچیدهٔ چندشخصی ممکن است به review عمیق نیاز داشته باشد.
- دقت سیاسی production تا قبل از dataset واقعی کافی **اثبات‌شده نیست**.
