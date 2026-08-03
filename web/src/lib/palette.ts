/**
 * The palette, for everything that cannot read a CSS variable.
 *
 * Three renderers here draw outside the DOM — MapLibre paint properties, the
 * timeline's 2D canvas, and Observable Plot's generated SVG — and each one
 * wants a literal colour string. Before this file they each carried their own
 * hex codes, so a palette change fixed the chrome and left the data looking
 * like the old brand.
 *
 * These values mirror index.css. That duplication is deliberate: reading the
 * computed styles at paint time would couple every redraw to layout, and the
 * timeline redraws on every scrub. Keep the two in step by hand — the token
 * names match one-to-one.
 */

export const PALETTE = {
  ink0: '#0f1620',
  ink1: '#16202c',
  ink4: '#2e3d51',

  text3: '#8a9099',

  flame: '#d2612b',
  flameLift: '#e88a52',
  flameDeep: '#a8461a',

  denim: '#4a7ba7',
  sky: '#7fc0e4',
  sand: '#d9a566',
  rose: '#cf7f8d',
  absent: '#46566d',

  /** Hairline, matching --line. */
  hairline: 'rgba(198,216,242,0.055)',
} as const

/**
 * The sequential ramp for map cells: cool ground to warm light, the same
 * journey the reference photography makes from sky to subject.
 *
 * Luminance rises monotonically across all six stops, which is the property
 * that actually matters — users learn "lighter = more" once and apply it to
 * all 118 factors. That constraint is why the frog's own orange is not the top
 * stop: at #d2612b it is darker than the teal below it, and a ramp that dips
 * in the middle cannot be read.
 *
 * The floor is #1a283a rather than the ground colour. A cell holding the
 * lowest value in range is still an observation, and it has to look different
 * from a cell holding nothing at all.
 */
export const RAMP: readonly [number, number, number][] = [
  [26, 40, 58],
  [34, 72, 106],
  [54, 116, 148],
  [100, 160, 174],
  [190, 172, 136],
  [246, 192, 146],
]

/**
 * Stable colour per series, for multi-line charts and legends.
 *
 * The flame leads so the primary series matches the accent and the scrubber;
 * the rest fan out in hue at similar lightness, so no series shouts.
 */
export const SERIES_COLORS = [
  PALETTE.flameLift, PALETTE.sky, '#b9c48f', '#98a8dc',
  '#d29ec0', PALETTE.sand, '#7fb8a0', '#c4877a',
  '#9db4d9', '#c2a6d4', '#a8c47f', '#d4a06f',
] as const
