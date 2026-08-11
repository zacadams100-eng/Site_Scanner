/**
 * Geometry for the hero field sheet.
 *
 * Everything here is pure and deterministic: the same seed draws the same
 * sheet on every load, on every machine. That matters more than it sounds —
 * a hero that reshuffles itself each visit is decoration, and this one is
 * meant to read as a specific place recorded by a specific instrument.
 *
 * Kept apart from the component so the maths can be tested without a canvas.
 */

/* ---------------------------------------------------------------- projection */

export interface Bbox { minLon: number; minLat: number; maxLon: number; maxLat: number }

export interface Projection {
  (lon: number, lat: number): [number, number]
  scale: number
}

/**
 * Equirectangular, corrected for latitude.
 *
 * Not a real projection for measurement — the application uses proper CRS
 * handling for that. This draws a picture, and at England's latitude a cosine
 * correction is the difference between a recognisable coastline and one
 * stretched sideways.
 */
export function project(bbox: Bbox, width: number, height: number, pad = 0): Projection {
  const midLat = (bbox.minLat + bbox.maxLat) / 2
  const k = Math.cos((midLat * Math.PI) / 180)
  const spanX = (bbox.maxLon - bbox.minLon) * k
  const spanY = bbox.maxLat - bbox.minLat
  const scale = Math.min((width - pad * 2) / spanX, (height - pad * 2) / spanY)
  const offX = (width - spanX * scale) / 2
  const offY = (height - spanY * scale) / 2

  const fn = ((lon: number, lat: number): [number, number] => [
    offX + (lon - bbox.minLon) * k * scale,
    // Screen y grows downward; latitude grows upward.
    offY + (bbox.maxLat - lat) * scale,
  ]) as Projection
  fn.scale = scale
  return fn
}

/* --------------------------------------------------------------------- noise */

/** Integer hash. Deterministic across engines — no Math.random anywhere in
 *  this module, so the sheet is reproducible and testable. */
function hash(x: number, y: number, seed: number): number {
  // All three multipliers are below 2^31 so they are exactly representable as
  // doubles. The original third constant was a 64-bit prime, which JavaScript
  // silently rounded — a hash whose constant is not the constant you wrote is
  // still deterministic, but for a reason nobody can reconstruct later.
  let h = x * 374761393 + y * 668265263 + seed * 1274126177
  h = (h ^ (h >> 13)) * 1274126177
  return ((h ^ (h >> 16)) >>> 0) / 4294967295
}

const smooth = (t: number) => t * t * (3 - 2 * t)

function valueNoise(x: number, y: number, seed: number): number {
  const xi = Math.floor(x), yi = Math.floor(y)
  const xf = x - xi, yf = y - yi
  const u = smooth(xf), v = smooth(yf)
  const a = hash(xi, yi, seed), b = hash(xi + 1, yi, seed)
  const c = hash(xi, yi + 1, seed), d = hash(xi + 1, yi + 1, seed)
  return (a * (1 - u) + b * u) * (1 - v) + (c * (1 - u) + d * u) * v
}

/**
 * Fractal noise standing in for elevation.
 *
 * This is **not** terrain data and is never labelled as an elevation in the
 * interface — the contour lines it produces are cartographic texture, and the
 * hero says "FIELD SHEET" rather than quoting metres. Inventing a number that
 * looks like a measurement is the one thing this product cannot do, including
 * in its own marketing.
 */
export function fbm(x: number, y: number, seed = 1, octaves = 5): number {
  let sum = 0, amp = 1, freq = 1, norm = 0
  for (let i = 0; i < octaves; i++) {
    sum += valueNoise(x * freq, y * freq, seed + i) * amp
    norm += amp
    amp *= 0.5
    freq *= 2
  }
  return sum / norm
}

/** A sampled scalar field, row-major, `w * h` values in 0..1. */
export interface Field { w: number; h: number; data: Float32Array }

export function buildField(w: number, h: number, seed = 1, scale = 3.2): Field {
  const data = new Float32Array(w * h)
  let lo = Infinity, hi = -Infinity
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      // Aspect-corrected sampling, or the "terrain" stretches with the canvas.
      const v = fbm((x / w) * scale, (y / h) * scale * (h / w), seed)
      data[y * w + x] = v
      if (v < lo) lo = v
      if (v > hi) hi = v
    }
  }

  /*
   * Stretch to the full 0..1 range.
   *
   * Summing five octaves averages five uniform samples, and averaging pulls
   * everything towards the middle — the raw field spanned roughly 0.35 to
   * 0.65. The contour levels are absolute, so the outer ones had nothing to
   * cross and simply produced no line: the first version of this drew four
   * contours where it claimed eleven, which on screen looked like none.
   */
  const span = hi - lo
  if (span > 1e-6) {
    // Clamped, because the values are stored as float32 and read back as
    // float64: the minimum came out at -8e-9 rather than 0, which is nothing
    // to look at and everything to a caller that trusts the 0..1 contract.
    for (let i = 0; i < data.length; i++) {
      data[i] = Math.min(1, Math.max(0, (data[i] - lo) / span))
    }
  }
  return { w, h, data }
}

