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
    loading: "Loading…",
    retry: "Try again",
    optional: "optional",
    toman: "Toman",
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
  },

  moodboards: {
    title: "Moodboards",
    emptyTitle: "No moodboards yet",
    emptyHint:
      "Pick products you like on the recommendations page to create your first moodboard.",
    emptyCta: "Go to recommendations",
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
  },

  errors: {
    generic: "Something went wrong. Please try again.",
    network: "The server could not be reached.",
    unauthorized: "You must sign in to continue.",
    forbidden: "You do not have access to this area.",
    coldStart: "The server is waking up… (up to 30 seconds)",
  },
};
