# چک‌لیست آماده‌سازی برای فروش و شروع پروژه

## A. کنترل نسخه و وضعیت پایه
- [ ] تعیین commit/tag baseline و ثبت تاریخ و محیط
- [ ] اصلاح README و حذف ادعاهای قدیمی/متناقض
- [ ] ثبت نسخه Python/Node/PostgreSQL/pgvector/Redis
- [ ] اجرای clean install در محیط تازه
- [ ] بررسی secrets، `.env.example` و نبود credential در Git
- [ ] تعیین مالکیت کد، مجوزها و سیاست third-party assets

## B. کشف محصول و قرارداد
- [ ] نهایی‌کردن taxonomy اتاق نشیمن و دسته‌های محصول
- [ ] تأیید وزن‌های recommender و tie-breaking
- [ ] تعیین مدل Free/Pro، مبلغ، مدت، refund و entitlement
- [ ] دریافت برند، رنگ، فونت، متن فارسی و RTL requirement
- [ ] دریافت dataset محصولات و ۵۰ تصویر benchmark با ground truth
- [ ] تعیین درگاه، S3/CDN، ایمیل، دامنه و API keys
- [ ] امضای acceptance criteria، milestone، warranty و out-of-scope

## C. امنیت و حریم خصوصی
- [ ] cookie امن + CSRF و تست دامنه واقعی
- [ ] rate limit login/register/recommend/share/upload
- [ ] IDOR/RBAC/tenant isolation regression tests
- [ ] validation `max_length` و `extra=forbid`
- [ ] sanitization متن و خروجی AI
- [ ] محدودیت حجم/MIME/EXIF upload
- [ ] Security headers، CSP، CORS و TLS
- [ ] audit log، log redaction، secret rotation
- [ ] GDPR delete، retention، backup و restore test

## D. هوش مصنوعی و داده
- [ ] اجرای benchmark واقعی ۵۰ تصویر با provider نهایی
- [ ] گزارش precision/recall/confidence هر ویژگی
- [ ] human review و workflow رد/تأیید/ویرایش
- [ ] embeddings واقعی CLIP در Production
- [ ] عدم فعال‌شدن hash fallback در Production
- [ ] تست catalog حداقل ۵۰۰–۱۰۰۰ محصول و scale با ۱۰هزار رکورد
- [ ] نسخه‌بندی prompt، مدل، embedding و taxonomy
- [ ] feedback کاربر برای بهبود ranking

## E. محصول و UX
- [ ] جریان end-to-end صاحب‌خانه
- [ ] جریان end-to-end طراح و مشتری
- [ ] جریان end-to-end ادمین
- [ ] empty/error/loading/success state برای همه مسیرها
- [ ] RTL واقعی، keyboard، موبایل و screen reader
- [ ] board selector، collision/clearance و autosave
- [ ] explainability و soft paywall
- [ ] لینک فروشنده با وضعیت و آخرین بررسی

## F. یکپارچه‌سازی و عملیات
- [ ] payment request/callback/verify idempotent
- [ ] S3 signed/public URL و CDN cache policy
- [ ] email share با template و rate limit
- [ ] background queue برای extraction/link checker
- [ ] readiness/liveness، metrics، tracing و error tracking
- [ ] CI واقعی روی PR و dependency scan
- [ ] staging با domain و TLS
- [ ] rollback، migration، backup/restore و runbook

## G. کیفیت و فروش
- [ ] unit/integration/E2E و regression برای هر سه نقش
- [ ] حداقل ۲۸/۳۰ سناریوی recommender
- [ ] p95 < 2s با روش benchmark مستند
- [ ] Lighthouse ≥80 و LCP <3s
- [ ] accessibility audit
- [ ] smoke test پس از deploy
- [ ] demo video، screenshots و case study
- [ ] proposal با جدول mapping، timeline و milestone
- [ ] گزارش محدودیت‌های صادقانه mock/real
