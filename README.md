# Political Core

هستهٔ مستقل برای صحت‌سنجی خبر و تحلیل استدلال سیاسی، با اولویت **سند، چندمنبعی بودن و هزینهٔ پایین API**.

## اصل طراحی

هر ادعا در شروع «تأییدنشده» است. سیستم بین واقعیت قابل مشاهده، روایت رسانه و استنباط کاربر فرق می‌گذارد. منبع هم بر اساس نزدیکی به واقعیت سنجیده می‌شود، نه گرایش سیاسی.

## جریان Quick Check

1. Normalize claim — بدون LLM
2. Cache lookup — بدون LLM
3. حداکثر ۲ query جست‌وجو
4. حذف منابع تکراری از یک دامنه
5. ترجیح سند اولیه و حداکثر ۵ منبع
6. فقط **یک** فراخوانی reasoning برای verdict + explanation
7. ذخیره نتیجه در SQLite

حالت Deep Check سقف را به ۶ query، ۱۰ منبع و حداکثر ۲ فراخوانی مدل افزایش می‌دهد.

## Verdicts

`true` · `mostly_true` · `missing_context` · `misleading` · `false` · `unverified`

## معماری

`FactCheckEngine` به دو interface وابسته است: `SearchProvider` و `ReasoningProvider`. بنابراین می‌توان search را با SearxNG/Brave/Tavily/OpenAI web search و مدل را با هر API دلخواه عوض کرد. Telegram، Web یا Desktop فقط adapter هستند و منطق سیاسی داخل UI قرار نمی‌گیرد.

## قدم بعدی

- OpenAI Responses adapter با structured output
- search adapter کم‌هزینه (ترجیحاً SearxNG self-hosted یا provider دارای quota مناسب)
- استخراج citation از خروجی search
- Telegram adapter
- feedback store برای گزارش verdict اشتباه / منبع ضعیف
- regression dataset از ادعاهای واقعی

## اجرای تست

```bash
python -m pytest
```
