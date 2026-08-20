/**
 * Phase 5 — accessibility audit.
 *
 * Renders every page to static markup and checks the WCAG criteria that can
 * be verified from the DOM alone. This is not a replacement for axe-core in a
 * real browser (which needs computed styles and a layout engine, unavailable
 * here — see docs/PERF_REPORT_V2.md on the Chromium block); it targets the
 * failures that are actually common in this codebase:
 *
 *   1.1.1  every <img> has an alt attribute (empty alt is valid for decorative)
 *   4.1.2  every control has an accessible name
 *   1.3.1  every form input has an associated label
 *   2.4.4  no "click here" / bare-icon links without a name
 *   1.4.3  text/background contrast >= 4.5:1 for the token palette
 *
 * Run: npx tsx --tsconfig tsconfig.app.json scripts/a11yAudit.mts
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import { JSDOM } from "jsdom";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "@/components/Toast";
import { CommandPaletteProvider } from "@/components/CommandPalette";

import HomePage from "@/pages/HomePage";
import LoginPage from "@/pages/LoginPage";
import RegisterPage from "@/pages/RegisterPage";
import QuizPage from "@/pages/QuizPage";
import RecommendationsPage from "@/pages/RecommendationsPage";
import MoodboardsPage from "@/pages/MoodboardsPage";
import MoodboardEditorPage from "@/pages/MoodboardEditorPage";
import FloorplanPage from "@/pages/FloorplanPage";
import ShoppingListPage from "@/pages/ShoppingListPage";
import UpgradePage from "@/pages/UpgradePage";
import SharePage from "@/pages/SharePage";
import DesignerDashboardPage from "@/pages/designer/DashboardPage";
import DesignerProjectPage from "@/pages/designer/ProjectPage";
import AdminProductsPage from "@/pages/admin/ProductsPage";
import AdminUsersPage from "@/pages/admin/UsersPage";
import AdminSubscriptionsPage from "@/pages/admin/SubscriptionsPage";

const PAGES: [string, React.ComponentType][] = [
  ["Home", HomePage], ["Login", LoginPage], ["Register", RegisterPage],
  ["Quiz", QuizPage], ["Recommendations", RecommendationsPage],
  ["Moodboards", MoodboardsPage], ["MoodboardEditor", MoodboardEditorPage],
  ["Floorplan", FloorplanPage], ["ShoppingList", ShoppingListPage],
  ["Upgrade", UpgradePage], ["Share", SharePage],
  ["DesignerDashboard", DesignerDashboardPage], ["DesignerProject", DesignerProjectPage],
  ["AdminProducts", AdminProductsPage], ["AdminUsers", AdminUsersPage],
  ["AdminSubs", AdminSubscriptionsPage],
];

/* ---------------------------------------------------------------- contrast */

function srgb(c: number) {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}
function luminance(hex: string) {
  const h = hex.replace("#", "");
  const n = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(n.slice(i, i + 2), 16));
  return 0.2126 * srgb(r) + 0.7152 * srgb(g) + 0.0722 * srgb(b);
}
function ratio(a: string, b: string) {
  const [l1, l2] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (l1 + 0.05) / (l2 + 0.05);
}

/** Parse the tokens out of index.css rather than duplicating them here.
 *  A hardcoded copy silently goes stale the moment someone tunes a colour —
 *  which is exactly the bug that let a failing --color-faint ship. */