/* ---------------------------------------------------------------- contours */

export type Segment = [number, number, number, number]

/**
 * Marching squares, returning one iso-line level as unjoined segments.
 *
 * Segments rather than stitched polylines: they are drawn, not analysed, and
 * stitching costs code and time to produce an identical picture. The saddle
 * cases (5 and 10) are resolved consistently rather than by centre-sampling,
 * which is the usual source of contours that cross each other.
 */
export function marchingSquares(field: Field, level: number): Segment[] {
  const { w, h, data } = field
  const out: Segment[] = []
  const at = (x: number, y: number) => data[y * w + x]
  // Linear interpolation along an edge to where the field crosses `level`.
  const lerp = (a: number, b: number) => (Math.abs(b - a) < 1e-9 ? 0.5 : (level - a) / (b - a))

  for (let y = 0; y < h - 1; y++) {
    for (let x = 0; x < w - 1; x++) {
      const tl = at(x, y), tr = at(x + 1, y), br = at(x + 1, y + 1), bl = at(x, y + 1)
      const idx = (tl > level ? 8 : 0) | (tr > level ? 4 : 0) | (br > level ? 2 : 0) | (bl > level ? 1 : 0)
      if (idx === 0 || idx === 15) continue

      const top: [number, number] = [x + lerp(tl, tr), y]
      const right: [number, number] = [x + 1, y + lerp(tr, br)]
      const bottom: [number, number] = [x + lerp(bl, br), y + 1]
      const left: [number, number] = [x, y + lerp(tl, bl)]
      const seg = (a: [number, number], b: [number, number]) =>
        out.push([a[0], a[1], b[0], b[1]])

      switch (idx) {
        case 1: case 14: seg(left, bottom); break
        case 2: case 13: seg(bottom, right); break
        case 3: case 12: seg(left, right); break
        case 4: case 11: seg(top, right); break
        case 6: case 9: seg(top, bottom); break
        case 7: case 8: seg(left, top); break
        case 5: seg(left, top); seg(bottom, right); break
        case 10: seg(left, bottom); seg(top, right); break
      }
    }
  }
  return out
}

/** Evenly spaced levels, excluding the extremes where contours degenerate into
 *  noise around the field's flattest regions. */
export function contourLevels(count: number, from = 0.28, to = 0.72): number[] {
  if (count < 1) return []
  if (count === 1) return [(from + to) / 2]
  return Array.from({ length: count }, (_, i) => from + ((to - from) * i) / (count - 1))
}

/* ------------------------------------------------------------------- labels */

/** A place chosen for the sheet, with the coordinates it is actually at. */
export interface FieldLabel {
  name: string
  lon: number
  lat: number
  /** 0-based order of appearance, so labels arrive in sequence rather than
   *  all at once. */
  order: number
}

export interface PlaceFeature {
  properties?: { name?: string; NAME?: string; population?: number; POP_MAX?: number }
  geometry?: { coordinates?: [number, number] }
}

/**
 * Pick the labels for the sheet.
 *
 * Largest first, then thinned so no two sit on top of each other. A hero with
 * eight overlapping town names reads as a bug; the thinning is what makes it
 * look surveyed rather than dumped.
 */
export function pickLabels(
  places: PlaceFeature[],
  count: number,
  minSeparationDeg = 0.9,
): FieldLabel[] {
  const named = places
    .map((f) => ({
      name: f.properties?.name ?? f.properties?.NAME ?? '',
      pop: f.properties?.population ?? f.properties?.POP_MAX ?? 0,
      lon: f.geometry?.coordinates?.[0],
      lat: f.geometry?.coordinates?.[1],
    }))
    .filter((p): p is { name: string; pop: number; lon: number; lat: number } =>
      !!p.name && typeof p.lon === 'number' && typeof p.lat === 'number')
    .sort((a, b) => b.pop - a.pop)

  const kept: FieldLabel[] = []
  for (const p of named) {
    if (kept.length >= count) break
    const clash = kept.some((k) =>
      Math.hypot(k.lon - p.lon, k.lat - p.lat) < minSeparationDeg)
    if (clash) continue
    kept.push({ name: p.name, lon: p.lon, lat: p.lat, order: kept.length })
  }
  return kept
}

/** Coordinates the way field equipment prints them: fixed width, signed, and
 *  never more precision than the thing being described deserves. */
export function formatCoord(value: number, axis: 'lat' | 'lon'): string {
  const hemi = axis === 'lat' ? (value >= 0 ? 'N' : 'S') : (value >= 0 ? 'E' : 'W')
  return `${Math.abs(value).toFixed(3)}°${hemi}`
}
