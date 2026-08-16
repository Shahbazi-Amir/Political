# Security

Fetch: فقط HTTP/HTTPS، URL userinfo ممنوع، localhost/private/link-local/reserved IP ممنوع، همه IPهای DNS باید public باشند، redirect دوباره validate می‌شود، تغییر مشکوک DNS resolution رد می‌شود، MIME/size محدود و binary-like content رد می‌شود.

LLM: retrieved content untrusted data است، instruction داخل webpage نادیده گرفته می‌شود، model URL/citation جدید نمی‌سازد، structured output validate می‌شود، retry حداکثر یک بار و failure به safe uncertainty منجر می‌شود. Secrets فقط environment.
