/**
 * Label for the "buy from" link on a product card, derived from the seller URL.
 *
 * P4-ب-2: real catalog rows now come from several sellers (Basalam vendors,
 * a seller's own shop via CSV feed, Digikala affiliate later). The card should
 * name the shop when it can, and fall back to a neutral label — never to a
 * wrong marketplace name.
 */
export type SellerKind = "digikala" | "torob" | "basalam" | "other";

export function sellerKind(sellerLink: string | null | undefined): SellerKind {
  if (!sellerLink) return "other";
  let host = "";
  try {
    host = new URL(sellerLink).hostname.toLowerCase();
  } catch {
    return "other";
  }
  if (host === "digikala.com" || host.endsWith(".digikala.com")) return "digikala";
  if (host === "torob.com" || host.endsWith(".torob.com")) return "torob";
  if (host === "basalam.com" || host.endsWith(".basalam.com")) return "basalam";
  return "other";
}

const LABELS: Record<"fa" | "en", Record<SellerKind, string>> = {
  fa: {
    digikala: "خرید از دیجی‌کالا",
    torob: "مشاهده در ترب",
    basalam: "خرید از باسلام",
    other: "مشاهده فروشنده",
  },
  en: {
    digikala: "Buy on Digikala",
    torob: "View on Torob",
    basalam: "Buy on Basalam",
    other: "View seller",
  },
};

export function sellerLabel(sellerLink: string | null | undefined, locale: "fa" | "en"): string {
  return LABELS[locale][sellerKind(sellerLink)];
}