function readTokens(): [Record<string, string>, Record<string, string>] {
  const css = readFileSync(new URL("../src/index.css", import.meta.url), "utf8");
  // Tailwind v4 declares tokens in @theme; html.dark overrides them.
  const themeBody = /@theme\s*\{([\s\S]*?)\n\}/.exec(css)?.[1] ?? "";
  const rootBody = (/:root\s*\{([\s\S]*?)\n\}/.exec(css)?.[1] ?? "") + themeBody;
  const darkBody = /html\.dark\s*\{([\s\S]*?)\n\}/.exec(css)?.[1] ?? "";
  const grab = (body: string) => {
    const out: Record<string, string> = {};
    for (const m of body.matchAll(/--color-([a-z]+):\s*(#[0-9A-Fa-f]{3,8})/g)) out[m[1]] = m[2];
    return out;
  };
  const light = grab(rootBody);
  const dark = { ...light, ...grab(darkBody) };
  const need = ["canvas", "surface", "ink", "muted", "faint", "accent", "ok", "warn", "danger"];
  for (const [label, t] of [["light", light], ["dark", dark]] as const) {
    const missing = need.filter((k) => !t[k]);
    if (missing.length) {
      throw new Error(`index.css is missing ${label} tokens: ${missing.join(", ")}`);
    }
  }
  return [light, dark];
}

const [LIGHT, DARK] = readTokens();

interface Issue { page: string; rule: string; detail: string }
const issues: Issue[] = [];
let checked = 0;

/* -------------------------------------------------------------- DOM checks */

for (const [name, Page] of PAGES) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  let html = "";
  try {
    html = renderToStaticMarkup(
      React.createElement(MemoryRouter, null,
        React.createElement(QueryClientProvider, { client: qc },
          React.createElement(ToastProvider, null,
            React.createElement(CommandPaletteProvider, null,
              React.createElement(Page))))),
    );
  } catch (e) {
    issues.push({ page: name, rule: "render", detail: (e as Error).message.split("\n")[0] });
    continue;
  }

  const doc = new JSDOM(`<body>${html}</body>`).window.document;

  for (const img of doc.querySelectorAll("img")) {
    checked++;
    if (img.getAttribute("alt") === null) {
      issues.push({ page: name, rule: "1.1.1 img-alt", detail: `<img src="${img.getAttribute("src")?.slice(0, 60)}">` });
    }
  }

  for (const el of doc.querySelectorAll("button, a[href], [role='button']")) {
    checked++;
    const name_ =
      el.getAttribute("aria-label") ||
      el.getAttribute("title") ||
      el.textContent?.trim() ||
      el.querySelector("img")?.getAttribute("alt") ||
      "";
    if (!name_) {
      issues.push({ page: name, rule: "4.1.2 control-name", detail: el.outerHTML.slice(0, 110) });
    } else if (/^(click here|here|read more|link|more)$/i.test(name_)) {
      issues.push({ page: name, rule: "2.4.4 link-purpose", detail: `"${name_}"` });
    }
  }

  for (const input of doc.querySelectorAll("input, select, textarea")) {
    if (input.getAttribute("type") === "hidden") continue;
    checked++;
    const id = input.getAttribute("id");
    const labelled =
      input.getAttribute("aria-label") ||
      input.getAttribute("aria-labelledby") ||
      (id && doc.querySelector(`label[for="${id}"]`)) ||
      input.closest("label");
    if (!labelled) {
      issues.push({ page: name, rule: "1.3.1 input-label", detail: input.outerHTML.slice(0, 110) });
    }
  }

  // A page should have exactly one h1 and no skipped heading levels.
  const hs = [...doc.querySelectorAll("h1,h2,h3,h4,h5,h6")].map((h) => +h.tagName[1]);
  const h1s = hs.filter((h) => h === 1).length;
  if (hs.length && h1s > 1) {
    issues.push({ page: name, rule: "1.3.1 heading-order", detail: `${h1s} <h1> elements` });
  }
  for (let i = 1; i < hs.length; i++) {
    if (hs[i] - hs[i - 1] > 1) {
      issues.push({ page: name, rule: "1.3.1 heading-order", detail: `h${hs[i - 1]} → h${hs[i]}` });
      break;
    }
  }
}

/* ------------------------------------------------------------ contrast run */

console.log("\n=== CONTRAST (WCAG 1.4.3, AA needs 4.5:1 body / 3:1 large) ===\n");
const contrastRows: string[] = [];
for (const [theme, T] of [["light", LIGHT], ["dark", DARK]] as const) {
  for (const bgKey of ["canvas", "surface"] as const) {
    for (const fgKey of ["ink", "muted", "faint", "ok", "warn", "danger"] as const) {
      const r = ratio(T[fgKey], T[bgKey]);
      // `faint` is used only for >=18.66px or bold metadata → large-text 3:1.
      const need = fgKey === "faint" ? 3 : 4.5;
      const pass = r >= need;
      contrastRows.push(
        `${theme.padEnd(6)} ${fgKey.padEnd(7)} on ${bgKey.padEnd(8)} ${r.toFixed(2)}:1  need ${need}  ${pass ? "PASS" : "FAIL"}`,
      );
      if (!pass) issues.push({ page: `theme:${theme}`, rule: "1.4.3 contrast", detail: `${fgKey} on ${bgKey} = ${r.toFixed(2)}:1 (need ${need})` });
    }
  }
  // Accent buttons render canvas-coloured text on the accent fill.
  const r = ratio(T.canvas, T.accent);
  contrastRows.push(`${theme.padEnd(6)} ${"canvas".padEnd(7)} on ${"accent".padEnd(8)} ${r.toFixed(2)}:1  need 4.5  ${r >= 4.5 ? "PASS" : "FAIL"}`);
  if (r < 4.5) issues.push({ page: `theme:${theme}`, rule: "1.4.3 contrast", detail: `canvas on accent = ${r.toFixed(2)}:1` });
}
console.log(contrastRows.join("\n"));

/* ---------------------------------------------------------------- report */

console.log(`\n=== DOM A11Y (${checked} elements checked across ${PAGES.length} pages) ===\n`);
if (issues.length === 0) {
  console.log("(no issues)");
} else {
  for (const i of issues) console.log(`[${i.rule}] ${i.page}: ${i.detail}`);
}
console.log(`\nTOTAL: ${issues.length} issue(s)`);
console.log(issues.length === 0 ? "RESULT: PASS" : "RESULT: FAIL");
process.exit(issues.length === 0 ? 0 : 1);
