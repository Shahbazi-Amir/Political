# Political Core

هستهٔ evidence-first برای صحت‌سنجی خبر، ادعا، نقل‌قول و استدلال سیاسی با تمرکز بر **کاهش پاسخ غلط با اعتماد بالا**، استقلال منابع و هزینهٔ پایین API.

## اصل سیستم
هر ورودی در شروع `UNVERIFIED` است. سیستم بین واقعیت/رویداد، ادعای رسمی، گزارش رسانه‌ای، سند اولیه، استنباط/framing، نظر و پیش‌بینی فرق می‌گذارد. رسمی بودن منبع فقط هویت صادرکننده را قوی‌تر می‌کند؛ به‌تنهایی هر ادعای آن منبع را حقیقت نمی‌کند.

## Pipeline
```text
input → claim decomposition → entity/date normalization → claim-aware search planning
→ claim-level search coverage → safe fetch → primary-source authority assessment
→ source provenance / copy-chain analysis → diverse evidence selection
→ Judge → optional Deep Critic → deterministic confidence guardrails
→ quote / temporal / negative-claim checks → verdict + citations + diagnostics
```

## مهم‌ترین guardrailها
- URL مثل `/decree/` یا `/law/` به‌تنهایی Primary Source نمی‌سازد.
- Primary Document باید هم document signal و هم issuer-authority match داشته باشد.
- چند بازنشر از یک wire/press release چند تأیید مستقل نیست.
- ادعای منفی با «در سرچ پیدا نشد» اثبات نمی‌شود.
- current-status بر اساس freshness کوتاه‌تر بررسی می‌شود.
- تاریخ شمسی/جلالی و عبارت‌های نسبی پشتیبانی می‌شوند.
- نقل‌قول دقیق بدون متن/رونوشت اصلی تأیید نمی‌شود.
- official statement می‌تواند ثابت کند «این نهاد چنین گفت»، نه لزوماً واقعیت underlying claim.
- citation فقط از Evidence IDهای واقعی قابل استفاده است.
- Deep mode واقعاً Judge + Critic دارد.
- failure مدل یا سرچ باعث hallucinated answer نمی‌شود.

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
```
Issuer registry اختیاری: `POLITICAL_AUTHORITY_DOMAINS='example.gov=Example Agency,official.example=Institution'`. این truth whitelist نیست؛ فقط مالک/صادرکننده سند را مشخص می‌کند.

## Live tests
```bash
RUN_LIVE_TESTS=1 SEARXNG_URL=... OPENAI_API_KEY=... OPENAI_MODEL=... python -m pytest -m live -q
```
Live test verdict سیاسی را ground truth جعل نمی‌کند؛ فقط integrity مسیر واقعی را بررسی می‌کند.

## Evaluation
`political-check --eval-jsonl evals/cases/your_verified_cases.jsonl`
Metricها شامل verdict accuracy، high-confidence accuracy، false-high-confidence rate، citation validity، primary-source F1، source-independence، coverage، هزینه و calibration bins هستند.
تا وقتی dataset واقعی و human-reviewed کافی نداریم برنامه صریحاً اعلام می‌کند: `Production political accuracy is not yet statistically established.`

## امنیت
SSRF/private IP/localhost blocking، redirect validation، size/MIME limits، prompt-injection boundary و no-secret-in-repo. جزئیات در `docs/`.
