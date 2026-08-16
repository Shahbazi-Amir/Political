# Independent human review workflow

The 100-case Persian queue is machine-prepared and source-backed, not a verified political benchmark. A case becomes production-eligible only after an independent human reviewer checks the claim against its listed evidence.

## Why review decisions are separate files

Review metadata is stored separately before promotion so a reviewer cannot accidentally mutate the case while judging it. Each review template carries a SHA-256 `case_fingerprint` over the claim, date, category, candidate verdict, source URLs, notes and tags. If any of those fields change after the review template was exported, applying the old decision fails as stale.

## Export templates

```bash
python -m political_core.review export \
  evals/cases/persian_political_review_queue.jsonl.gz \
  review-decisions.jsonl
```

The reviewer fills `reviewer_id`, `reviewed_at`, `expected_verdict`, optional `acceptable_verdicts`, and a substantive `reviewer_note`. The reviewer must not be the recorded preparer.

## Apply reviewed decisions

```bash
python -m political_core.review apply \
  evals/cases/persian_political_review_queue.jsonl.gz \
  review-decisions.jsonl \
  evals/cases/persian_political_verified.jsonl.gz
```

Application is fail-closed: duplicate decisions, unknown case IDs, stale fingerprints, missing reviewer metadata, non-independent reviewers, or invalid verdicts stop publication of the output file.

The promoted record preserves `reviewer_id` and `review_case_hash` so later audits can confirm which exact case content was reviewed. This metadata does not prove that a reviewer was competent; organizational reviewer identity/quality control remains an external governance responsibility.

## Production threshold

Do not report production accuracy until the dataset validator reports at least 100 auditable verified cases, required category coverage, and the evaluation pipeline reports calibration/false-high-confidence metrics. Machine-prepared cases never count as verified merely because they have source URLs.
