# Architecture

`FactCheckEngine` UI-agnostic است. Telegram/Web/Desktop فقط adapter هستند.

Core:
- `claims.py`: intent، atomic claims، claim-aware query planning و coverage
- `entity.py`: alias/entity normalization
- `temporal.py`: Jalali/Gregorian/relative dates و freshness
- `primary_source.py`: issuer/document ownership assessment
- `source_policy.py`: evidence role/quality
- `provenance.py`: source-chain graph و independence
- `fetch.py`: safe retrieval
- `quotes.py`: exact quote verification
- `timeline.py`: entity-role events
- `openai_reasoning.py`: Judge/Critic adapter
- `confidence.py`: deterministic post-model guardrails
- `evals.py`: calibration/benchmark metrics

Quick یک reasoning call دارد. Deep روی همان evidence bundle ابتدا Judge و سپس Critic دارد و disagreement محافظه‌کار reconcile می‌شود. Failure سرچ/fetch/provider در diagnostics ثبت می‌شود؛ اگر Judge در دسترس نباشد نتیجه `verification_unavailable` است، نه پاسخ حدسی.
