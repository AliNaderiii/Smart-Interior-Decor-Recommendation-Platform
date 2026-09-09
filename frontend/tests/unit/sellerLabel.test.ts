/**
 * P4-ب-2 — the "buy from" label names the shop only when the host really is
 * that shop; everything else gets the neutral label (never a wrong brand).
 */
import { describe, expect, it } from "vitest";
import { sellerKind, sellerLabel } from "@/lib/sellerLabel";

describe("sellerKind", () => {
  it("recognises the three Iranian marketplaces by host, not by substring", () => {
    expect(sellerKind("https://www.digikala.com/product/dkp-1234567/")).toBe("digikala");
    expect(sellerKind("https://torob.com/p/abc/")).toBe("torob");
    expect(sellerKind("https://basalam.com/mobl-ara/product/24223620")).toBe("basalam");
    // a look-alike host must not borrow the brand
    expect(sellerKind("https://digikala.com.evil.example/product/1")).toBe("other");
    expect(sellerKind("https://example-seller.ir/?ref=basalam.com")).toBe("other");
  });

  it("is neutral for empty, relative or malformed links", () => {
    expect(sellerKind("")).toBe("other");
    expect(sellerKind(null)).toBe("other");
    expect(sellerKind("not a url")).toBe("other");
  });
});

describe("sellerLabel", () => {
  it("is locale-aware", () => {
    expect(sellerLabel("https://basalam.com/x/product/1", "fa")).toBe("خرید از باسلام");
    expect(sellerLabel("https://basalam.com/x/product/1", "en")).toBe("Buy on Basalam");
    expect(sellerLabel("https://shop.example.ir/p/1", "fa")).toBe("مشاهده فروشنده");
    expect(sellerLabel("https://shop.example.ir/p/1", "en")).toBe("View seller");
    expect(sellerLabel("https://www.digikala.com/product/dkp-1/", "fa")).toBe("خرید از دیجی‌کالا");
  });
});
