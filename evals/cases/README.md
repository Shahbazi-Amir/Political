# Political evaluation cases

این پوشه برای پرونده‌های سیاسی واقعی و source-backed است. هیچ case صرفاً برای بالا بردن accuracy نباید `verified` شود.

## فایل اصلی review queue

`persian_political_review_queue.jsonl.gz` شامل ۱۰۰ پروندهٔ فارسی است که در ۱۶ دستهٔ اجباری پخش شده‌اند. هر پرونده منبع یا منابع مشخص دارد، اما در نسخهٔ تولیدشده توسط ماشین با این وضعیت نگه داشته می‌شود:

- `review_status: human_required`
- `expected_verdict: null`
- `independent_human_review: false`

بنابراین این ۱۰۰ مورد **هنوز benchmark تأییدشده نیستند** و در accuracy سیاسی production شمرده نمی‌شوند.

## schema حداقلی

هر پرونده باید شامل این فیلدها باشد:

`id`, `claim`, `language`, `claim_type`, `category`, `reference_date`,
`expected_verdict`, `candidate_verdict`, `acceptable_verdicts`,
`ground_truth_sources`, `ground_truth_notes`, `review_status`,
`independent_human_review`, `reviewed_at`, `tags`.

`verified` فقط بعد از بررسی واقعی انسان، ثبت verdict مورد انتظار، تاریخ بازبینی، یادداشت review و source provenance مجاز است.

## اعتبارسنجی

```bash
python -m political_core.dataset evals/cases/persian_political_review_queue.jsonl.gz --require-review-queue-ready
```

این validation وجود ۱۰۰ مورد، URL منبع، یکتایی ID و حداقل ۵ پرونده در هر ۱۶ دسته را کنترل می‌کند. آماده بودن review queue با «اثبات دقت production» یک چیز نیست.
