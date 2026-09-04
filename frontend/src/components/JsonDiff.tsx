/** Field-level diff between the AI's extraction and the human's correction.
 *
 *  RESEARCH_V2 §7 (human-in-the-loop review): a reviewer approving a raw JSON
 *  blob cannot see what they changed, so they either approve blindly or
 *  re-read 14 lines every time. Showing only the touched fields — old struck
 *  through, new highlighted — makes "save & verify" an informed action.
 *
 *  Deliberately not a text/line diff: these are structured records, so a
 *  key-by-key comparison is both more accurate and easier to read than
 *  character runs. */

type Json = unknown;

function render(v: Json): string {
  if (v === null || v === undefined) return "—";
  if (Array.isArray(v)) return v.length ? v.join(", ") : "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function equal(a: Json, b: Json): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

export interface DiffRow {
  key: string;
  before: Json;
  after: Json;
}

export function diffObjects(
  before: Record<string, Json>,
  after: Record<string, Json>,
): DiffRow[] {
  const keys = new Set([...Object.keys(before), ...Object.keys(after)]);
  const rows: DiffRow[] = [];
  for (const key of keys) {
    if (!equal(before[key], after[key])) {
      rows.push({ key, before: before[key], after: after[key] });
    }
  }
  return rows.sort((a, b) => a.key.localeCompare(b.key));
}

export function JsonDiff({ rows }: { rows: DiffRow[] }) {
  if (rows.length === 0) {
    return (
      <p className="rounded-xl bg-[var(--color-line)] px-3 py-2 text-xs text-[var(--color-muted)]">
        No changes yet — edit a field above to see the diff against the AI extraction.
      </p>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-[var(--color-line)]">
      <table className="w-full text-start text-xs">
        <caption className="sr-only">Changes compared with the AI extraction</caption>
        <thead>
          <tr className="bg-[var(--color-line)]/60 text-[10px] uppercase tracking-wider text-[var(--color-muted)]">
            <th scope="col" className="px-3 py-1.5 font-medium">Field</th>
            <th scope="col" className="px-3 py-1.5 font-medium">AI extracted</th>
            <th scope="col" className="px-3 py-1.5 font-medium">Your correction</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className="border-t border-[var(--color-line)]">
              <td className="px-3 py-2 font-mono font-medium text-[var(--color-ink)]">{r.key}</td>
              <td className="px-3 py-2">
                <span className="rounded bg-[var(--color-danger)]/8 px-1.5 py-0.5 text-[var(--color-danger)] line-through decoration-[var(--color-danger)]/50">
                  {render(r.before)}
                </span>
              </td>
              <td className="px-3 py-2">
                <span className="rounded bg-[var(--color-ok)]/10 px-1.5 py-0.5 font-medium text-[var(--color-ok)]">
                  {render(r.after)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
