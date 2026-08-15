# Confidence Model

Confidence نهایی فقط نظر مدل نیست. مدل یک پیشنهاد می‌دهد و core آن را محدود می‌کند.

نمونه caps فعلی:

- یک evidence ضعیف: حداکثر `0.35`
- یک گروه مستقل بدون primary: حداکثر `0.62`
- چند URL ولی یک source-chain: حداکثر `0.58`
- conflict حل‌نشده: حداکثر `0.65`
- breaking بدون primary: حداکثر `0.60`
- high-impact بدون primary و بدون دو منبع مستقل: حداکثر `0.55`
- negative claim بدون primary: حداکثر `0.58` و `true` به `unverified` محدود می‌شود
- current-status با evidence تاریخ‌گذشته: حداکثر `0.55`

این اعداد policy هستند و باید با dataset واقعی calibration شوند. مهم‌ترین metric، `false_high_confidence_rate` است.
