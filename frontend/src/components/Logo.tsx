/** Brand mark.
 *
 * The previous mark was the literal string "SD" in a rounded square — a
 * placeholder, not a logo. This one is drawn: an armchair silhouette formed
 * from a rounded seat and two arms, sitting inside a soft square that reads
 * as a room. It says "furniture in a space" at 24px, which is the only size
 * that matters for a nav bar.
 *
 * Why an inline SVG rather than a file: it inherits `currentColor`, so the
 * same component works on the light canvas and on the dark footer without a
 * second asset, and it costs no extra request.
 */
export function Logo({
  size = 32,
  className = "",
}: {
  size?: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      role="img"
      aria-hidden="true"
      className={className}
    >
      {/* room / frame */}
      <rect
        x="1.25"
        y="1.25"
        width="29.5"
        height="29.5"
        rx="8.5"
        fill="currentColor"
      />
      {/* armchair, knocked out of the frame */}
      <g fill="var(--color-canvas)">
        {/* backrest */}
        <rect x="9" y="8.5" width="14" height="7.5" rx="3.2" opacity="0.55" />
        {/* seat */}
        <rect x="8" y="15" width="16" height="5.4" rx="2.4" />
        {/* arms */}
        <rect x="6.2" y="13.4" width="3.2" height="7" rx="1.6" />
        <rect x="22.6" y="13.4" width="3.2" height="7" rx="1.6" />
        {/* legs */}
        <rect x="8.6" y="20.6" width="1.8" height="3.2" rx="0.9" />
        <rect x="21.6" y="20.6" width="1.8" height="3.2" rx="0.9" />
      </g>
    </svg>
  );
}
