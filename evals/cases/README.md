# Political evaluation cases

این پوشه برای پرونده‌های **واقعی و بازبینی‌شده** است. هیچ case فقط برای بالا بردن accuracy نباید `verified` شود.
حداقل schema شامل `id`, `claim`, `language`, `claim_type`, `reference_date`, `expected_verdict`, `acceptable_verdicts`, `ground_truth_sources`, `ground_truth_notes`, `review_status`, `reviewed_at`, `tags` است.
`human_required` در accuracy سیاسی شمرده نمی‌شود. `synthetic: true` فقط smoke/regression plumbing است. `verified` فقط پس از provenance و بازبینی انسانی مجاز است. خبر فوری قبل از تثبیت benchmark stable نیست.
