/**
 * The logo, reduced until it survives 24px.
 *
 * The full lockup is a photographic frog inside a closed navy rectangle. Neither
 * part transfers: the render turns to mud below about 64px, and a closed
 * rectangle at this size reads as a checkbox. What is kept is the pairing that
 * makes the logo recognisable — a warm orange body against a cool ground,
 * framed — with the frame opened into four corner marks. That reads as a
 * reticle, which is what the product does anyway.
 *
 * The pose is the logo's: a side-on crouch, weight forward, hind leg folded
 * high. Four candidate silhouettes were rendered from 22px to 170px before
 * this one — a front-facing two-eyed frog reads faster at 22px, but it reads
 * as a generic cartoon frog rather than as this logo, and the wordmark sitting
 * beside the mark is doing the identifying anyway.
 *
 * Body is one filled outline; limbs are strokes. A filled leg at this weight
 * is two curves meeting in a point, and the point is what pixelates first.
 */
export default function BrandMark({ size = 30 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      role="img"
      aria-label="Site Scanner"
    >
      {/* Corner marks. Drawn under the frog so the body breaks the frame the
          way it does in the full lockup. */}
      <g stroke="currentColor" strokeWidth="1.6" strokeLinecap="square" opacity=".85">
        <path d="M2.6 9.4V2.6h6.8" />
        <path d="M22.6 2.6h6.8v6.8" />
        <path d="M29.4 22.6v6.8h-6.8" />
        <path d="M9.4 29.4H2.6v-6.8" />
      </g>

      {/* Snout, browline, arched back, folded haunch, belly — one path. */}
      <path
        fill="var(--flame, #d2612b)"
        d="M5.4 17.6c-.5-2.2.8-4.3 3.1-5.1.6-2.1 2.8-3.2 4.8-2.4
           3.1-1.6 7.2-1.2 10 1 3.2 2.5 4.5 6.1 3.3 8.8-.8 1.8-2.7 2.3-4 1.4
           -1.2-.8-1.5-2.2-1-3.4-3.1 2-8.5 2.3-12.3 1.1-1.7-.5-3.5-.9-3.9-1.4Z"
      />
      <g
        stroke="var(--flame, #d2612b)"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      >
        <path d="M9.8 19.9c-1.1 2-.9 3.9.5 4.7" />
        <path d="M10.3 24.6h3.2" />
        <path d="M24 22.6l.5 2.1-3 .4" />
      </g>

      {/* The eye is the whole face at this size. */}
      <circle cx="11.2" cy="12.4" r="2" fill="var(--ink-0, #0f1620)" />
      <circle cx="10.5" cy="11.7" r=".62" fill="var(--text, #ece4d7)" opacity=".85" />
    </svg>
  )
}
