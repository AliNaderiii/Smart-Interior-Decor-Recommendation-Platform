# Smart Decor Platform — Agent Master Prompt Pack

## هدف
این بسته برای آماده‌سازی مخزن `AliNaderiii/Smart-Interior-Decor-Recommendation-Platform` جهت ارائه و فروش به کارفرمای پروژه پونیشا تهیه شده است.

## ترتیب اجرا

### موج ۱ — مستقل و کم‌ریسک
1. `01-baseline-release-governance.md`
2. `02-research-benchmark.md`
3. `03-security-privacy.md`
4. `04-ai-recommender-data.md`
5. `05-frontend-rtl-ux.md`
6. `06-integrations-payments-storage.md`
7. `07-infrastructure-cicd-observability.md`

### موج ۲ — پس از مشخص‌شدن قراردادها
8. `08-qa-acceptance-testing.md`
9. `09-sales-demo-documentation.md`

### موج ۳ — ادغام نهایی
10. `10-integration-release-manager.md`

## قانون اجرای موازی
هر سشن باید قبل از شروع:

- از `main` یا تگ baseline یک **worktree/branch اختصاصی** بسازد.
- فقط فایل‌ها و دایرکتوری‌های مجاز در Master Prompt خودش را تغییر دهد.
- در صورت نیاز به فایل مشترک، آن را تغییر ندهد و یک `integration-request.md` تولید کند.
- هیچ branch، commit یا PR سشن دیگر را rebase، reset، cherry-pick یا force-push نکند.
- branch اختصاصی با الگوی `agent/<stage>-<date>` بسازد.
- هر commit فقط یک موضوع منطقی داشته باشد.
- PR خود را فقط برای branch مقصد تعیین‌شده ارسال کند؛ ادغام فقط توسط Prompt 10 انجام می‌شود.

## قرارداد خروجی هر عامل
هر عامل باید این موارد را تحویل دهد:

- کد/مستندات/testهای مربوط به Scope خودش
- `docs/agent-reports/<stage>-report.md`
- `docs/agent-reports/<stage>-evidence/` شامل log، screenshot، benchmark یا test output
- فهرست تغییرات و فایل‌های تغییرکرده
- ریسک‌های باقی‌مانده و تصمیم‌های نیازمند کارفرما
- `integration-request.md` در صورت نیاز به تغییر فایل مشترک
- PR بدون merge کردن branch دیگر

## Definition of Done عمومی
- هیچ ادعای «انجام شد» بدون command و evidence پذیرفته نیست.
- تست‌های مرتبط، lint، type-check و build باید اجرا شوند یا علت دقیق عدم اجرا ثبت شود.
- secret، token، API key، داده شخصی و credential هرگز commit نشود.
- تغییرات backward-compatible باشند مگر اینکه migration و release note ارائه شود.
- هر تغییر API دارای schema، authorization، error handling، test و مستندات باشد.
- کار ناقص با TODO مبهم تحویل نشود؛ یا کامل شود یا به‌صورت ریسک مستند و از Scope خارج شود.

## فهرست وضعیت
در پایان هر موج، مدیر ادغام باید این موارد را بررسی کند:

- [ ] baseline tag و clean working tree
- [ ] dependency lock و محیط reproducible
- [ ] گزارش واقعی AI جدا از mock
- [ ] امنیت و حریم خصوصی تأییدشده
- [ ] PostgreSQL/pgvector و Redis واقعی تست‌شده
- [ ] پرداخت sandbox و callback idempotent تست‌شده
- [ ] Lighthouse، Core Web Vitals و accessibility گزارش‌شده
- [ ] E2E سه role و paywall pass
- [ ] demo و proposal آماده ارسال
- [ ] rollback plan و handover کامل
