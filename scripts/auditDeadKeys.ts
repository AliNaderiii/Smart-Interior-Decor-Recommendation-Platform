/**
 * Dead Keys Audit — V2 Strict Mode (Phase 0B / Phase 4 gate)
 *
 * Scans every interactive element in the frontend and proves that it does
 * something. A "dead key" is any control a user can click that has no effect.
 *
 * Improvement over the PHASE0_AUDIT_GUIDE regex template: that template scanned
 * flat text and could not see attributes that span lines, nor tell an element
 * with `type="submit"` (driven by a form handler) from a genuinely inert one.
 * This implementation walks the source with a brace/quote-aware tag scanner, so
 * every finding carries a real file:line and an attribute set.
 *
 * Classification
 *   [DEAD]    enabled control with no way to do anything:
 *             - no onClick, no type="submit", no href, not a <Link>
 *             - onClick={() => {}} / onClick={() => null} / console.log-only
 *             - href="#" or href=""
 *   [PARTIAL] control wired to an API call with no error path in the file
 *             (no catch / onError / isError / toast)
 *   [OK-DISABLED] disabled control — allowed only when it carries a
 *             title/aria-label/tooltip explaining why (else DEAD)
 *
 * Usage:  npx tsx scripts/auditDeadKeys.ts [--json] [--quiet]
 * Exit:   1 when DEAD > 0 (strict-mode CI gate), else 0
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT = process.cwd();
const SCAN_DIRS = ["frontend/src/pages", "frontend/src/components"];
const INTERACTIVE = new Set(["button", "Button", "a", "Link", "NavLink", "IconButton"]);

type Finding = {
  level: "DEAD" | "PARTIAL" | "OK-DISABLED" | "SUSPECT";
  file: string;
  line: number;
  tag: string;
  label: string;
  reason: string;
};

const findings: Finding[] = [];
let interactiveCount = 0;

/* ------------------------------------------------------------------ utils */

function walk(dir: string, out: string[] = []): string[] {
  let entries: string[];
  try {
    entries = readdirSync(dir);
  } catch {
    return out;
  }
  for (const entry of entries) {
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) walk(full, out);
    else if (/\.tsx$/.test(entry)) out.push(full);
  }
  return out;
}

/** Scan forward from `<` to the matching `>` of the opening tag, ignoring
 *  `>` that appears inside strings, template literals or nested braces
 *  (e.g. onClick={() => x > 1 ? a : b}). Returns the raw opening tag. */
function readOpeningTag(src: string, start: number): { raw: string; end: number } | null {
  let depth = 0;
  let quote: string | null = null;
  for (let i = start; i < src.length; i++) {
    const ch = src[i];
    const prev = src[i - 1];
    if (quote) {
      if (ch === quote && prev !== "\\") quote = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === "`") {
      quote = ch;
      continue;
    }
    if (ch === "{") depth++;
    else if (ch === "}") depth--;
    else if (ch === ">" && depth === 0) return { raw: src.slice(start, i + 1), end: i + 1 };
  }
  return null;
}

/** Extract the value of an attribute from a raw opening tag, brace-aware. */
function attr(raw: string, name: string): string | null {
  const re = new RegExp(`(?:^|\\s)${name}\\s*=\\s*`, "g");
  const m = re.exec(raw);
  if (!m) {
    // bare attribute, e.g. `disabled`
    return new RegExp(`(?:^|\\s)${name}(?=[\\s/>])`).test(raw) ? "true" : null;
  }
  let i = m.index + m[0].length;
  const opener = raw[i];
  if (opener === '"' || opener === "'") {
    const close = raw.indexOf(opener, i + 1);
    return raw.slice(i + 1, close === -1 ? raw.length : close);
  }
  if (opener === "{") {
    let depth = 0;
    let quote: string | null = null;
    for (let j = i; j < raw.length; j++) {
      const ch = raw[j];
      if (quote) {
        if (ch === quote && raw[j - 1] !== "\\") quote = null;
        continue;
      }
      if (ch === '"' || ch === "'" || ch === "`") quote = ch;
      else if (ch === "{") depth++;
      else if (ch === "}") {
        depth--;
        if (depth === 0) return raw.slice(i + 1, j).trim();
      }
    }
  }
  return null;
}

/** Visible text of the element, for human-readable reporting. */
function labelOf(src: string, tagEnd: number, raw: string): string {
  const aria = attr(raw, "aria-label");
  if (aria) return aria.slice(0, 40);
  const text = src
    .slice(tagEnd, tagEnd + 220)
    .split("<")[0]
    .replace(/\{[^}]*\}/g, "")
    .replace(/\s+/g, " ")
    .trim();
  return text.slice(0, 40) || "(no label)";
}

