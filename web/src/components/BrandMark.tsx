/**
 * The dart frog, drawn as a specimen plate rather than a character.
 *
 * A flat silhouette with the two things that make a dart frog readable at any
 * size — the bulging eyes above the head line, and the splayed legs — plus two
 * contour arcs across the back, which is the one place the map shows up in the
 * mark. No gradient, no outline finer than 1.5px, nothing that turns to grey
 * mush when the browser paints it into a 16px tab.
 *
 * The geometry is duplicated in `public/favicon.svg` on purpose: the favicon
 * has to be a static file the browser can fetch before any JavaScript runs.
 * If one changes, change both.
 */
export default function BrandMark({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 32 32" role="img" aria-label="Site Scanner">
      {/* Legs — drawn first so the body sits over the joints. */}
      <g stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" fill="none">
        <path d="M10 21.5 6 26" />
        <path d="M22 21.5 26 26" />
        <path d="M12.5 24.5 11.5 29" />
        <path d="M19.5 24.5 20.5 29" />
      </g>
      {/* Toes — contour ticks, the frog's grip on the ground. */}
      <g stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" fill="none" opacity=".85">
        <path d="M4 26.6h3.4M9.9 29.4h3.2M18.9 29.4h3.2M24.6 26.6H28" />
      </g>

      {/* Body */}
      <path
        d="M16 8c4.6 0 8.2 3.6 8.6 8.6.4 4.6-2.4 8.6-8.6 8.6s-9-4-8.6-8.6C7.8 11.6 11.4 8 16 8Z"
        fill="currentColor"
      />
      {/* Contour rings on the back: concentric, the way a dome is drawn on a
          topographic sheet. Arcs were tried first and read as a mouth, which
          made the mark a cartoon. */}
      <g stroke="var(--paper-100, #f8f6f2)" strokeWidth="1.1" fill="none" opacity=".5">
        <ellipse cx="16" cy="18.2" rx="6" ry="4.2" />
        <ellipse cx="16" cy="18.2" rx="3.2" ry="2.2" />
      </g>

      {/* Eyes, above the head line — the read that says "frog" at 16px. */}
      <circle cx="11.4" cy="9.6" r="4.1" fill="currentColor" />
      <circle cx="20.6" cy="9.6" r="4.1" fill="currentColor" />
      <circle cx="11.4" cy="9.6" r="2.2" fill="var(--paper-000, #fff)" />
      <circle cx="20.6" cy="9.6" r="2.2" fill="var(--paper-000, #fff)" />
      <circle cx="11.4" cy="9.6" r="1.1" fill="currentColor" />
      <circle cx="20.6" cy="9.6" r="1.1" fill="currentColor" />
    </svg>
  )
}
