/** Persian UI strings.
 *
 * Why a module and not a full i18n runtime: the product ships Persian-only for
 * the Iranian market (prices in Toman, Digikala seller links). A runtime like
 * i18next would add ~40 KB and a provider tree for a single locale. When a
 * second locale is actually required, swap this object for the loader — every
 * call site already goes through `t`, so nothing else changes.
 */
export const fa = {
  brand: "اسمارت دکور",

  nav: {
    quiz: "آزمون سبک",
    recommendations: "پیشنهادها",
    moodboards: "مودبورد",
    floorplan: "نقشه چیدمان",
    shoppingList: "فهرست خرید",
    search: "جست‌وجو",
    logout: "خروج",
    login: "ورود",
    register: "ثبت‌نام",
    lightMode: "حالت روشن",
    darkMode: "حالت تیره",
    openSearch: "باز کردن جست‌وجو",
    designerDashboard: "داشبورد طراح",
    adminProducts: "مدیریت محصولات",
    adminUsers: "مدیریت کاربران",
  },

  common: {
    next: "بعدی",
    back: "قبلی",
    continue: "شروع کنیم",
    save: "ذخیره",
    cancel: "انصراف",
    delete: "حذف",
    edit: "ویرایش",
    close: "بستن",
    loading: "در حال بارگذاری…",
    retry: "تلاش دوباره",
    optional: "اختیاری",
    toman: "تومان",
  },

  home: {
    eyebrow: "اتاق نشیمن · ایران",
    title: "نشیمن رؤیایی شما،",
    titleAccent: "با هوش مصنوعی",
    subtitle:
      "یک آزمون سبک دو دقیقه‌ای پاسخ دهید. برای هر دسته، محصولات رتبه‌بندی‌شده با امتیاز شفافِ «چرا این؟» دریافت کنید؛ به‌همراه مودبورد قابل ویرایش، نقشه چیدمان با ابعاد واقعی و فهرست خرید معتبر.",
    cta: "شروع رایگان",
    ctaNote: "رایگان · بدون نیاز به کارت بانکی · قیمت‌ها به تومان",
    howItWorks: "چطور کار می‌کند",
    steps: [
      {
        title: "فضایتان را معرفی کنید",
        body: "ابعاد واقعی اتاق، بودجه و سبک‌هایی که دوست دارید. دو دقیقه، بدون دیوار ثبت‌نام.",
      },
      {
        title: "«چرا»، نه فقط «چه»",
        body: "هر محصول امتیاز تفکیک‌شده دارد: تناسب سبک، هماهنگی رنگ، جا شدن در بودجه و تناسب با اتاق شما.",
      },
      {
        title: "بچینید، بسنجید، بخرید",
        body: "انتخاب‌ها را روی مودبورد بگذارید، مسیرهای عبور را در نقشه بسنجید، سپس از لینک‌های معتبر فروشندگان خرید کنید.",
      },
    ],
    stylesTitle: "شش سبک، یک آزمون",
    stylesSubtitle:
      "اتاق‌هایی را انتخاب کنید که به دلتان می‌نشیند — مدل سلیقه شما را از تصویر می‌فهمد، نه از صفت‌ها.",
  },

  quiz: {
    title: "طراحی نشیمن شما",
    stepOf: (current: number, total: number) =>
      `مرحله ${toFa(current)} از ${toFa(total)}`,
    stepTitles: [
      "چه سبکی دوست داری؟",
      "چه پالت رنگی؟",
      "اتاقت چقدر بزرگه؟",
      "بودجه‌ات چقدره؟",
      "چه متریالی دوست داری؟",
    ],
    roomWidth: "عرض اتاق (سانتی‌متر)",
    roomLength: "طول اتاق (سانتی‌متر)",
    roomHint: (area: string) =>
      `≈ ${area} متر مربع — طبق قانون طلایی، برای راه عبور حداقل ۷۶ سانتی‌متر نیاز داریم.`,
    totalBudget: "بودجه کل",
    min: "حداقل (تومان)",
    max: "حداکثر (تومان)",
    materialsQuestion: "چه متریالی دوست داری؟",
    colorHint: "پالت رنگی نزدیک به حس دلخواهت را انتخاب کن.",
    custom: "دلخواه",
    submit: "پیشنهادها را نشانم بده",
    progressLabel: (current: number, total: number) =>
      `پیشرفت آزمون: مرحله ${toFa(current)} از ${toFa(total)}`,
  },

  recommendations: {
    title: "پیشنهادهای شما",
    subtitle:
      "رتبه‌بندی بر اساس تناسب سبک، رنگ، بودجه و متریال. با 👍/👎 مجموعه بعدی را دقیق‌تر کنید.",
    /** Three distinct states — conflating them was the "No matches" bug. */
    noQuizTitle: "هنوز آزمون سبک را کامل نکرده‌اید",
    noQuizHint:
      "برای دیدن پیشنهادهای شخصی‌سازی‌شده، ابتدا آزمون دو دقیقه‌ای سبک را کامل کنید.",
    noQuizCta: "شروع آزمون سبک",
    emptyTitle: "با این فیلترها محصولی پیدا نشد",
    emptyHint:
      "هیچ محصولی همه شرط‌ها را پاس نکرد. معمولاً بازتر کردن بازه بودجه بیشترین گزینه را برمی‌گرداند.",
    emptyCta: "ویرایش آزمون",
    errorTitle: "بارگذاری پیشنهادها ممکن نشد",
    errorHint: "ارتباط با سرور برقرار نشد. لطفاً دوباره تلاش کنید.",
    scoreStyle: "تناسب سبک",
    scoreColor: "هماهنگی رنگ",
    scoreBudget: "تناسب بودجه",
    scoreMaterial: "تناسب متریال",
  },

  moodboards: {
    title: "مودبوردها",
    emptyTitle: "هنوز مودبوردی نساخته‌اید",
    emptyHint:
      "از صفحه پیشنهادها محصولات مورد علاقه‌تان را انتخاب کنید تا اولین مودبورد ساخته شود.",
    emptyCta: "رفتن به پیشنهادها",
  },

  floorplan: {
    title: "نقشه چیدمان",
    subtitle:
      "ابعاد واقعی، هر واحد ۱ سانتی‌متر. مبلمان را بکشید و بچینید — مسیرهای عبور کمتر از ۷۶ سانتی‌متر علامت می‌خورند.",
    exportPng: "خروجی تصویر",
    roomDimensions: "ابعاد اتاق",
    width: "عرض (سانتی‌متر)",
    length: "طول (سانتی‌متر)",
    addFromMoodboard: "افزودن از مودبورد",
    addFromMoodboardHint:
      "ابتدا یک مودبورد بسازید — محصولاتش با ابعاد واقعی اینجا ظاهر می‌شوند.",
    footprint: (w: string, l: string, used: string, total: string, pct: string) =>
      `${w}×${l} سانتی‌متر · اشغال ${used} از ${total} متر مربع (${pct}٪)`,
  },

  shoppingList: {
    title: "فهرست خرید",
    emptyTitle: "فهرست خرید خالی است",
    emptyHint: "از مودبورد محصولات را اضافه کنید تا اینجا فهرست شوند.",
    total: "جمع کل",
  },

  auth: {
    loginTitle: "ورود",
    registerTitle: "ساخت حساب",
    email: "ایمیل",
    password: "رمز عبور",
    fullName: "نام و نام خانوادگی",
    loginCta: "ورود",
    registerCta: "ثبت‌نام",
    noAccount: "حساب ندارید؟",
    hasAccount: "قبلاً ثبت‌نام کرده‌اید؟",
    passwordHint: "حداقل ۸ کاراکتر",
  },

  errors: {
    generic: "خطایی رخ داد. لطفاً دوباره تلاش کنید.",
    network: "ارتباط با سرور برقرار نشد.",
    unauthorized: "برای ادامه باید وارد شوید.",
    forbidden: "به این بخش دسترسی ندارید.",
    /** Render Free sleeps after inactivity; the first request pays the wake-up. */
    coldStart: "سرور در حال بیدار شدن است… (تا ۳۰ ثانیه)",
  },
} as const;

/** Latin digits -> Persian digits. */
export function toFa(input: number | string): string {
  return String(input).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
}

/** Toman amount with Persian digits and thousands separators. */
export function formatToman(amount: number): string {
  return toFa(new Intl.NumberFormat("en-US").format(amount));
}

export const t = fa;
