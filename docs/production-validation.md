# Production validation plan

این سند وضعیت واقعی اجرای برنامهٔ hardening را ثبت می‌کند.

## اصل ارزیابی

هدف اصلی کاهش `wrong answer with high confidence` است. سیستم باید در کمبود شواهد به verdict محافظه‌کارانه برود و هر خطای کشف‌شده به regression test تبدیل شود.

## فازهای پیاده‌سازی‌شده

- dataset validator برای ۱۶ دسته و review queue صدتایی
- calibration و false-high-confidence reporting
- primary-source precision evaluation helper
- low-cost provenance با attribution، quote/paragraph/shingle overlap و time
- entity aliases برای نام‌های فارسی/لاتین منتخب بدون معتبر دانستن transliteration حدسی
- role-aware timeline که سمت‌های همزمان یک فرد را ادغام نمی‌کند
- search-query cleanup با budget ثابت
- CacheBackend abstraction بدون dependency اجباری Redis/Postgres
- application layer مستقل از Telegram/HTTP
- dependency-free Telegram command adapter
- quick/deep live-test harness
- failure-matrix regression tests

## چیزی که هنوز قابل ادعا نیست

۱۰۰ پروندهٔ موجود machine-prepared/source-backed هستند، نه independently human-reviewed. بنابراین `production_accuracy_established` باید false بماند تا بازبینی انسانی کامل شود.

Live end-to-end نیز فقط وقتی معتبر است که `RUN_LIVE_TESTS=1`, `SEARXNG_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL` واقعاً در محیط اجرا وجود داشته باشند. CI عادی verdict سیاسی زنده جعل نمی‌کند.

## معیارهای production

برای ادعای production accuracy:

- حداقل ۱۰۰ پروندهٔ `verified`
- حداقل ۵ مورد در هر ۱۶ دسته
- ground-truth source غیرخالی
- independent human review
- گزارش false-high-confidence rate و calibration
- citation integrity
- primary-source precision
- source-independence accuracy

نمونهٔ کوچک یا synthetic هرگز کافی نیست.
