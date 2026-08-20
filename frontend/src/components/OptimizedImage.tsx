import { memo, useState } from "react";
import clsx from "clsx";

/**
 * Responsive, CLS-safe image — V2 Phase 2 (performance).
 *
 * Phase 0B counted 10 raw `<img>` tags across 8 files with no modern formats
 * and no `srcset` (`docs/PERF_REPORT_V2.md` §3). Product photography is the
 * dominant byte weight of the recommendations page.
 *
 * What this component guarantees:
 *  - **AVIF → WebP → original** via `<picture>`, so modern browsers get the
 *    smallest encoding and old ones still work.
 *  - **`srcset` / `sizes`** so a phone never downloads a 1600px hero.
 *  - **Reserved aspect box** (`aspect-ratio` + width/height) — the image can
 *    never push layout around while loading, which is the main CLS source.
 *  - **Blur-up placeholder** that cross-fades on decode, so a slow image
 *    looks intentional instead of broken.
 *  - **`decoding="async"`** to keep decode off the main thread, and
 *    `loading`/`fetchPriority` controllable for the LCP element.
 *
 * The catalogue stores one source URL per product, so derivative URLs are
 * produced by convention (`?format=avif&w=…`) — a CDN/S3 image pipeline can
 * honour these without any frontend change. When `deriveSources` is false we
 * degrade to the plain original, never a broken request.
 */

export interface OptimizedImageProps {
  src: string;
  alt: string;
  /** Intrinsic width in px — required to reserve layout space. */
  width: number;
  /** Intrinsic height in px — required to reserve layout space. */
  height: number;
  className?: string;
  /** Wrapper class (the aspect box). */
  wrapperClassName?: string;
  /** `sizes` attribute; defaults to a sensible responsive grid value. */
  sizes?: string;
  /** Widths to emit in srcset. */
  widths?: number[];
  /** True for the LCP image only. */
  priority?: boolean;
  /** Set false for already-optimised or external URLs. */
  deriveSources?: boolean;
  /** Low-quality placeholder colour while loading. */
  placeholderColor?: string;
  onClick?: () => void;
}

const DEFAULT_WIDTHS = [320, 480, 640, 960, 1280];

/** Build a `?format=…&w=…` derivative URL, preserving existing query params. */
function derive(src: string, format: "avif" | "webp", width?: number): string {
  try {
    const url = new URL(src, window.location.origin);
    url.searchParams.set("format", format);
    if (width) url.searchParams.set("w", String(width));
    return url.pathname + url.search + url.hash;
  } catch {
    return src;
  }
}

function srcSet(src: string, format: "avif" | "webp", widths: number[]): string {
  return widths.map((w) => `${derive(src, format, w)} ${w}w`).join(", ");
}

function OptimizedImageInner({
  src,
  alt,
  width,
  height,
  className,
  wrapperClassName,
  sizes = "(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw",
  widths = DEFAULT_WIDTHS,
  priority = false,
  deriveSources = true,
  placeholderColor = "#F1ECE4",
  onClick,
}: OptimizedImageProps) {
  const [loaded, setLoaded] = useState(false);

  // Only offer derivatives for same-origin/relative assets — an arbitrary
  // third-party host will not understand our query convention.
  const canDerive =
    deriveSources && !/^https?:\/\//i.test(src) && !src.startsWith("data:");

  return (
    <div
      className={clsx("relative overflow-hidden", wrapperClassName)}
      style={{ aspectRatio: `${width} / ${height}`, backgroundColor: placeholderColor }}
      onClick={onClick}
    >
      <picture>
        {canDerive && (
          <>
            <source type="image/avif" srcSet={srcSet(src, "avif", widths)} sizes={sizes} />
            <source type="image/webp" srcSet={srcSet(src, "webp", widths)} sizes={sizes} />
          </>
        )}
        <img
          src={src}
          alt={alt}
          width={width}
          height={height}
          sizes={canDerive ? sizes : undefined}
          loading={priority ? "eager" : "lazy"}
          fetchPriority={priority ? "high" : "auto"}
          decoding="async"
          onLoad={() => setLoaded(true)}
          onError={() => setLoaded(true)}
          className={clsx(
            "h-full w-full object-cover transition-opacity duration-300 motion-reduce:transition-none",
            loaded ? "opacity-100" : "opacity-0",
            className,
          )}
        />
      </picture>
    </div>
  );
}

export const OptimizedImage = memo(OptimizedImageInner);
export default OptimizedImage;
