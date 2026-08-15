# Security

`SafeHttpFetcher` فقط HTTP(S) عمومی را می‌پذیرد، DNS و redirect target را بررسی می‌کند و private/loopback/link-local/reserved/multicast/unspecified IP را رد می‌کند. Timeout، response byte limit، redirect limit و content-type allowlist وجود دارد.

Retrieved content همیشه untrusted data است و instruction داخل صفحه نباید روی reasoning اثر بگذارد. مدل URL تولید نمی‌کند؛ فقط Evidence ID cite می‌کند و core citation را validate می‌کند.

API keys فقط از environment خوانده می‌شوند و secret نباید داخل repo، log یا fixture ذخیره شود.
