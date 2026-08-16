# Production validation status

The software validation layer is designed to fail closed on epistemic claims while allowing operational caches to fail open.

## Measurement integrity

Production evaluation requires:

1. genuine auditable human reviews,
2. a versioned immutable ground-truth dataset,
3. a separate prediction artifact produced by the actual engine,
4. held-out evaluation data,
5. a schema-versioned benchmark report,
6. CI, live, load and benchmark evidence bound to the same Git SHA.

A green workflow is not automatically live validation. A skipped live stage remains `skipped` in `live-validation-report.json` and cannot satisfy readiness.

## Human review

Governed promotions bind:

- the reviewed case fingerprint,
- each review record hash,
- adjudication hash when present,
- policy version,
- a governance bundle hash.

`reviewed_at` must be timezone-aware ISO-8601 and must not be implausibly future-dated. Multi-review policy is enforced through `required_reviewers_per_case`; a single-review record cannot satisfy a two-review production gate.

Reviewer identity remains an external governance concern. The core supports assurance levels (`unverified`, `registry_verified`, `externally_authenticated`) but does not pretend that a text reviewer ID proves a real-world identity.

## Dataset provenance

Ground-truth source records may bind URL, canonical URL, retrieval time and content SHA-256 to the reviewed case. Optional source-rot checking reports changed/missing sources without mutating historical ground truth.

## Runtime

SQLite remains the default single-instance cache. Redis is optional, uses server-side TTL, and is wrapped by fail-open cache behavior by default. Cache failure is an operational degradation, not a reason to fabricate or suppress a fact-check.

Provider/cache metrics are request-local deltas. A final-cache hit must not replay the provider calls or token cost of the request that originally created the cached result.

Rate-limit subject state, Telegram last-result state and in-memory metrics are bounded. Unexpected verification errors emit failure telemetry and Telegram returns a conservative Persian unavailable message rather than a political verdict.

## External blockers

Production readiness remains false until all external gates are genuinely closed:

- sufficient independent human review,
- Live Quick passed,
- Live Deep passed,
- held-out benchmark quality gates passed,
- controlled production-representative load validation passed.

Missing credentials or humans must be reported, never fabricated.
