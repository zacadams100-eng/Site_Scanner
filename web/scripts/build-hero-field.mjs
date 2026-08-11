/**
 * Build the hero's field sheet from the bundled basemap.
 *
 * The basemap is 608 kB, and the marketing homepage is 81 kB of JavaScript. A
 * hero that fetches the whole thing would cost more than the entire page it
 * decorates — so this decimates it to the few layers the sheet actually draws,
 * at the precision a background picture needs, and writes a much smaller file.
 *
 * Run from `npm run build` and `npm run predev`, so the asset cannot drift
 * from the basemap it is derived from. The output is generated and gitignored.
 */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'

const SRC = new URL('../public/basemap/england.json', import.meta.url)
const OUT_DIR = new URL('../public/hero/', import.meta.url)
const OUT = new URL('../public/hero/field.json', import.meta.url)

/** England and Wales, tight. The basemap covers Ireland and northern France
 *  too; a hero that opens on the Channel is a hero about the sea. */
const VIEW = { minLon: -6.1, minLat: 49.85, maxLon: 1.9, maxLat: 55.9 }

/** Coordinate precision. Three decimals is about 110 m — far finer than a
 *  hairline on a background canvas, and it halves the file. */
const PRECISION = 3

const round = (n) => Number(n.toFixed(PRECISION))

/**
 * Ramer–Douglas–Peucker.
 *
 * The coastline arrives with far more vertices than a 1600px-wide canvas can
 * resolve. Simplifying is not a quality loss here: below about a pixel of
 * tolerance the extra points are drawn on top of each other.
 */
function simplify(points, tolerance) {
  if (points.length < 3) return points
  let maxDist = 0, index = 0
  const [ax, ay] = points[0]
  const [bx, by] = points[points.length - 1]
  const dx = bx - ax, dy = by - ay
  const denom = Math.hypot(dx, dy) || 1
  for (let i = 1; i < points.length - 1; i++) {
    const [px, py] = points[i]
    const dist = Math.abs(dy * px - dx * py + bx * ay - by * ax) / denom
    if (dist > maxDist) { maxDist = dist; index = i }
  }
  if (maxDist <= tolerance) return [points[0], points[points.length - 1]]
  return [
    ...simplify(points.slice(0, index + 1), tolerance).slice(0, -1),
    ...simplify(points.slice(index), tolerance),
  ]
}

/**
 * Simplify a ring whose first and last point are the same.
 *
 * Douglas–Peucker measures every point against the line from the first to the
 * last. On a closed ring those are the same point, the baseline has no
 * direction, and the whole coastline collapses to two vertices — which is
 * exactly what happened the first time this ran: 0 rings out of 8.
 *
 * Splitting at the vertex farthest from the start gives each half a real
 * baseline, which is the standard fix.
 */
function simplifyRing(ring, tolerance) {
  const closed = ring.length > 3
    && ring[0][0] === ring[ring.length - 1][0]
    && ring[0][1] === ring[ring.length - 1][1]
  if (!closed) return simplify(ring, tolerance)

  const body = ring.slice(0, -1)
  let far = 0, best = -1
  for (let i = 1; i < body.length; i++) {
    const d = Math.hypot(body[i][0] - body[0][0], body[i][1] - body[0][1])
    if (d > best) { best = d; far = i }
  }
  const a = simplify(body.slice(0, far + 1), tolerance)
  const b = simplify(body.slice(far), tolerance)
  const merged = [...a.slice(0, -1), ...b]
  return [...merged, merged[0]]
}

const inView = ([lon, lat]) =>
  lon >= VIEW.minLon - 1 && lon <= VIEW.maxLon + 1
  && lat >= VIEW.minLat - 1 && lat <= VIEW.maxLat + 1

/** Rings of a polygon or multipolygon, flattened to plain coordinate lists. */
function ringsOf(geometry) {
  if (!geometry) return []
  if (geometry.type === 'Polygon') return geometry.coordinates
  if (geometry.type === 'MultiPolygon') return geometry.coordinates.flat()
  return []
}

function linesOf(geometry) {
  if (!geometry) return []
  if (geometry.type === 'LineString') return [geometry.coordinates]
  if (geometry.type === 'MultiLineString') return geometry.coordinates
  return []
}

const clean = (parts, tolerance, minPoints, ring = false) => parts
  .filter((p) => p.some(inView))
  .map((p) => (ring ? simplifyRing(p, tolerance) : simplify(p, tolerance))
    .map(([lon, lat]) => [round(lon), round(lat)]))
  .filter((p) => p.length >= minPoints)

const src = JSON.parse(readFileSync(SRC, 'utf8'))
const features = (layer) => src[layer]?.features ?? []

// Coastline. Kept as closed rings so the sheet can fill land as well as stroke
// it — the fill is what stops the hero reading as a wireframe.
const coast = clean(
  features('land').flatMap((f) => ringsOf(f.geometry)), 0.012, 8, true)

// Rivers, at a coarser tolerance: they are hairlines and read as gesture.
const rivers = clean(
  features('rivers').flatMap((f) => linesOf(f.geometry)), 0.02, 4)

// A handful of lakes, for the same reason the coastline is filled.
const lakes = clean(
  features('lakes').flatMap((f) => ringsOf(f.geometry)), 0.015, 5, true)

/*
 * Places. Only English and Welsh ones, largest first — the sheet labels a
 * dozen and the selection has to be the dozen a reader would recognise.
 * Filtered here rather than in the browser so the payload carries no names
 * that will never be drawn.
 */
const places = features('places')
  .map((f) => ({
    name: f.properties?.name ?? '',
    pop: f.properties?.pop_max ?? 0,
    country: f.properties?.adm0name ?? '',
    lon: f.geometry?.coordinates?.[0],
    lat: f.geometry?.coordinates?.[1],
  }))
  .filter((p) => p.name && typeof p.lon === 'number'
    && p.lon >= VIEW.minLon && p.lon <= VIEW.maxLon
    && p.lat >= VIEW.minLat && p.lat <= VIEW.maxLat
    && /United Kingdom|England|Wales/i.test(p.country))
  .sort((a, b) => b.pop - a.pop)
  .slice(0, 28)
  .map((p) => ({
    type: 'Feature',
    properties: { name: p.name, population: p.pop },
    geometry: { type: 'Point', coordinates: [round(p.lon), round(p.lat)] },
  }))

const out = {
  attribution: src.attribution,
  note: 'Generated by scripts/build-hero-field.mjs — do not edit. '
    + 'Decimated from public/basemap/england.json for the homepage hero.',
  view: VIEW,
  coast,
  rivers,
  lakes,
  places,
}

mkdirSync(OUT_DIR, { recursive: true })
writeFileSync(OUT, JSON.stringify(out))
const kb = (n) => `${Math.round(n / 1024)} kB`
console.log(
  `hero field: ${coast.length} coast rings, ${rivers.length} rivers, `
  + `${places.length} places — ${kb(JSON.stringify(out).length)} `
  + `(from ${kb(readFileSync(SRC).length)})`)
