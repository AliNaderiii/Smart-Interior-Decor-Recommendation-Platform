import { memo, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import * as HoverCard from "@radix-ui/react-hover-card";
import { Link } from "react-router-dom";
import type { RecommendedProduct } from "@/lib/types";
import { formatToman } from "@/lib/constants";
import { MotionCard } from "@/components/ui";
import { OptimizedImage } from "@/components/OptimizedImage";
import { crossfade, spring } from "@/lib/motion";

interface Props {
  product: RecommendedProduct;
  rank: number;
  onAdd?: (p: RecommendedProduct) => void;
  added?: boolean;
  /** Current 👍/👎 verdict: 1, -1 or undefined. */
  feedback?: number;
  onFeedback?: (p: RecommendedProduct, signal: 1 | -1) => void;
}

/* ---------------------------------------------------------------- sub-parts */

/** Match breakdown in a HoverCard, not a tooltip.
 *
 *  DESIGN_SYSTEM_V2 §7: a tooltip cannot be hovered into or focused, so rich
 *  interactive content inside one is unreachable for keyboard and touch users.
 *  Radix HoverCard is focusable, dismissible with Esc, and keeps the content
 *  in the a11y tree. Aesop's rule — secondary detail hides behind interaction
 *  rather than cluttering the card face. */
function MatchBreakdown({ product }: { product: RecommendedProduct }) {
  const exp = product.explanation;
  const rows = [
    { label: "Style", value: exp.style_match, detail: product.styles.join(" / ") || "—" },
    { label: "Colour", value: exp.color_match, detail: null },
    { label: "Budget", value: exp.budget_fit, detail: formatToman(product.price_toman) },
    {
      label: "Material",
      value: exp.material_match,
      detail: exp.matched_materials.length ? exp.matched_materials.join(", ") : product.materials.join(", ") || "—",
    },
  ];

  return (
    <HoverCard.Root openDelay={120} closeDelay={80}>
      <HoverCard.Trigger asChild>
        <button
          type="button"
          className="w-full rounded-lg text-left text-xs font-semibold text-[var(--color-muted)] underline decoration-dotted underline-offset-2 hover:text-[var(--color-ink)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
          aria-label={`Why we matched ${product.title}: ${Math.round(product.final_score * 100)} percent overall`}
        >
          {Math.round(product.final_score * 100)}% match — why?
        </button>
      </HoverCard.Trigger>
      <HoverCard.Portal>
        <HoverCard.Content
          side="top"
          align="start"
          sideOffset={8}
          className="z-50 w-72 rounded-2xl bg-[var(--color-surface)] p-4 shadow-[var(--shadow-float)]"
        >
          <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-[var(--color-faint)]">
            Match breakdown
          </p>
          <div className="space-y-2.5">
            {rows.map((r) => (
              <div key={r.label}>
                <div className="flex items-baseline justify-between text-xs">
                  <span className="font-medium text-[var(--color-ink)]">{r.label}</span>
                  <span className="tabular-nums text-[var(--color-muted)]">{r.value}%</span>
                </div>
                {/* Bar doubles as the visual weight; the number stays for a11y. */}
                <div className="mt-1 h-1 overflow-hidden rounded-full bg-[var(--color-line)]">
                  <div
                    className="h-full rounded-full bg-[var(--color-accent)]"
                    style={{ width: `${Math.max(2, Math.min(100, r.value))}%` }}
                  />
                </div>
                {r.detail && <p className="mt-1 text-[11px] text-[var(--color-faint)]">{r.detail}</p>}
              </div>
            ))}
          </div>
          {product.colors.length > 0 && (
            <div className="mt-3 flex items-center gap-1.5 border-t border-[var(--color-line)] pt-3">
              <span className="text-[11px] text-[var(--color-faint)]">Palette</span>
              {product.colors.slice(0, 5).map((c) => (
                <span
                  key={c}
                  title={c}
                  className="h-3.5 w-3.5 rounded-full ring-1 ring-inset ring-black/10"
                  style={{ backgroundColor: c }}
                />
              ))}
            </div>
          )}
          <HoverCard.Arrow className="fill-[var(--color-surface)]" />
        </HoverCard.Content>
      </HoverCard.Portal>
    </HoverCard.Root>
  );
}

/** 👍/👎. RESEARCH_V2 §2 (Havenly) — this must re-rank, not just light up. */
function FeedbackButtons({
  product,
  value,
  onFeedback,
}: {
  product: RecommendedProduct;
  value?: number;
  onFeedback?: (p: RecommendedProduct, signal: 1 | -1) => void;
}) {
  if (!onFeedback) return null;
  const base =
    "grid h-8 w-8 place-items-center rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]";
  return (
    <div className="flex items-center gap-1">
      <button
        type="button"
        aria-label={`More like ${product.title}`}
        aria-pressed={value === 1}
        onClick={() => onFeedback(product, 1)}
        className={`${base} ${
          value === 1
            ? "bg-[var(--color-ok)]/12 text-[var(--color-ok)]"
            : "text-[var(--color-faint)] hover:bg-[var(--color-line)] hover:text-[var(--color-ink)]"
        }`}
      >
        <svg width="15" height="15" viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <path
            d="M6 17V8.5l3.2-5.1a1.3 1.3 0 012.4.7V8h3.6a1.6 1.6 0 011.55 2l-1.3 5.4A2 2 0 0113.5 17H6zM6 17H3.5V8.5H6"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinejoin="round"
            fill={value === 1 ? "currentColor" : "none"}
            fillOpacity={value === 1 ? 0.18 : 0}
          />
        </svg>
      </button>
      <button
        type="button"
        aria-label={`Fewer like ${product.title}`}
        aria-pressed={value === -1}
        onClick={() => onFeedback(product, -1)}
        className={`${base} ${
          value === -1
            ? "bg-[var(--color-danger)]/12 text-[var(--color-danger)]"
            : "text-[var(--color-faint)] hover:bg-[var(--color-line)] hover:text-[var(--color-ink)]"
        }`}
      >
        <svg width="15" height="15" viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <path
            d="M14 3v8.5l-3.2 5.1a1.3 1.3 0 01-2.4-.7V12H4.8a1.6 1.6 0 01-1.55-2l1.3-5.4A2 2 0 016.5 3H14zM14 3h2.5v8.5H14"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinejoin="round"
            fill={value === -1 ? "currentColor" : "none"}
            fillOpacity={value === -1 ? 0.18 : 0}
          />
        </svg>
      </button>
    </div>
  );
}

/** Verification-honest price badge — RESEARCH_V2 §10 (Made.com).
 *  Never present an AI-extracted price as fact. Colour is paired with a text
 *  label so the signal survives colour-blindness and greyscale. */
function PriceBadge({ verified }: { verified?: boolean }) {
  if (verified === undefined) return null;
  return verified ? (
    <span className="inline-flex items-center gap-1 rounded-full bg-[var(--color-ok)]/10 px-2 py-0.5 text-[10px] font-semibold text-[var(--color-ok)]">
      <svg width="9" height="9" viewBox="0 0 12 12" fill="none" aria-hidden="true">
        <path d="M2.5 6.2l2.2 2.2 4.8-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      Verified price
    </span>
  ) : (
    <span
      className="rounded-full bg-[var(--color-warn)]/10 px-2 py-0.5 text-[10px] font-semibold text-[var(--color-warn)]"
      title="Extracted by AI from the retailer page — confirm before buying."
    >
      Estimated price
    </span>
  );
}

/* -------------------------------------------------------------------- card */

function ProductCardInner({ product, rank, onAdd, added, feedback, onFeedback }: Props) {
  const [hovered, setHovered] = useState(false);
  const reduce = useReducedMotion();

  /* Soft paywall — RESEARCH_V2 §2: show the shape of the value, do not slam a
     door. The image stays blurred but the card keeps its geometry so the grid
     does not reflow when a user upgrades. */
  if (product.locked) {
    return (
      <MotionCard interactive={false} className="relative overflow-hidden">
        <OptimizedImage
          src={product.image_url}
          alt=""
          width={400}
          height={260}
          sizes="(max-width: 768px) 100vw, 33vw"
          wrapperClassName="h-40 w-full"
          className="blur-lg saturate-50"
        />
        <div className="absolute inset-0 grid place-items-center bg-[var(--color-surface)]/60 p-4 text-center backdrop-blur-[2px]">
          <div>
            <p className="text-sm font-semibold text-[var(--color-ink)]">
              {rank + 1} more match{rank === 0 ? "" : "es"} in this room
            </p>
            <p className="mt-0.5 text-xs text-[var(--color-muted)]">Unlock the full set with Pro</p>
            <Link
              to="/upgrade"
              className="mt-3 inline-block rounded-xl bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-[var(--color-canvas)] hover:opacity-90"
            >
              Unlock with Pro
            </Link>
          </div>
        </div>
      </MotionCard>
    );
  }

  /* Second-image crossfade on hover (Article, 220ms — instant reads as a
     glitch). The catalogue stores one image per product, so the "second image"
     is a zoomed derivative of the same asset: it still communicates depth and
     lets the interaction ship without new data. */
  const secondSrc = product.image_url;

  return (
    <MotionCard
      className="flex h-full flex-col overflow-hidden"
      interactive
    >
      <div
        className="relative"
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        <OptimizedImage
          src={product.image_url}
          alt={product.title}
          width={400}
          height={260}
          priority={rank === 0}
          sizes="(max-width: 768px) 100vw, 33vw"
          wrapperClassName="h-40 w-full"
        />
        <AnimatePresence>
          {hovered && !reduce && (
            <motion.div
              className="pointer-events-none absolute inset-0"
              initial={{ opacity: 0, scale: 1.0 }}
              animate={{ opacity: 1, scale: 1.06 }}
              exit={{ opacity: 0 }}
              transition={crossfade}
            >
              <OptimizedImage
                src={secondSrc}
                alt=""
                width={400}
                height={260}
                sizes="(max-width: 768px) 100vw, 33vw"
                wrapperClassName="h-40 w-full"
              />
            </motion.div>
          )}
        </AnimatePresence>
        <span className="absolute left-2 top-2 rounded-full bg-[var(--color-surface)]/90 px-2 py-0.5 text-[11px] font-semibold tabular-nums text-[var(--color-ink)] backdrop-blur">
          #{rank + 1}
        </span>
        <div className="absolute right-2 top-2">
          <PriceBadge verified={product.is_verified} />
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-2 p-4">
        <h3 className="line-clamp-2 text-sm font-semibold leading-snug text-[var(--color-ink)]">
          {product.title}
        </h3>
        <p className="text-base font-semibold tabular-nums text-[var(--color-ink)]">
          {formatToman(product.price_toman)}
        </p>

        {/* Colour swatches as chips, never a text list (Wayfair/Baymard). */}
        {product.colors.length > 0 && (
          <div className="flex items-center gap-1" aria-label={`Colours: ${product.colors.join(", ")}`}>
            {product.colors.slice(0, 4).map((c) => (
              <span
                key={c}
                title={c}
                className="h-3.5 w-3.5 rounded-full ring-1 ring-inset ring-black/10"
                style={{ backgroundColor: c }}
              />
            ))}
          </div>
        )}

        <MatchBreakdown product={product} />

        <div className="mt-auto flex items-center gap-2 pt-2">
          {onAdd && (
            <motion.button
              type="button"
              whileTap={reduce ? undefined : { scale: 0.98 }}
              transition={spring}
              onClick={() => onAdd(product)}
              disabled={added}
              className={`min-h-9 flex-1 rounded-xl px-3 py-2 text-xs font-semibold transition-colors ${
                added
                  ? "cursor-default bg-[var(--color-ok)]/10 text-[var(--color-ok)]"
                  : "bg-[var(--color-accent)] text-[var(--color-canvas)] hover:opacity-90"
              }`}
            >
              {added ? "Added ✓" : "Add to moodboard"}
            </motion.button>
          )}
          <FeedbackButtons product={product} value={feedback} onFeedback={onFeedback} />
        </div>

        {product.seller_link && (
          <a
            href={product.seller_link}
            target="_blank"
            rel="noreferrer noopener"
            className="text-center text-[11px] font-medium text-[var(--color-muted)] underline-offset-2 hover:text-[var(--color-ink)] hover:underline"
          >
            View at retailer ↗
          </a>
        )}
      </div>
    </MotionCard>
  );
}

export const ProductCard = memo(ProductCardInner);
export default ProductCard;
