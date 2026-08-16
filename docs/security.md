# Security

- Web content is untrusted data, never instruction.
- URL schemes are limited to public `http/https`.
- localhost, private, loopback, link-local, multicast, reserved and unspecified addresses are rejected.
- URL userinfo is rejected.
- Redirect targets are revalidated.
- HTTP/HTTPS connections are pinned to an IP that passed public-address validation; HTTPS still verifies the original hostname/SNI. This closes the previous DNS-rebinding TOCTOU window between validation and connection.
- Response size and MIME type are bounded; binary-like text is rejected.
- SearxNG JSON responses are also size/MIME bounded.
- Model citations/contradictions are validated against supplied Evidence/Claim IDs.
- API keys/tokens are environment-only and must not be logged or committed.
- SQLite cache uses WAL/busy-timeout for concurrent bot requests and corrupt cache rows are evicted rather than crashing verification.
- Feedback storage defaults to no raw user claim/comment; only a fingerprint and metadata are retained unless storage is explicitly opted in.
