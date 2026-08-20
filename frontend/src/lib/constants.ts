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
export const BUDGET_MIN = Math.min(...ranges.map((range) => range.min));
export const BUDGET_MAX = Math.max(...ranges.map((range) => range.max));
