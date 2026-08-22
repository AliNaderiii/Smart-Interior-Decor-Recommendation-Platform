/** Unit tests for the URL sanitiser used by every `href` in the SPA.
 *
 * Run (no new dependency, no package.json change — Node 22 strips the types):
 *
 *     cd frontend
 *     node --experimental-strip-types --test tests/unit/safeUrl.test.ts
 *
 * The repository has no frontend unit-test runner today. Adding vitest would
 * mean editing `package.json` and the CI workflow, which Master Prompt 03 puts
 * outside this stage's file ownership — raised as an integration request
 * instead (IR-SEC-004). These tests therefore run standalone.
 */
import assert from "node:assert/strict";
import { before, describe, it } from "node:test";

// `safeUrl` resolves relative URLs against the page origin.
(globalThis as unknown as { window: { location: { origin: string } } }).window = {
  location: { origin: "https://app.smartdecor.example" },
};

type SafeUrlModule = typeof import("../../src/lib/safeUrl.ts");
let safeUrl: SafeUrlModule["safeUrl"];
let isSafeUrl: SafeUrlModule["isSafeUrl"];
let safeImageUrl: SafeUrlModule["safeImageUrl"];

before(async () => {
  const mod = await import("../../src/lib/safeUrl.ts");
  safeUrl = mod.safeUrl;
  isSafeUrl = mod.isSafeUrl;
  safeImageUrl = mod.safeImageUrl;
});

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
      assert.equal(safeUrl(payload), "", `not blocked: ${JSON.stringify(payload)}`);
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
      assert.equal(safeUrl(payload), "", `not blocked: ${payload}`);
    }
  });

  it("allows ordinary product links", () => {
    assert.equal(
      safeUrl("https://www.digikala.com/product/dkp-1"),
      "https://www.digikala.com/product/dkp-1",
    );
    assert.equal(safeUrl("http://shop.example.com/x"), "http://shop.example.com/x");
    assert.equal(safeUrl("mailto:sales@example.com"), "mailto:sales@example.com");
  });

  it("allows in-app relative links unchanged", () => {
    assert.equal(safeUrl("/share/abc123"), "/share/abc123");
    assert.equal(safeUrl("#section"), "#section");
    assert.equal(safeUrl("?page=2"), "?page=2");
  });

  it("normalises protocol-relative URLs instead of trusting them", () => {
    const out = safeUrl("//evil.example/x");
    assert.equal(out, "https://evil.example/x", "should resolve against the page scheme");
  });

  it("returns an empty string for empty input", () => {
    assert.equal(safeUrl(""), "");
    assert.equal(safeUrl(null), "");
    assert.equal(safeUrl(undefined), "");
    assert.equal(safeUrl("   "), "");
  });

  it("never throws on malformed input", () => {
    for (const payload of ["http://", "://x", "%%%", "h".repeat(10000)]) {
      assert.doesNotThrow(() => safeUrl(payload));
    }
  });
});

describe("isSafeUrl", () => {
  it("mirrors safeUrl", () => {
    assert.equal(isSafeUrl("https://example.com"), true);
    assert.equal(isSafeUrl("javascript:alert(1)"), false);
  });
});

describe("safeImageUrl", () => {
  it("allows http(s) images and rejects everything else", () => {
    assert.equal(
      safeImageUrl("https://cdn.example.com/a.png"),
      "https://cdn.example.com/a.png",
    );
    assert.equal(safeImageUrl("data:image/svg+xml,<svg onload=alert(1)>"), "");
    assert.equal(safeImageUrl("mailto:a@b.com"), "");
    assert.equal(safeImageUrl("javascript:alert(1)"), "");
  });
});
