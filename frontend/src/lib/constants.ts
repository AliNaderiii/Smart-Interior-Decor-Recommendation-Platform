/** Centralized display strings + taxonomy. i18n-ready: swap this module
 *  for a locale-keyed dictionary when RTL/Persian UI ships (post-MVP). */

export const STYLES = [
  { id: "modern", label: "Modern", fa: "مدرن", image: "https://images.unsplash.com/photo-1586023492125-27b2c045efd7?w=640&q=60&fm=webp" },
  { id: "scandinavian", label: "Scandinavian", fa: "اسکاندیناوی", image: "https://images.unsplash.com/photo-1583847268964-b28dc8f51f92?w=640&q=60&fm=webp" },
  { id: "industrial", label: "Industrial", fa: "صنعتی", image: "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=640&q=60&fm=webp" },
  { id: "boho", label: "Boho", fa: "بوهو", image: "https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?w=640&q=60&fm=webp" },
  { id: "minimal", label: "Minimal", fa: "مینیمال", image: "https://images.unsplash.com/photo-1449247709967-d4461a6a6103?w=640&q=60&fm=webp" },
  { id: "classic", label: "Classic", fa: "کلاسیک", image: "https://images.unsplash.com/photo-1519710164239-da123dc03ef4?w=640&q=60&fm=webp" },
] as const;

export const MATERIALS = [
  { id: "wood", label: "Wood", fa: "چوب" },
  { id: "metal", label: "Metal", fa: "فلز" },
  { id: "fabric", label: "Fabric", fa: "پارچه" },
  { id: "leather", label: "Leather", fa: "چرم" },
  { id: "glass", label: "Glass", fa: "شیشه" },
  { id: "rattan", label: "Rattan", fa: "حصیری" },
] as const;

export const PALETTE_PRESETS = [
  "#2E2E2E", "#FFFFFF", "#F2E8D5", "#C8A165", "#5D4037",
  "#C1633F", "#4C6444", "#3B5B7A", "#7B1E26", "#D4AF37",
  "#9E9E9E", "#EDEDED",
];

export const CATEGORY_LABELS: Record<string, string> = {
  sofa: "Sofa",
  coffee_table: "Coffee Table",
  rug: "Rug",
  lighting: "Lighting",
  armchair: "Armchair",
  tv_stand: "TV Stand",
  bookshelf: "Bookshelf",
  curtain: "Curtains",
};

/** Persian price format with fa-IR digits: ۴۵٬۰۰۰٬۰۰۰ تومان */
const faNumber = new Intl.NumberFormat("fa-IR");
export function formatToman(value: number): string {
  return `${faNumber.format(value)} تومان`;
}

/** Latin-digit variant for admin tables / logs where fa digits hinder scanning. */
export function formatTomanLatin(value: number): string {
  return `${value.toLocaleString("en-US")} تومان`;
}

export const BUDGET_MIN = 1_000_000;
export const BUDGET_MAX = 500_000_000;
