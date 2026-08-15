# Evals

Political ground truth باید curated و مستند باشد؛ این repo عمداً claim سیاسی ساختگی را به‌عنوان حقیقت وارد نمی‌کند.

JSONL schema حداقلی برای runner:

```json
{"expected_verdict":"true","actual_verdict":"true","confidence":0.91,"citation_ids":["E1"],"available_evidence_ids":["E1","E2"]}
```

برای dataset واقعی، هر case باید provenance منبع ground-truth و تاریخ بازبینی انسانی داشته باشد.
