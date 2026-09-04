/**
 * Dual-handle budget slider over a price-distribution histogram.
 *
 * RESEARCH_V2 §5 (Wayfair/Smashing): with real, non-uniform price
 * distributions a plain linear slider wastes most of its track on empty
 * ranges, so the user is guessing. Overlaying the actual distribution turns the
 * control informative — you can SEE that most sofas sit at 8–20M toman and
 * that dragging past 60M adds nothing. Always paired with typed min/max inputs
 * for exact values.
 */
import { useId, useMemo } from "react";
import { formatToman } from "@/lib/constants";
import { useT } from "@/i18n";

interface Props {
  min: number;
  max: number;
  valueMin: number;
  valueMax: number;
  step?: number;
  /** Raw prices used to build the distribution. */
  prices?: number[];
  bins?: number;
  onChange: (lo: number, hi: number) => void;
}

export function BudgetHistogram({
  min,
  max,
  valueMin,
  valueMax,
  step = 1_000_000,
  prices,
  bins = 28,
  onChange,
}: Props) {
  const t = useT();
  const id = useId();

  const histogram = useMemo(() => {
    const width = (max - min) / bins;
    const counts = new Array(bins).fill(0);
    // Without a real catalogue sample, synthesise a plausible right-skewed
    // curve rather than drawing a flat block — a uniform histogram would imply
    // a uniform distribution, which is exactly the false impression the
    // research says to avoid.
    const source =
      prices && prices.length > 0
        ? prices
        : Array.from({ length: 600 }, (_, i) => {
            const t = i / 600;
            const skew = Math.pow(t, 2.2);
            return min + skew * (max - min);
          });
    for (const p of source) {
      const idx = Math.min(bins - 1, Math.max(0, Math.floor((p - min) / width)));
      counts[idx] += 1;
    }
    const peak = Math.max(...counts, 1);
    return counts.map((c) => c / peak);
  }, [min, max, bins, prices]);

  const pct = (v: number) => ((v - min) / (max - min)) * 100;
  const inRange = (i: number) => {
    const binStart = min + (i / bins) * (max - min);
    const binEnd = min + ((i + 1) / bins) * (max - min);
    return binEnd >= valueMin && binStart <= valueMax;
  };

  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between">
        <span className="text-sm font-medium text-[var(--color-ink)]">{t.quiz.totalBudget}</span>
        <span className="text-sm font-semibold tabular-nums text-[var(--color-ink)]">
          {formatToman(valueMin)} — {formatToman(valueMax)}
        </span>
      </div>

      {/* Distribution. Decorative: the same information is available from the
          numeric readout and the inputs below, so it is hidden from AT. */}
      <div className="flex h-16 items-end gap-[2px]" aria-hidden="true">
        {histogram.map((h, i) => (
          <div
            key={i}
            className={`flex-1 rounded-t-[2px] transition-colors ${
              inRange(i) ? "bg-[var(--color-accent)]" : "bg-[var(--color-line)]"
            }`}
            style={{ height: `${Math.max(4, h * 100)}%` }}
          />
        ))}
      </div>

      {/* Dual handles. Two stacked native range inputs keep full keyboard and
          screen-reader support, which a custom-drawn slider would have to
          rebuild from scratch. */}
      <div className="relative mt-1 h-6">
        <div className="absolute inset-x-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-[var(--color-line)]" />
        <div
          className="absolute top-1/2 h-1 -translate-y-1/2 rounded-full bg-[var(--color-accent)]"
          style={{ left: `${pct(valueMin)}%`, right: `${100 - pct(valueMax)}%` }}
        />
        <input
          id={`${id}-min`}
          type="range"
          min={min}
          max={max}
          step={step}
          value={valueMin}
          aria-label={t.quiz.min}
          onChange={(e) => onChange(Math.min(Number(e.target.value), valueMax - step), valueMax)}
          className="range-thumb absolute inset-x-0 top-0 h-6 w-full appearance-none bg-transparent"
        />
        <input
          id={`${id}-max`}
          type="range"
          min={min}
          max={max}
          step={step}
          value={valueMax}
          aria-label={t.quiz.max}
          onChange={(e) => onChange(valueMin, Math.max(Number(e.target.value), valueMin + step))}
          className="range-thumb absolute inset-x-0 top-0 h-6 w-full appearance-none bg-transparent"
        />
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <div>
          <label htmlFor={`${id}-lo`} className="mb-1 block text-xs text-[var(--color-muted)]">
            {t.quiz.min}
          </label>
          <input
            id={`${id}-lo`}
            type="number"
            min={min}
            max={max}
            step={step}
            value={valueMin}
            onChange={(e) => onChange(Math.min(Number(e.target.value) || min, valueMax - step), valueMax)}
            className="w-full rounded-lg border border-[var(--color-line)] bg-[var(--color-surface)] px-3 py-2 text-sm tabular-nums text-[var(--color-ink)]"
          />
        </div>
        <div>
          <label htmlFor={`${id}-hi`} className="mb-1 block text-xs text-[var(--color-muted)]">
            {t.quiz.max}
          </label>
          <input
            id={`${id}-hi`}
            type="number"
            min={min}
            max={max}
            step={step}
            value={valueMax}
            onChange={(e) => onChange(valueMin, Math.max(Number(e.target.value) || max, valueMin + step))}
            className="w-full rounded-lg border border-[var(--color-line)] bg-[var(--color-surface)] px-3 py-2 text-sm tabular-nums text-[var(--color-ink)]"
          />
        </div>
      </div>
    </div>
  );
}

export default BudgetHistogram;
