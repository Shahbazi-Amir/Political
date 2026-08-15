# Architecture

## Boundaries

`SearchProvider`, `Fetcher`, `ReasoningProvider`, cache و output از هم جدا هستند. Engine منطق orchestration را نگه می‌دارد و provider-specific behavior داخل آن hard-code نمی‌شود.

## Claim layer

`claims.py` intent، atomic claims، dependencies، negative/high-impact/current/breaking flags و required evidence را deterministic استخراج می‌کند. هدف ایجاد guardrail ارزان قبل از LLM است.

## Retrieval layer

Query plan در Quick محدود و در Deep شامل primary/challenge/support/freshness/negative-existence می‌شود. Fetcher HTML را پاک‌سازی و passageهای مرتبط را محدود می‌کند تا token waste کم شود.

## Evidence + provenance

هر Evidence URL canonical، source kind/role، relevance، quality، independence key و source chain دارد. `provenance.py` با explicit cited-source و similarity بازنشرهای محتمل را گروه‌بندی می‌کند. این heuristic محافظه‌کار است و ادعای شناخت مالکیت پنهان رسانه‌ها ندارد.

## Reasoning boundary

Reasoning model فقط evidence bundle را می‌بیند و فقط Evidence ID cite می‌کند. URLها در اختیار application code هستند. محتوای fetched به‌عنوان untrusted data علامت‌گذاری می‌شود.

## Deterministic post-validation

حتی اگر مدل confidence بالا بدهد، `confidence.py` caps مستقل اعمال می‌کند: منبع ضعیف واحد، source-chain واحد، conflict، negative claim، breaking news، high-impact و stale current-status.

## Cache / cost

Cache key بر fingerprint نرمال‌شده + mode بنا شده است. TTL براساس temporal sensitivity تغییر می‌کند. Quick یک reasoning call دارد.
