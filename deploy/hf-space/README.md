---
title: Smart Decor — Demo
emoji: 🛋️
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: AI-matched living-room decor with explainable recommendations
---

# Smart Interior Decor — نسخهٔ نمایشی

نسخهٔ نمایشی پلتفرم پیشنهاد دکوراسیون داخلی، با پیشنهادهای قابل‌توضیح،
مودبورد، پلان دوبعدی و فهرست خرید.

## حساب‌های آمادهٔ ورود

| نقش | ایمیل | رمز |
|---|---|---|
| مشتری (خانه‌دار) | `demo@smartdecor.dev` | `Demo1234!` |
| طراح | `designer@smartdecor.dev` | `Design123!` |
| مدیر سیستم | `admin@smartdecor.dev` | `Admin123!` |

## نکته‌های مهم دربارهٔ این نسخه

* **اطلاعات موقتی است.** با هر بار راه‌اندازی دوباره، پایگاه داده از نو ساخته و
  داده‌های نمونه دوباره بارگذاری می‌شود. هر تغییری که ایجاد کنید بعد از
  راه‌اندازی مجدد پاک می‌شود. برای نمایش‌های تکراری این یک مزیت است.
* **پس از حدود ۴۸ ساعت بی‌استفاده ماندن، این فضا به خواب می‌رود.** اولین باز
  کردن بعد از خواب ممکن است یک تا دو دقیقه طول بکشد.
* **هوش مصنوعی در حالت آزمایشی (mock) است** — نتیجه‌ها قطعی و تکرارپذیرند اما
  خروجی مدل واقعی نیستند.
* **پرداخت در حالت sandbox است** — هیچ پول واقعی جابه‌جا نمی‌شود.

---

## About this demo (English)

A single-container demo of the Smart Interior Decor Recommendation Platform:
PostgreSQL 16 + pgvector, Redis, a FastAPI backend and the built React SPA,
all under supervisord.

**This is a demo box, not the production topology.**

* Storage is **ephemeral** — the database is re-created and re-seeded on every
  restart (deviation D-4a).
* The Space **sleeps after ~48 h idle**; the first request after that pays the
  cold start (deviation D-4b).
* **AI is mocked** (deterministic, offline) and payments use the **Zarinpal
  sandbox**. No third-party credential exists in this container.
* Interactive API docs (`/docs`, `/redoc`, `/openapi.json`) are **disabled** —
  enforced twice, by an explicit application setting (`API_DOCS_MODE=disabled`)
  and again at the nginx edge.
* TLS is terminated by the Hugging Face platform, not by this container
  (deviation D-4c); origin-TLS verification belongs to the production
  deployment.
* The three demo accounts exist **only here**. They can never be created under
  `APP_ENV=production` — the container re-proves that refusal on every boot and
  refuses to serve if it ever fails.

Production deployment (separate services, Caddy with TLS 1.3, S3 storage, a
real AI provider) is unchanged and lives in `docker-compose.prod.yml`.
