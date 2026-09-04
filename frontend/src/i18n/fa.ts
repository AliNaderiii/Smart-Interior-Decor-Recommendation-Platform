/** Persian UI strings — the reference catalogue.
 *
 * Persian is the source of truth: its shape is exported as `Dict`, and `en.ts`
 * is typed against it, so a missing or misspelled English key fails the build
 * instead of leaking Persian into an English page.
 *
 * Why a hand-rolled catalogue rather than i18next: two static locales need a
 * lookup table, not a 40 KB runtime with plural rules and lazy namespaces.
 * Every call site goes through `useT()`, so swapping in a real runtime later
 * touches this folder only.
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
    adminSubscriptions: "اشتراک‌ها",
    language: "زبان",
    skipToContent: "پرش به محتوا",
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
    percent: "٪",
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
    explainTitle: "هر پیشنهاد، دلیل دارد",
    explainBody:
      "به‌جای فهرست بی‌توضیح، هر محصول با امتیاز تفکیک‌شده می‌آید تا بدانید چرا انتخاب شده و کجا با سلیقه‌تان فاصله دارد.",
    sampleProduct: "مبل مدرن — چرم عسلی",
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
    stylesHint:
      "اتاق‌هایی را انتخاب کن که به دلت می‌نشیند. سبکت را از انتخاب‌هایت می‌فهمیم — لازم نیست اسمش را بدانی.",
    custom: "دلخواه",
    submit: "پیشنهادها را نشانم بده",
    submitting: "در حال یافتن گزینه‌ها…",
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
    palette: "پالت",
    addToMoodboard: "افزودن به مودبورد",
    added: "افزوده شد ✓",
    aiNotice: "استخراج‌شده با هوش مصنوعی از صفحه فروشنده — پیش از خرید تأیید کنید.",
    proLocked: "با نسخه Pro همه گزینه‌ها را ببینید",
    verifiedPrice: "قیمت تأییدشده",
    estimatedPrice: "قیمت تخمینی",
    whyMatched: (title: string, pct: number) =>
      `چرا ${title} پیشنهاد شد: ${pct} درصد تطابق کلی`,
    moreLike: (title: string) => `بیشتر شبیه ${title}`,
    fewerLike: (title: string) => `کمتر شبیه ${title}`,
  },

  moodboards: {
    title: "مودبوردها",
    emptyTitle: "هنوز مودبوردی نساخته‌اید",
    emptyHint:
      "از صفحه پیشنهادها محصولات مورد علاقه‌تان را انتخاب کنید تا اولین مودبورد ساخته شود.",
    emptyCta: "رفتن به پیشنهادها",
    subtitle: "محصولاتی که پسندیده‌اید را در بردی بچینید که بتوانید به اشتراک بگذارید یا خرید کنید.",
    defaultName: "نشیمن من",
    created: "مودبورد ساخته شد.",
    createFailed: "ساخت مودبورد ممکن نشد.",
    deleted: "مودبورد حذف شد.",
    deleteFailed: "حذف مودبورد ممکن نشد.",
    creating: "در حال ساخت…",
    createCta: "ساخت مودبورد",
    loadFailed: "بارگذاری مودبوردها ممکن نشد.",
    deleting: "در حال حذف…",
    confirmDelete: "تأیید حذف",
  },

  floorplan: {
    title: "نقشه چیدمان",
    subtitle:
      "ابعاد واقعی، هر واحد ۱ سانتی‌متر. مبلمان را بکشید و بچینید — مسیرهای عبور کمتر از ۷۶ سانتی‌متر علامت می‌خورند.",
    exportPng: "خروجی تصویر",
    exporting: "در حال ذخیره…",
    exported: "نقشه چیدمان به‌صورت تصویر ذخیره شد.",
    roomDimensions: "ابعاد اتاق",
    width: "عرض (سانتی‌متر)",
    length: "طول (سانتی‌متر)",
    addFromMoodboard: "افزودن از مودبورد",
    addFromMoodboardHint:
      "ابتدا یک مودبورد بسازید — محصولاتش با ابعاد واقعی اینجا ظاهر می‌شوند.",
  },

  shoppingList: {
    title: "فهرست خرید",
    emptyTitle: "فهرست خرید خالی است",
    emptyHint: "از مودبورد محصولات را اضافه کنید تا اینجا فهرست شوند.",
    total: "جمع کل",
    copied: "فهرست خرید در کلیپ‌بورد کپی شد.",
    clipboardBlocked: "مرورگر اجازه‌ی دسترسی به کلیپ‌بورد نداد.",
    copyList: "کپی فهرست خرید",
    loadFailed: "بارگذاری فهرست خرید ممکن نشد.",
    nothingAdded: "هنوز چیزی اضافه نشده",
    createBoardFirst: "ابتدا یک مودبورد بسازید",
    goToMoodboards: "رفتن به مودبوردها",
    browseRecommendations: "مرور پیشنهادها",
    hintFromBoard: "یک مودبورد را باز کنید و «افزودن همه به فهرست خرید» را بزنید تا هرچه می‌خواهید بخرید جمع شود.",
    hintNoBoard: "فهرست خرید از روی مودبورد ساخته می‌شود. محصولات موردعلاقه‌تان را انتخاب و در یک برد ذخیره کنید.",
    linkVerified: "لینک تأییدشده",
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
    welcomeBack: "خوش آمدید",
    loginSubtitle: "برای ادامه‌ی طراحی نشیمن‌تان وارد شوید.",
    registerSubtitle: "برای شروع، یک حساب رایگان بسازید.",
    createOne: "یک حساب بسازید",
    signInHere: "وارد شوید",
    signingIn: "در حال ورود…",
    creating: "در حال ساخت حساب…",
    loginFailed: "ورود ناموفق بود.",
    registerFailed: "ثبت‌نام ناموفق بود.",
    invalidEmail: "ایمیل معتبر وارد کنید",
    minChars: "حداقل ۸ کاراکتر",
    enterName: "نام خود را وارد کنید",
    registerHeading: "حساب خود را بسازید",
    iAmA: "من یک…",
    homeowner: "صاحب‌خانه",
    designer: "طراح داخلی",
  },

  cinematic: {
    title: "قدم بزنید داخل خانه",
    body:
      "با اسکرول، دوربین از بیرون ساختمان وارد نشیمن می‌شود و از کنار مبل، فرش، تابلوها و چراغ عبور می‌کند. همه‌چیز با ابعاد واقعی مدل شده — همان اندازه‌هایی که در پیشنهادها می‌بینید.",
    scrollHint: "برای حرکت دوربین اسکرول کنید",
    loading: "در حال آماده‌سازی صحنه سه‌بعدی…",
    staticNotice:
      "نمای سه‌بعدی روی این دستگاه غیرفعال است تا سرعت سایت حفظ شود.",
  },

  errors: {
    generic: "خطایی رخ داد. لطفاً دوباره تلاش کنید.",
    network: "ارتباط با سرور برقرار نشد.",
    unauthorized: "برای ادامه باید وارد شوید.",
    forbidden: "به این بخش دسترسی ندارید.",
    /** Render Free sleeps after inactivity; the first request pays the wake-up. */
    coldStart: "سرور در حال بیدار شدن است… (تا ۳۰ ثانیه)",
  },
};

/** The catalogue shape every locale must satisfy. */
export type Dict = typeof fa;

/** Latin digits -> Persian digits. */
export function toFa(input: number | string): string {
  return String(input).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
}

/** Toman amount with Persian digits and thousands separators. */
export function formatToman(amount: number): string {
  return toFa(new Intl.NumberFormat("en-US").format(amount));
}

export const t = fa;
