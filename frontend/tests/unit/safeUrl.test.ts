/** Unit tests for the URL sanitiser used by every `href` in the SPA.
 *
 * Stage 1 (T-1.3): ported to Vitest (the runner this task wires into
 * `npm test`). The assertions are the same security contract as the
 * original node:test suite — every blocking case must block, every
 * legitimate link must survive, protocol-relative URLs resolve against
 * the page scheme (jsdom origin: http://localhost:3000).
 */
import { describe, expect, it } from "vitest";
import { safeUrl, safeImageUrl, isSafeUrl } from "@/lib/safeUrl";

describe("safeUrl", () => {
  it("blocks javascript: in every disguise", () => {
    const payloads = [
      "javascript:alert(1)",
      "JavaScript:alert(1)",
      "  javascript:alert(1)",
      "java\tscript:alert(1)",
      "java\nscript:alert(1)",
      "\u0000javascript:alert(1)",
      "jAvAsCrIpT:alert(document.domain)",
    ];
    for (const payload of payloads) {
      expect(safeUrl(payload), `not blocked: ${JSON.stringify(payload)}`).toBe("");
    }
  });

  it("blocks other executable and local schemes", () => {
    for (const payload of [
      "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
      "vbscript:msgbox(1)",
      "file:///etc/passwd",
      "blob:https://evil.example/1234",
      "about:blank",
    ]) {
      expect(safeUrl(payload), `not blocked: ${payload}`).toBe("");
    }
  });

  it("allows ordinary product links", () => {
    expect(safeUrl("https://www.digikala.com/product/dkp-1")).toBe(
      "https://www.digikala.com/product/dkp-1",
    );
    expect(safeUrl("http://shop.example.com/x")).toBe("http://shop.example.com/x");
    expect(safeUrl("mailto:sales@example.com")).toBe("mailto:sales@example.com");
  });

  it("allows in-app relative links unchanged", () => {
    expect(safeUrl("/share/abc123")).toBe("/share/abc123");
    expect(safeUrl("#section")).toBe("#section");
    expect(safeUrl("?page=2")).toBe("?page=2");
  });

  it("normalises protocol-relative URLs against the page scheme instead of trusting them", () => {
    // jsdom origin is http:// — protocol-relative must inherit http, never upgrade.
    expect(window.location.protocol).toBe("http:");
    expect(safeUrl("//evil.example/x")).toBe("http://evil.example/x");
  });

  it("returns an empty string for empty input", () => {
    expect(safeUrl("")).toBe("");
    expect(safeUrl(null)).toBe("");
    expect(safeUrl(undefined)).toBe("");
    expect(safeUrl("   ")).toBe("");
  });

  it("never throws on malformed input", () => {
    for (const payload of ["http://", "://x", "%%%", "h".repeat(10_000)]) {
      expect(() => safeUrl(payload)).not.toThrow();
    }
  });
});

describe("isSafeUrl", () => {
  it("mirrors safeUrl", () => {
    expect(isSafeUrl("https://example.com")).toBe(true);
    expect(isSafeUrl("javascript:alert(1)")).toBe(false);
  });
});

describe("safeImageUrl", () => {
  it("allows http(s) images and rejects everything else", () => {
    expect(safeImageUrl("https://cdn.example.com/a.png")).toBe(
      "https://cdn.example.com/a.png",
    );
    expect(safeImageUrl("data:image/svg+xml,<svg onload=alert(1)>")).toBe("");
    expect(safeImageUrl("mailto:a@b.com")).toBe("");
    expect(safeImageUrl("javascript:alert(1)")).toBe("");
  });
});
