/** English UI strings.
 *
 * Typed as `Dict` (the shape of the Persian catalogue), so omitting or
 * misspelling a key is a compile error rather than a string that silently
 * renders as Persian inside an English page — the exact class of defect the
 * user reported after the Persian-only pass.
 */
import type { Dict } from "./fa";

export const en: Dict = {
  brand: "Smart Decor",

  nav: {
    quiz: "Style Quiz",
    recommendations: "Recommendations",
    moodboards: "Moodboards",
    floorplan: "Floorplan",
    shoppingList: "Shopping List",
    search: "Search",
    logout: "Log out",
    login: "Sign in",
    register: "Sign up",
    lightMode: "Light mode",
    darkMode: "Dark mode",
    openSearch: "Open search",
    designerDashboard: "Projects",
    adminProducts: "Products",
    adminUsers: "Users",
    adminSubscriptions: "Subscriptions",
    language: "Language",
    skipToContent: "Skip to content",
  },

  common: {
    next: "Next",
    back: "Back",
    continue: "Continue",
    save: "Save",
    cancel: "Cancel",
    delete: "Delete",
    edit: "Edit",
    close: "Close",
    loading: "Preparing the walkthrough…",
    retry: "Try again",
    optional: "optional",
    toman: "Toman",
    percent: "%",
  },

  home: {
    eyebrow: "Living room · Iran",
    title: "Your dream living room,",
    titleAccent: "matched by AI.",
    subtitle:
      "Answer a two-minute style quiz. Get ranked products per category with transparent “why this” scores, an editable moodboard, a real-dimension floorplan and a validated shopping list.",
    cta: "Start free",
    ctaNote: "Free to try · No credit card · Prices in Toman",
    howItWorks: "How it works",
    steps: [
      {
        title: "Tell us your space",
        body: "Real dimensions, your budget, and the styles you are drawn to. Two minutes, no account walls.",
      },
      {
        title: "See why, not just what",
        body: "Every product carries its score breakdown — style fit, colour harmony, budget and how it fits your room.",
      },
      {
        title: "Arrange, check, buy",
        body: "Drop picks onto a moodboard, verify walkways on the floorplan, then shop from validated retailer links.",
      },
    ],
    stylesTitle: "Six styles, one quiz",
    stylesSubtitle:
      "Pick the rooms you react to — the model infers your taste from images, not adjectives.",
    explainTitle: "Every recommendation has a reason",
    explainBody:
      "Instead of an unexplained list, each product arrives with a score breakdown, so you know why it was chosen and where it diverges from your taste.",
    sampleProduct: "Modern Sofa — Cognac Leather",
  },

  quiz: {
    title: "Design your living room",
    stepOf: (current: number, total: number) => `Step ${current} of ${total}`,
    stepTitles: [
      "What style do you love?",
      "Which colour palette?",
      "How big is your room?",
      "What is your budget?",
      "Which materials do you love?",
    ],
    roomWidth: "Room width (cm)",
    roomLength: "Room length (cm)",
    roomHint: (area: string) =>
      `≈ ${area} m² — the golden rule needs at least 76 cm of walkway.`,
    totalBudget: "Total budget",
    min: "Minimum (Toman)",
    max: "Maximum (Toman)",
    materialsQuestion: "Which materials do you love?",
    colorHint: "Pick the palette closest to the mood you want.",
    stylesHint:
      "Pick the rooms you are drawn to. We infer your style from what you choose — you never have to name it.",
    custom: "Custom",
    submit: "Get my recommendations",
    submitting: "Finding matches…",
    progressLabel: (current: number, total: number) =>
      `Quiz progress: step ${current} of ${total}`,
  },

  recommendations: {
    title: "Your recommendations",
    subtitle:
      "Ranked by style, colour, budget and material fit. Use 👍/👎 to tune the next set.",
    noQuizTitle: "You have not taken the style quiz yet",
    noQuizHint:
      "Complete the two-minute style quiz first to see personalised recommendations.",
    noQuizCta: "Start the style quiz",
    emptyTitle: "No matches with these filters",
    emptyHint:
      "Nothing cleared every condition. Widening the budget range usually brings back the most options.",
    emptyCta: "Adjust your quiz",
    errorTitle: "Could not load recommendations",
    errorHint: "The server could not be reached. Please try again.",
    scoreStyle: "Style fit",
    scoreColor: "Colour harmony",
    scoreBudget: "Budget fit",
    scoreMaterial: "Material fit",
    palette: "Palette",
    addToMoodboard: "Add to moodboard",
    added: "Added ✓",
    aiNotice: "Extracted by AI from the retailer page — confirm before buying.",
    proLocked: "Unlock the full set with Pro",
    verifiedPrice: "Verified price",
    estimatedPrice: "Estimated price",
    whyMatched: (title: string, pct: number) =>
      `Why we matched ${title}: ${pct} percent overall`,
    moreLike: (title: string) => `More like ${title}`,
    fewerLike: (title: string) => `Fewer like ${title}`,
  },

  moodboards: {
    title: "Moodboards",
    emptyTitle: "No moodboards yet",
    emptyHint:
      "Pick products you like on the recommendations page to create your first moodboard.",
    emptyCta: "Go to recommendations",
    subtitle: "Arrange the products you liked into a board you can share or shop.",
    defaultName: "My Living Room",
    created: "Moodboard created.",
    createFailed: "Could not create the moodboard.",
    deleted: "Moodboard deleted.",
    deleteFailed: "Could not delete the moodboard.",
    creating: "Creating…",
    createCta: "Create moodboard",
    loadFailed: "Could not load your moodboards.",
    deleting: "Deleting…",
    confirmDelete: "Confirm delete",
  },

  floorplan: {
    title: "Floorplan",
    subtitle:
      "Real dimensions, 1 unit = 1 cm. Drag furniture to arrange the room — walkways under 76 cm are flagged.",
    exportPng: "Export PNG",
    exporting: "Exporting…",
    exported: "Floorplan exported as an image.",
    roomDimensions: "Room dimensions",
    width: "Width (cm)",
    length: "Length (cm)",
    addFromMoodboard: "Add from your moodboard",
    addFromMoodboardHint:
      "Create a moodboard first — its products appear here with real dimensions.",
  },

  shoppingList: {
    title: "Shopping list",
    emptyTitle: "Your shopping list is empty",
    emptyHint: "Add products from a moodboard to list them here.",
    total: "Total",
    copied: "Shopping list copied to clipboard.",
    clipboardBlocked: "Clipboard blocked by your browser.",
    copyList: "Copy shopping list",
    loadFailed: "Could not load your shopping list.",
    nothingAdded: "Nothing added yet",
    createBoardFirst: "Create a moodboard first",
    goToMoodboards: "Go to moodboards",
    browseRecommendations: "Browse recommendations",
    hintFromBoard: "Open a moodboard and choose “Add all to shopping list” to collect everything you want to buy.",
    hintNoBoard: "Your shopping list is built from a moodboard. Pick products you like and save them to a board.",
    linkVerified: "Link verified",
    unavailable: "Unavailable",
    sharedPlan: "Shared room plan",
  },

  auth: {
    loginTitle: "Sign in",
    registerTitle: "Create account",
    email: "Email",
    password: "Password",
    fullName: "Full name",
    loginCta: "Sign in",
    registerCta: "Sign up",
    noAccount: "No account?",
    hasAccount: "Already registered?",
    passwordHint: "At least 8 characters",
    welcomeBack: "Welcome back",
    loginSubtitle: "Sign in to continue designing your living room.",
    registerSubtitle: "Create a free account to get started.",
    createOne: "Create one",
    signInHere: "Sign in",
    signingIn: "Signing in…",
    creating: "Creating…",
    loginFailed: "Login failed.",
    registerFailed: "Registration failed.",
    invalidEmail: "Enter a valid email",
    minChars: "At least 8 characters",
    enterName: "Enter your name",
    registerHeading: "Create your account",
    iAmA: "I am a…",
    homeowner: "Homeowner",
    designer: "Interior Designer",
  },

  cinematic: {
    title: "Step inside the room",
    captions: [
      "We start outside — a modern home at dusk.",
      "Approaching the entrance, warm light behind the glass.",
      "Stepping inside: open plan, high ceiling, timber stair.",
      "The living room — sofa, hand-knotted rug, walnut table.",
      "Gliding past the sofa; texture, brass, tea on the table.",
      "And finally, the gallery wall and bookshelf.",
    ],
    scrollHint: "Scroll to move the camera",
    loading: "Preparing the 3D scene…",
    staticNotice:
      "Shown as a still image because your device requests reduced motion.",
  },

  gallery: {
    title: "What you actually get",
    subtitle:
      "These are real platform outputs: a room furnished from catalogue products, with Toman prices and verified seller links.",
    before: "Before",
    after: "After",
    sliderLabel: "Compare before and after",
    baTitle: "From an empty room to a finished layout",
    baBody:
      "Drag the handle. The right side is the same room furnished by our engine — every piece is a real product with its own match score.",
    baHint: "Drag the handle in the middle to compare",
    stylesTitle: "Six styles, different outcomes",
    stylesBody:
      "For each style the engine picks a different combination of furniture, colour and material.",
    styleCards: [
      {
        title: "Modern",
        body: "Clean lines, neutral palette, glossy materials. Suits compact urban spaces.",
      },
      {
        title: "Scandinavian",
        body: "Light wood, soft textures, plenty of daylight. Calm and visually open.",
      },
      {
        title: "Bohemian",
        body: "Layered rugs and textiles, warm colours, handmade pieces and plants.",
      },
      {
        title: "Classic",
        body: "Velvet, hand-knotted carpet, walnut and brass. For formal living rooms.",
      },
    ],
  },

  proof: {
    title: "What people say",
    subtitle: "Three different roles, three different uses.",
    items: [
      {
        quote:
          "Before buying a sofa I compared three combinations and saw which one worked with our existing carpet. I did not waste the money.",
        role: "Homeowner, Tehran",
      },
      {
        quote:
          "I can prepare several directions for a client in minutes instead of spending two days building moodboards.",
        role: "Interior designer",
      },
      {
        quote:
          "The score breakdown is the important part — I can explain to a client exactly why a piece was recommended.",
        role: "Styling consultant",
      },
    ],
  },

  faq: {
    title: "Frequently asked questions",
    subtitle: "Everything worth knowing before you start.",
    items: [
      {
        q: "Are the prices and seller links real?",
        a: "Yes. Every product carries a Toman price and a seller link, and link health is checked automatically — dead links are quarantined out of the results.",
      },
      {
        q: "How is the match score calculated?",
        a: "Four components: style fit, colour harmony, budget fit and material fit. Each is shown separately so you can see where a product diverges from your taste.",
      },
      {
        q: "Do I need to upload a photo of my room?",
        a: "No. The two-minute style quiz is enough: style, colour palette, room dimensions, budget and preferred materials.",
      },
      {
        q: "Do I need design experience?",
        a: "No. Just pick the rooms you are drawn to — your style is inferred from what you choose.",
      },
      {
        q: "Why do you ask for room dimensions?",
        a: "The floorplan is built at real scale and walkways under 76 cm are flagged, so furniture that will not physically fit is never recommended.",
      },
      {
        q: "Is my data stored?",
        a: "Only your quiz answers and moodboards. Card details are never stored, and full account deletion is available at any time.",
      },
    ],
  },

  errors: {
    generic: "Something went wrong. Please try again.",
    network: "The server could not be reached.",
    unauthorized: "You must sign in to continue.",
    forbidden: "You do not have access to this area.",
    coldStart: "The server is waking up… (up to 30 seconds)",
  },
};
