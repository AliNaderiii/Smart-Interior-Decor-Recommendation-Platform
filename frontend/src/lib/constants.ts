/** Shared display helpers and dataset-backed taxonomy. */
import taxonomy from "@/assets/style_taxonomy.json";
import questionnaire from "@/assets/questionnaire.json";

export const STYLES = taxonomy.styles.map((style) => ({
  id: style.id,
  label: style.name_en,
  fa: style.name_fa,
  icon: style.icon,
  image: `${style.sample_image}?w=640&q=60&fm=webp`,
  description: style.description_fa,
}));

const materialStep = questionnaire.steps.find((step) => step.id === "material");
type MaterialOption = { id: string; label_en: string; label_fa: string; icon: string; subtypes: string[] };
export const MATERIALS = (("options" in (materialStep ?? {}) ? materialStep?.options : []) ?? []).map((item) => {
  const option = item as MaterialOption;
  return { id: option.id, label: option.label_en, fa: option.label_fa, icon: option.icon, subtypes: option.subtypes };
});

const colorStep = questionnaire.steps.find((step) => step.id === "color_palette");
type PaletteOption = { colors: string[] };
export const PALETTE_PRESETS = Array.from(new Set(
  (("options" in (colorStep ?? {}) ? colorStep?.options : []) ?? []).flatMap((item) => (item as PaletteOption).colors),
));

export const CATEGORY_LABELS: Record<string, string> = {
  sofa: "مبل",
  coffee_table: "میز جلومبلی",
  rug: "فرش",
  lighting: "روشنایی",
  chair: "صندلی",
  storage: "فضای نگهداری",
  decor: "دکور",
};

/** Persian price format with fa-IR digits: ۴۵٬۰۰۰٬۰۰۰ تومان */
const faNumber = new Intl.NumberFormat("fa-IR");
export function formatToman(value: number): string {
  return `${faNumber.format(value)} تومان`;
}

export function formatTomanLatin(value: number): string {
  return `${value.toLocaleString("en-US")} تومان`;
}

const budgetStep = questionnaire.steps.find((step) => step.id === "budget");
type BudgetRange = { min: number; max: number };
const ranges = (("ranges" in (budgetStep ?? {}) ? budgetStep?.ranges : []) ?? []) as BudgetRange[];
/** The quiz budget is the living-room TOTAL (ADR-019); the server splits it per category. */
export const BUDGET_MIN = Math.min(...ranges.map((range) => range.min));
export const BUDGET_MAX = Math.max(...ranges.map((range) => range.max));
/** Slider/number-input granularity, from the dataset so a real-price floor (500k) is reachable. */
export const BUDGET_STEP =
  (("slider_step" in (budgetStep ?? {}) ? Number(budgetStep?.slider_step) : 0) || 1_000_000);
/**
 * Default window offered before the user touches the control: every preset
 * except the top ("luxury") one — deliberately broad, because the first
 * result set should show the room and the user narrows from there; a narrow
 * default on a per-category split (ADR-019) would start with empty sections.
 */
const sortedRanges = [...ranges].sort((a, b) => a.min - b.min);
export const BUDGET_DEFAULT_MIN = BUDGET_MIN;
export const BUDGET_DEFAULT_MAX =
  sortedRanges.length >= 2 ? sortedRanges[sortedRanges.length - 2].max : BUDGET_MAX;
