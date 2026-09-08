/**
 * ADR-016 — provenance and price freshness must be visible on the card face,
 * and the integrity helpers must parse the API's 409 body exactly.
 */
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { renderWithProviders } from "./renderWithProviders";
import { ProductCard } from "@/components/ProductCard";
import { daysSince, parseIntegrityCodes } from "@/lib/integrity";
import type { RecommendedProduct } from "@/lib/types";

function product(overrides: Partial<RecommendedProduct> = {}): RecommendedProduct {
  return {
    id: "p1",
    title: "Hand-knotted Tabriz rug",
    title_fa: "فرش دستباف تبریز",
    category: "rug",
    price_toman: 48_000_000,
    image_url: "https://cdn.example-seller.ir/rugs/tabriz.jpg",
    seller_link: "https://www.digikala.com/product/dkp-1234567/",
    seller_link_ok: true,
    colors: ["#8B0000"],
    styles: ["classic"],
    materials: ["fabric"],
    patterns: ["persian"],
    width_cm: 300,
    depth_cm: 200,
    height_cm: 1,
    description: "",
    final_score: 0.9,
    is_verified: true,
    source: "feed:example-seller",
    price_checked_at: new Date().toISOString(),
    integrity_ok: true,
    explanation: {
      style_match: 90, color_match: 80, budget_fit: 100, material_match: 70,
      pattern_match: 60, fit_match: 100, fit_reason: "fit_ok", matched_materials: [],
      summary: "",
    },
    ...overrides,
  };
}

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: typeof ResizeObserverStub }).ResizeObserver ??= ResizeObserverStub;

describe("ProductCard — ADR-016 trust badges", () => {
  it("shows no demo badge for a feed-sourced product", () => {
    renderWithProviders(<ProductCard product={product()} rank={0} />, { locale: "en", wrapper: MemoryRouter });
    expect(screen.queryByTestId("badge-demo-item")).toBeNull();
    expect(screen.getByTestId("price-freshness").textContent).toBe("Price checked today");
  });

  it("labels synthetic rows as demo items (en + fa)", () => {
    renderWithProviders(<ProductCard product={product({ source: "synthetic-demo" })} rank={0} />, {
      locale: "en", wrapper: MemoryRouter,
    });
    expect(screen.getByTestId("badge-demo-item").textContent).toBe("Demo item");
  });

  it("localises the demo badge in Persian", () => {
    renderWithProviders(<ProductCard product={product({ source: "perf" })} rank={0} />, {
      locale: "fa", wrapper: MemoryRouter,
    });
    expect(screen.getByTestId("badge-demo-item").textContent).toBe("نمونهٔ نمایشی");
  });

  it("says when a verified price was never confirmed with the seller", () => {
    renderWithProviders(<ProductCard product={product({ price_checked_at: null })} rank={0} />, {
      locale: "en", wrapper: MemoryRouter,
    });
    expect(screen.getByText("Price not yet confirmed with the seller")).toBeTruthy();
  });

  it("shows the age of the last price check in days", () => {
    const twelveDaysAgo = new Date(Date.now() - 12 * 86_400_000).toISOString();
    renderWithProviders(<ProductCard product={product({ price_checked_at: twelveDaysAgo })} rank={0} />, {
      locale: "en", wrapper: MemoryRouter,
    });
    expect(screen.getByTestId("price-freshness").textContent).toBe("Price checked 12 d ago");
  });

  it("renders no freshness line for unverified drafts (already labelled estimated)", () => {
    renderWithProviders(<ProductCard product={product({ is_verified: false })} rank={0} />, {
      locale: "en", wrapper: MemoryRouter,
    });
    expect(screen.queryByTestId("price-freshness")).toBeNull();
  });
});

describe("integrity helpers", () => {
  it("parses the codes out of the 409 body", () => {
    expect(
      parseIntegrityCodes(
        "catalog integrity failed [image_category_mismatch,material_implausible]: image_category_mismatch: …",
      ),
    ).toEqual(["image_category_mismatch", "material_implausible"]);
    expect(parseIntegrityCodes("Request failed with status 409")).toEqual([]);
    expect(parseIntegrityCodes("")).toEqual([]);
  });

  it("computes whole non-negative days", () => {
    const now = Date.UTC(2026, 8, 7, 12);
    expect(daysSince(new Date(now - 2.9 * 86_400_000).toISOString(), now)).toBe(2);
    expect(daysSince(new Date(now + 86_400_000).toISOString(), now)).toBe(0);
    expect(daysSince("not-a-date", now)).toBe(0);
  });
});
