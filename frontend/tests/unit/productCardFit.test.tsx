/**
 * ADR-012 — the dimensional-fit signal must reach the user in two places:
 * as a sixth row in the "why we matched" breakdown, and as a badge on the
 * card face for the three actionable states (won't fit / tight / small).
 * A comfortable fit deliberately shows no badge.
 */
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { renderWithProviders } from "./renderWithProviders";
import { ProductCard } from "@/components/ProductCard";
import type { RecommendedProduct } from "@/lib/types";

function product(overrides: Partial<RecommendedProduct["explanation"]> = {}): RecommendedProduct {
  return {
    id: "p1",
    title: "Compact Modern Sofa",
    title_fa: "مبل مدرن جمع‌وجور",
    category: "sofa",
    price_toman: 48_500_000,
    image_url: "https://images.example.com/sofa.jpg",
    seller_link: "https://example.com/p/1",
    seller_link_ok: true,
    colors: ["#2E2E2E"],
    styles: ["modern"],
    materials: ["fabric"],
    patterns: ["solid"],
    width_cm: 220,
    depth_cm: 95,
    height_cm: 85,
    description: "",
    final_score: 0.83,
    is_verified: true,
    explanation: {
      style_match: 90,
      color_match: 80,
      budget_fit: 100,
      material_match: 70,
      pattern_match: 60,
      fit_match: 100,
      fit_reason: "fit_ok",
      matched_materials: [],
      summary: "Style Match 90% | Color Match 80% | Budget Fit 100%",
      ...overrides,
    },
  };
}

// Radix HoverCard measures its content with ResizeObserver, which jsdom lacks.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: typeof ResizeObserverStub }).ResizeObserver ??= ResizeObserverStub;

describe("ProductCard — ADR-012 room fit", () => {
  it("shows no badge when the piece fits comfortably", () => {
    renderWithProviders(<ProductCard product={product()} rank={0} />, { locale: "en", wrapper: MemoryRouter });
    expect(screen.queryByTestId("fit-badge")).toBeNull();
  });

  it.each([
    ["fit_too_big", "Won't fit"],
    ["fit_too_tall", "Won't fit"],
    ["fit_tight", "Tight fit"],
    ["fit_too_small", "Small for room"],
  ] as const)("badges %s as “%s” (en)", (reason, label) => {
    renderWithProviders(
      <ProductCard product={product({ fit_reason: reason, fit_match: 5 })} rank={0} />,
      { locale: "en", wrapper: MemoryRouter },
    );
    const badge = screen.getByTestId("fit-badge");
    expect(badge.getAttribute("data-fit")).toBe(reason);
    expect(badge.textContent).toContain(label);
  });

  it("localises the badge in Persian", () => {
    renderWithProviders(
      <ProductCard product={product({ fit_reason: "fit_too_big", fit_match: 5 })} rank={0} />,
      { locale: "fa", wrapper: MemoryRouter },
    );
    expect(screen.getByTestId("fit-badge").textContent).toContain("جا نمی‌شود");
  });

  it("exposes the fit row in the breakdown with the localised reason and dimensions", async () => {
    renderWithProviders(
      <ProductCard product={product({ fit_reason: "fit_tight", fit_match: 55 })} rank={0} />,
      { locale: "en", wrapper: MemoryRouter },
    );
    await userEvent.click(screen.getByTestId("match-chip"));
    const row = await screen.findByTestId("match-breakdown");
    const fit = row.querySelector('[data-testid="match-signal"][data-signal="fit"]');
    expect(fit).not.toBeNull();
    const text = fit!.textContent ?? "";
    expect(text).toContain("Room fit");
    expect(text).toContain("55%");
    expect(text).toContain("Tight for your room");
    expect(text).toContain("220 × 95 cm");
  });
});
