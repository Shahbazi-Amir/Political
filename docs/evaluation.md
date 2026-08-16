# Evaluation integrity

Political Core separates **ground truth** from **predictions**.

## Immutable ground truth

The reviewed dataset contains claims, reference dates, expected/acceptable verdicts, source provenance, review governance and a deterministic split. Engine outputs must never be written back into this dataset.

`political-dataset-manifest` reports both:

- `file_sha256`: exact file bytes
- `canonical_content_sha256`: semantic JSONL content after canonical ordering

`dataset_version` derives from the canonical content hash, so gzip metadata does not silently create a new semantic dataset version.

## Benchmark execution

`political-benchmark-run DATASET PREDICTIONS` executes the real application/engine on eligible reviewed cases and writes a separate prediction JSONL artifact.

`political-benchmark-report` joins the reviewed ground truth and prediction artifact only at evaluation time. Reports are schema-versioned and include Git SHA, dataset identity, evaluated split, model/provider metadata and metrics.

## Splits

Cases use a stable `train|calibration|evaluation` split. If a legacy case has no explicit split, `split-v1` deterministically assigns it from the case ID. Threshold tuning belongs on calibration data; release metrics belong on the held-out evaluation split.

## Metrics

Software ID integrity is distinct from semantic support:

- `citation_id_integrity`
- `citation_support_precision`

Primary-source quality reports global TP/FP/FN and separate precision/recall/F1. Production policy prioritizes precision.

Source-independence evaluation uses pairwise source-chain grouping metrics rather than only comparing the number of groups.

False high-confidence metrics have exact and acceptable-verdict variants. Negative-claim overclaim and exact-quote precision are reported only when corresponding audited labels exist.

## Production claims

Sample sufficiency is not quality. `benchmark_sample_sufficient=true` only means enough auditable held-out cases exist. Release readiness is decided separately by quality gates and version-bound CI/live/load/benchmark evidence.

Synthetic and machine-prepared cases never establish political production accuracy.
