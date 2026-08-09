/**
 * A saved site drawn as its own outline.
 *
 * The gallery's job is recognition, and people do not recognise a site by its
 * name — they recognise the shape they traced. "Manor Farm" and "Manor Farm 2"
 * are indistinguishable in a list; a long thin roadside strip and a fat
 * rectangle are not.
 *
 * So the thumbnail is the boundary itself, drawn from the geometry already in
 * `localStorage`. No tiles, no network, no screenshot to capture or store — it
 * works offline, it costs nothing, and it looks like what it is: a traced
 * outline in a field notebook.
 */

/** Padding inside the box, in the same units as the box. Keeps a hairline
 *  stroke off the edge and stops a long thin site touching the sides. */
const INSET = 0.08

/**
 * Longitude is narrower than latitude, and ignoring that squashes every site.
 *
 * At 51°N a degree of longitude covers about 0.63 of the ground a degree of
 * latitude does. Normalising the raw coordinates to a box would stretch every
 * English outline horizontally by roughly 1.6x — so a square field would draw
 * as a landscape rectangle, and the shape is the entire point of doing this.
 */
export function lonScale(lat: number): number {
  return Math.cos((lat * Math.PI) / 180)
}

export interface ThumbBox {
  width: number
  height: number
}

/**
 * An SVG path for a polygon, fitted to `box` with its proportions intact.
 *
 * Returns null when there is nothing meaningful to draw, which the caller must
 * handle — a card with no thumbnail is better than a card with a dot in the
 * middle of it pretending to be a site.
 */
export function thumbnailPath(
  geometry: GeoJSON.Polygon | null | undefined,
  box: ThumbBox,
): string | null {
  const ring = geometry?.coordinates?.[0]
  if (!ring || ring.length < 3) return null

  const lats = ring.map((p) => p[1])
  const midLat = (Math.min(...lats) + Math.max(...lats)) / 2
  const k = Math.max(0.1, lonScale(midLat))

  // Project to a local flat space where x and y cover comparable ground.
  const pts = ring.map(([lng, lat]) => [lng * k, lat] as [number, number])

  const xs = pts.map((p) => p[0])
  const ys = pts.map((p) => p[1])
  const west = Math.min(...xs)
  const east = Math.max(...xs)
  const south = Math.min(...ys)
  const north = Math.max(...ys)

  const spanX = east - west
  const spanY = north - south
  if (!Number.isFinite(spanX) || !Number.isFinite(spanY)) return null
  if (spanX <= 0 && spanY <= 0) return null

  const inset = Math.min(box.width, box.height) * INSET
  const usableW = box.width - inset * 2
  const usableH = box.height - inset * 2

  // One scale for both axes, so the drawing keeps the site's proportions. A
  // site fitted to the box on each axis independently is a different shape,
  // and the shape is what the user is looking for.
  const scale = Math.min(
    spanX > 0 ? usableW / spanX : Infinity,
    spanY > 0 ? usableH / spanY : Infinity,
  )
  const safeScale = Number.isFinite(scale) ? scale : 1

  // Centre whatever is left over, so a wide site sits in the middle of the
  // card rather than along its top edge.
  const drawnW = spanX * safeScale
  const drawnH = spanY * safeScale
  const offsetX = inset + (usableW - drawnW) / 2
  const offsetY = inset + (usableH - drawnH) / 2

  const d = pts.map(([x, y], i) => {
    const px = offsetX + (x - west) * safeScale
    // SVG y grows downward and latitude grows upward, so north has to end up
    // at the top. Forgetting this draws every site upside down, which is
    // subtle enough to ship and wrong enough to matter for recognition.
    const py = offsetY + (north - y) * safeScale
    return `${i === 0 ? 'M' : 'L'}${px.toFixed(1)} ${py.toFixed(1)}`
  })

  return d.join(' ') + ' Z'
}

/**
 * "3 days ago". Coarse on purpose.
 *
 * A saved site is not an event log; the reader wants to know whether this is
 * the thing they were working on yesterday or something from last term.
 * Minute-level precision would imply a timeline nobody is tracking.
 */
export function relativeTime(then: number, now: number = Date.now()): string {
  const s = Math.max(0, (now - then) / 1000)
  if (s < 90) return 'just now'
  const m = s / 60
  if (m < 60) return `${Math.round(m)} min ago`
  const h = m / 60
  if (h < 24) return `${Math.round(h)} hour${Math.round(h) === 1 ? '' : 's'} ago`
  const d = h / 24
  if (d < 7) return `${Math.round(d)} day${Math.round(d) === 1 ? '' : 's'} ago`
  if (d < 31) {
    const w = Math.round(d / 7)
    return `${w} week${w === 1 ? '' : 's'} ago`
  }
  const mo = Math.round(d / 30.44)
  if (d < 365) return `${mo} month${mo === 1 ? '' : 's'} ago`
  const y = Math.round(d / 365.25)
  return `${y} year${y === 1 ? '' : 's'} ago`
}