const isEmptyHandler = (v: string): boolean => {
  const body = v.trim();
  if (/^\(\s*\)?\s*=>\s*\{\s*\}$/.test(body)) return true; // () => {}
  if (/^\([^)]*\)\s*=>\s*\{\s*\}$/.test(body)) return true;
  if (/^\([^)]*\)?\s*=>\s*(null|undefined|void 0)$/.test(body)) return true;
  if (/^undefined$/.test(body)) return true;
  // console.log-only body
  const stripped = body.replace(/^\([^)]*\)\s*=>\s*\{?/, "").replace(/\}$/, "").trim();
  if (/^console\.(log|warn|debug)\([^;]*\);?$/.test(stripped)) return true;
  if (/^\/\/\s*TODO/i.test(stripped) || /^\{?\s*\/\*\s*TODO/i.test(body)) return true;
  return false;
};

/* ------------------------------------------------------------------- scan */

const files = SCAN_DIRS.flatMap((d) => walk(join(ROOT, d))).sort();

for (const file of files) {
  const src = readFileSync(file, "utf-8");
  const rel = relative(ROOT, file);
  const lineAt = (idx: number) => src.slice(0, idx).split("\n").length;

  // file-level error-handling signal, used for PARTIAL classification
  const hasApiCall = /\b(get|post|patch|put|del|delete)\s*[<(]|useMutation|fetch\(|axios\./.test(src);
  const hasErrorPath =
    /catch\s*\(|\.catch\(|onError|isError|ErrorState|toast\.error|toast\(/.test(src);

  for (let i = 0; i < src.length; i++) {
    if (src[i] !== "<") continue;
    const nameMatch = /^<([A-Za-z][A-Za-z0-9.]*)/.exec(src.slice(i, i + 40));
    if (!nameMatch) continue;
    const tag = nameMatch[1];
    if (!INTERACTIVE.has(tag)) continue;

    const scanned = readOpeningTag(src, i);
    if (!scanned) continue;
    const { raw, end } = scanned;
    const line = lineAt(i);
    const label = labelOf(src, end, raw);
    interactiveCount++;

    const onClick = attr(raw, "onClick");
    const type = attr(raw, "type");
    const href = attr(raw, "href");
    const to = attr(raw, "to");
    const disabled = attr(raw, "disabled");
    const explains = attr(raw, "title") || attr(raw, "aria-label") || /Tooltip/.test(raw);
    const spread = /\{\s*\.\.\.props\s*\}/.test(raw) || /\{\s*\.\.\.rest\s*\}/.test(raw);
    const isPrimitive = /components\/ui\.tsx$/.test(rel) && spread;

    const push = (level: Finding["level"], reason: string) =>
      findings.push({ level, file: rel, line, tag, label, reason });

    // href="#" / href="" — decorative link
    if (href !== null && (href.trim() === "#" || href.trim() === "")) {
      push("DEAD", `<${tag}> href="${href}" is a decorative link`);
      continue;
    }

    // empty / no-op handler
    if (onClick !== null && isEmptyHandler(onClick)) {
      push("DEAD", `empty handler onClick={${onClick.slice(0, 60)}}`);
      continue;
    }

    // disabled controls
    if (disabled !== null) {
      if (disabled === "true" || /^\{?true\}?$/.test(disabled)) {
        if (!explains) {
          push("DEAD", "permanently disabled with no title/aria-label explaining why");
        } else {
          push("OK-DISABLED", `disabled + explained ("${String(explains).slice(0, 40)}")`);
        }
      }
      // conditionally disabled (disabled={saved || isPending}) is fine
      continue;
    }

    // design-system primitive that forwards props — not a dead key by itself
    if (isPrimitive) continue;

    // nothing wired at all
    const wired =
      onClick !== null ||
      type === "submit" ||
      href !== null ||
      to !== null ||
      tag === "Link" ||
      tag === "NavLink";
    if (!wired) {
      push("DEAD", `<${tag}> has no onClick, no type="submit", no href/to — inert control`);
      continue;
    }

    // wired to an API call but the file has no error path
    if (onClick !== null && hasApiCall && !hasErrorPath && /mutate|post|patch|del|fetch/.test(onClick)) {
      push("PARTIAL", "handler triggers an API call but file has no catch/onError/toast");
    }
  }
}

/* ---------------------------------------------------------------- reporting */

const dead = findings.filter((f) => f.level === "DEAD");
const partial = findings.filter((f) => f.level === "PARTIAL");
const okDisabled = findings.filter((f) => f.level === "OK-DISABLED");

if (process.argv.includes("--json")) {
  console.log(JSON.stringify({ interactiveCount, findings }, null, 2));
} else {
  console.log("=== DEAD KEYS AUDIT ===");
  console.log(`scanned ${files.length} files, ${interactiveCount} interactive elements\n`);
  for (const f of [...dead, ...partial, ...okDisabled]) {
    console.log(`[${f.level}] ${f.file}:${f.line} <${f.tag}> "${f.label}" — ${f.reason}`);
  }
  if (findings.length === 0) console.log("(no findings)");
  console.log(`\nTOTAL: ${dead.length} DEAD, ${partial.length} PARTIAL, ${okDisabled.length} OK-DISABLED`);
  console.log(
    dead.length > 0
      ? "RESULT: FAIL — fix all DEAD before proceeding"
      : "RESULT: PASS — 0 DEAD",
  );
}

process.exit(dead.length > 0 ? 1 : 0);
