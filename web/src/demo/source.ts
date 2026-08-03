import * as turf from '@turf/turf'
import type {
  AnnualRow, Base, Catalog, CellsResponse, Factor, Point, Series, SeriesResponse,
} from '../types'
import catalogJson from './catalog.json'

/**
 * The demo data source — the app with no server behind it.
 *
 * This is a port of the mock backend's generator (`series.py`) into the
 * browser, so a static build of the frontend is fully usable on its own: draw
 * anything, get a plausible answer, with no API to deploy.
 *
 * **It is a port in behaviour, not in output.** The Python side seeds
 * `random.Random` from a SHA-256 digest; reproducing Mersenne Twister here to
 * get byte-identical numbers would be a lot of code in service of a property
 * nothing needs. What is preserved is everything that makes the data *read*
 * correctly:
 *
 *   - determinism — the same shape always returns the same numbers, so the
 *     report is stable across reloads and a saved project reopens unchanged
 *   - site character — nearby shapes behave alike, and a northern upland site
 *     differs from a southern city
 *   - coherence — NDVI and tree cover agree; heat and built-up agree
 *   - honest gaps — cloud-limited factors have no answer in English winters,
 *     and those months are holes rather than interpolated lines
 *
 * The catalogue itself is not generated: `catalog.json` is the real response,
 * captured verbatim, so all 118 factors carry their true units, ranges,
 * licences and provenance.
 *
 * Everything here is generated. Nothing is an observation of anything.
 */

const catalog = catalogJson as unknown as Catalog

const FACTOR_BY_ID = new Map<string, Factor>(catalog.factors.map((f) => [f.id, f]))
const BASE_BY_ID = new Map<string, Base>(catalog.bases.map((b) => [b.id, b]))

const MAX_AREA_HA = 250_000
const GAP_THRESHOLD = 0.15
const CLOUD_LIMITED_BASES = new Set(['sentinel2_sr', 'modis_lst'])

const SEASON_PEAK: Record<string, number> = {
  Vegetation: 7.0, Temperature: 7.5, Water: 0.5,
  'Air quality': 1.0, Radar: 7.0, 'Night lights': 0.0,
}
const SEASON_AMPLITUDE: Record<string, number> = {
  Vegetation: 0.34, Temperature: 0.40, Water: 0.28, 'Air quality': 0.22,
  Radar: 0.12, 'Night lights': 0.30, 'People & economy': 0.03,
}

/** Matches the backend's error text exactly — the UI surfaces it verbatim. */
export class DemoError extends Error {
  readonly status: number
  constructor(message: string, status = 400) {
    super(message)
    this.status = status
  }
}

// ---------------------------------------------------------------------------
// Deterministic noise
// ---------------------------------------------------------------------------

/** xmur3: string -> well-mixed 32-bit seed. */
function seedFrom(key: string): number {
  let h = 1779033703 ^ key.length
  for (let i = 0; i < key.length; i++) {
    h = Math.imul(h ^ key.charCodeAt(i), 3432918353)
    h = (h << 13) | (h >>> 19)
  }
  h = Math.imul(h ^ (h >>> 16), 2246822507)
  h = Math.imul(h ^ (h >>> 13), 3266489909)
  return (h ^= h >>> 16) >>> 0
}

/** mulberry32 — small, fast, and good enough that neighbouring cells do not
 *  visibly correlate. */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), 1 | t)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const key = (...parts: (string | number)[]) => parts.join('|')

/** One stable number in [0, 1) for a given set of parts. */
function unitNoise(...parts: (string | number)[]): number {
  return mulberry32(seedFrom(key(...parts)))()
}

function rng(...parts: (string | number)[]): () => number {
  return mulberry32(seedFrom(key(...parts)))
}

// ---------------------------------------------------------------------------
// Site character
// ---------------------------------------------------------------------------

interface Site {
  urbanity: number; wetness: number; elevation: number
  northness: number; affluence: number
}

/**
 * A stable "personality" for a location. Without it every drawn shape returns
 * statistically identical data and the map stops meaning anything.
 */
function siteCharacter(lng: number, lat: number): Site {
  const r = rng('site', lng.toFixed(3), lat.toFixed(3))
  const northness = (lat - 49.9) / (55.8 - 49.9)
  const urbanity = r()
  const wetness = 0.35 + 0.5 * r() + 0.15 * northness
  const elevation = Math.pow(r(), 1.6)
  const affluence = r()
  return { urbanity, wetness, elevation, northness, affluence }
}

/** Ties related factors to the same underlying character, so NDVI and tree
 *  cover agree, and heat and built-up agree. */
function coherentPosition(group: string, site: Site): number {
  if (group === 'Temperature') return 0.75 - 0.45 * site.northness + 0.2 * site.urbanity
  if (group === 'Water' || group === 'Flood & water') {
    return 0.25 + 0.55 * site.wetness - 0.3 * site.elevation
  }
  if (group === 'Terrain') return site.elevation
  if (group === 'People & economy') return 0.2 + 0.6 * site.affluence
  if (group === 'Air quality' || group === 'Built environment' || group === 'Night lights') {
    return 0.1 + 0.8 * site.urbanity
  }
  if (group === 'Vegetation' || group === 'Land cover' || group === 'Designations') {
    return 0.8 - 0.55 * site.urbanity
  }
  return 0.5
}

const BUILT_LIKE = new Set([
  'lc_built_pct', 'impervious_pct', 'built_pct', 'building_density',
  'road_density', 'population_density', 'no2', 'nightlight_radiance',
])
const GREEN_LIKE = new Set(['lc_tree_pct', 'lc_crop_pct', 'lc_grass_pct', 'ndvi', 'evi'])

function baseline(factor: Factor, site: Site, areaHa: number): number {
  const lo = factor.lo ?? 0
  const hi = factor.hi ?? 1
  const span = hi - lo
  const u = site.urbanity

  let pos = unitNoise('base', factor.id, site.urbanity.toFixed(4), site.northness.toFixed(4))
  pos = 0.35 * pos + 0.65 * coherentPosition(factor.group, site)

  if (BUILT_LIKE.has(factor.id)) pos = Math.min(1, 0.15 + 0.85 * u)
  else if (GREEN_LIKE.has(factor.id)) pos = Math.max(0, 0.85 - 0.6 * u) * (0.7 + 0.6 * pos)

  // Small areas are more extreme; large ones regress toward the middle because
  // they average over more varied ground. Real, and it matters to anyone
  // comparing a field against a county.
  const pull = Math.min(1, areaHa / 20000)
  pos = pos * (1 - 0.45 * pull) + 0.5 * (0.45 * pull)

  return lo + span * Math.max(0, Math.min(1, pos))
}

/** Long-run drift as a fraction of range per year. A 15-year timeline is
 *  pointless if nothing trends. */
function trendPerYear(factor: Factor, site: Site): number {
  const r = rng('trend', factor.id, site.urbanity.toFixed(3))
  const jitter = (r() - 0.5) * 0.004
  const fid = factor.id

  if (factor.group === 'Temperature') return 0.006 + jitter
  if (fid === 'frost_days') return -0.008 + jitter
  if (['lc_built_pct', 'built_pct', 'impervious_pct', 'building_density'].includes(fid)) {
    return 0.004 * (0.3 + site.urbanity) + jitter
  }
  if (fid === 'avg_sale_price' || fid === 'price_per_m2') return 0.021 + jitter
  // Air quality has genuinely improved.
  if (['no2', 'pm25', 'pm10', 'so2'].includes(fid)) return -0.010 + jitter
  if (fid === 'lc_tree_pct' || fid === 'ancient_woodland_pct') return 0.001 + jitter
  if (fid === 'lc_crop_pct' || fid === 'lc_grass_pct') return -0.002 + jitter
  return jitter
}

function seasonal(factor: Factor, month: number): number {
  const amp = SEASON_AMPLITUDE[factor.group] ?? 0
  if (amp === 0) return 0
  const peak = SEASON_PEAK[factor.group] ?? 7
  const swing = Math.cos(((month - peak) / 12) * 2 * Math.PI)

  const fid = factor.id
  if (fid === 'frost_days') return -amp * swing * 1.6
  // Inverse of the Water group's phase.
  if (['dry_days', 'sunshine_hours', 'o3', 'solar_ghi'].includes(fid)) return -amp * swing
  if (fid === 'growing_degree_days') return amp * Math.max(0, swing) * 1.8
  return amp * swing
}

/**
 * How much of the area produced a usable observation. English winters are
 * genuinely cloudy — December optical coverage is often under 20%, and the
 * interface has to show that rather than pretend a January NDVI is as solid
 * as a July one.
 */
function validFraction(factor: Factor, year: number, month: number, site: Site): number {
  if (!CLOUD_LIMITED_BASES.has(factor.base)) return 1
  const seasonalClear = 0.5 + 0.42 * Math.cos(((month - 7) / 12) * 2 * Math.PI)
  const noise = unitNoise('cloud', factor.base, year, month, site.wetness.toFixed(3))
  let frac = seasonalClear * (0.55 + 0.75 * noise)
  frac -= 0.12 * site.wetness
  return Math.max(0, Math.min(1, frac))
}

function categoricalValue(factor: Factor, year: number, site: Site): string {
  const classes = catalog.class_values[factor.id] ?? ['Unknown']
  let weights: number[]
  if (factor.id === 'lc_dominant') {
    const u = site.urbanity
    weights = [Math.max(0.02, 0.9 - u), 0.12, Math.max(0.05, 0.7 - 0.4 * u),
               Math.max(0.05, 0.8 - 0.6 * u), 0.1 + 1.4 * u, 0.05, 0.08, 0.05]
  } else {
    weights = classes.map(() => 1)
  }
  const w = classes.map((_, i) => weights[i] ?? 1)
  const total = w.reduce((s, v) => s + v, 0)
  // The class holds for five years at a time — land cover does not flip yearly.
  let pick = unitNoise('cat', factor.id, site.urbanity.toFixed(3),
                       site.northness.toFixed(3), Math.floor(year / 5)) * total
  for (let i = 0; i < classes.length; i++) {
    pick -= w[i]
    if (pick <= 0) return classes[i]
  }
  return classes[classes.length - 1]
}

// ---------------------------------------------------------------------------
// Series
// ---------------------------------------------------------------------------

function round(v: number, dp: number): number {
  const f = Math.pow(10, dp)
  return Math.round(v * f) / f
}

function generatePoints(
  factor: Factor, lng: number, lat: number, areaHa: number, steps: string[],
): Point[] {
  const site = siteCharacter(lng, lat)
  const cadence = factor.cadence
  const stepped = cadence === 'annual' || cadence === '5 years' || cadence === 'periodic'

  if (factor.kind === 'categorical') {
    return steps.map((step) => {
      const [year, month] = step.split('-').map(Number)
      return {
        t: step,
        value: categoricalValue(factor, year, site),
        valid_fraction: round(validFraction(factor, year, month, site), 3),
        // A yearly product shown on a monthly axis is stepped, and the months
        // between observations are marked as such.
        interpolated: stepped && month !== 1,
      }
    })
  }

  const lo = factor.lo ?? 0
  const hi = factor.hi ?? 1
  const span = hi - lo
  const base = baseline(factor, site, areaHa)
  const trend = trendPerYear(factor, site)
  const firstYear = Number(steps[0].slice(0, 4))

  return steps.map((step) => {
    const [year, month] = step.split('-').map(Number)
    let value: number
    let valid: number
    let interpolated: boolean

    if (cadence === 'static') {
      value = base
      valid = 1
      interpolated = false
    } else {
      // Static-in-year products hold their January value all year.
      const sampleMonth = stepped ? 1 : month
      const sampleYear = cadence === '5 years' ? year - (year % 5) : year

      const drift = trend * (sampleYear - firstYear) * span
      const season = seasonal(factor, sampleMonth) * span
      const wobble = (unitNoise('v', factor.id, sampleYear, sampleMonth,
                                lng.toFixed(3), lat.toFixed(3)) - 0.5) * 0.09 * span

      value = base + drift + season + wobble
      valid = validFraction(factor, year, month, site)
      interpolated = stepped && month !== 1
    }

    value = Math.max(lo, Math.min(hi, value))

    // The honest gap. Cloud-limited factors simply have no answer some months,
    // and the chart must show a hole rather than a straight line.
    if (valid < GAP_THRESHOLD) {
      return { t: step, value: null, valid_fraction: round(valid, 3), interpolated: false }
    }
    return {
      t: step, value: round(value, 4),
      valid_fraction: round(valid, 3), interpolated,
    }
  })
}

/**
 * Collapse a monthly series into one row per year. `months_observed` is what
 * stops a year built from two cloud-free Julys looking as authoritative as one
 * built from twelve months.
 */
function annualRollup(points: Point[], kind: Factor['kind']): AnnualRow[] {
  const byYear = new Map<number, Point[]>()
  for (const p of points) {
    const y = Number(p.t.slice(0, 4))
    const list = byYear.get(y)
    if (list) list.push(p)
    else byYear.set(y, [p])
  }

  const rows: AnnualRow[] = []
  for (const year of [...byYear.keys()].sort((a, b) => a - b)) {
    const all = byYear.get(year)!
    const pts = all.filter((p) => p.value !== null)
    const total = all.length

    if (!pts.length) {
      rows.push({ year, value: null, min: null, max: null,
                  months_observed: 0, months_total: total, confidence: 0 })
      continue
    }

    if (kind === 'categorical') {
      const counts = new Map<string, number>()
      for (const p of pts) {
        const v = String(p.value)
        counts.set(v, (counts.get(v) ?? 0) + 1)
      }
      let modal = ''
      let best = -1
      for (const [v, n] of counts) if (n > best) { best = n; modal = v }
      rows.push({
        year, value: modal, min: null, max: null,
        months_observed: pts.length, months_total: total,
        confidence: round(pts.reduce((s, p) => s + p.valid_fraction, 0) / pts.length, 3),
      })
      continue
    }

    // Weight by valid_fraction: a month where 90% of pixels were clear should
    // count for more than one where 20% were.
    const weights = pts.map((p) => Math.max(0.01, p.valid_fraction))
    const values = pts.map((p) => p.value as number)
    const mean = values.reduce((s, v, i) => s + v * weights[i], 0)
      / weights.reduce((s, w) => s + w, 0)

    rows.push({
      year, value: round(mean, 4),
      min: round(Math.min(...values), 4),
      max: round(Math.max(...values), 4),
      months_observed: pts.length, months_total: total,
      confidence: round(weights.reduce((s, w) => s + w, 0) / weights.length, 3),
    })
  }
  return rows
}

// ---------------------------------------------------------------------------
// Geometry
// ---------------------------------------------------------------------------

/** Same checks and the same wording as the backend, so the demo fails the way
 *  the real thing does. */
function validate(geometry: GeoJSON.Polygon): { lng: number; lat: number; areaHa: number } {
  const areaHa = turf.area(geometry as never) / 10_000
  if (!(areaHa > 0)) throw new DemoError('That shape has no area — try drawing it again.')
  if (areaHa > MAX_AREA_HA) {
    throw new DemoError(
      `That area is ${Math.round(areaHa).toLocaleString('en-GB')} ha, which is larger than the `
      + `${MAX_AREA_HA.toLocaleString('en-GB')} ha interactive limit. Draw something smaller, `
      + 'or save it as a project to run in the background.',
    )
  }
  const c = turf.centroid(geometry as never).geometry.coordinates
  const [lng, lat] = c as [number, number]
  const b = catalog.coverage.bbox
  if (!(lng >= b.west && lng <= b.east && lat >= b.south && lat <= b.north)) {
    throw new DemoError(
      'That area is outside England. Site Scanner only covers England at the moment.',
    )
  }
  return { lng, lat, areaHa }
}

function ringOf(geometry: GeoJSON.Polygon): number[][] {
  return geometry.coordinates[0] as number[][]
}

/** Ray casting — clips the grid to the drawn shape so a freehand outline does
 *  not come back as its bounding box. */
function pointInRing(x: number, y: number, ring: number[][]): boolean {
  let inside = false
  for (let i = 0; i < ring.length - 1; i++) {
    const [x1, y1] = ring[i]
    const [x2, y2] = ring[i + 1]
    if ((y1 > y) !== (y2 > y)) {
      const xint = ((x2 - x1) * (y - y1)) / (y2 - y1) + x1
      if (x < xint) inside = !inside
    }
  }
  return inside
}

// ---------------------------------------------------------------------------
// The three endpoints
// ---------------------------------------------------------------------------

export function demoCatalog(): Catalog {
  return catalog
}

export function demoSeries(geometry: GeoJSON.Polygon, factorIds: string[]): SeriesResponse {
  const { lng, lat, areaHa } = validate(geometry)
  const steps = catalog.time.steps

  const series: Record<string, Series> = {}
  for (const id of factorIds) {
    const factor = FACTOR_BY_ID.get(id)
    if (!factor) continue
    const points = generatePoints(factor, lng, lat, areaHa, steps)
    series[id] = {
      factor_id: id,
      // Never claim otherwise: every number here was invented by the code
      // above, and the interface labels columns from this field.
      source: 'generated',
      kind: factor.kind,
      cadence: factor.cadence,
      unit: factor.unit,
      points,
      annual: annualRollup(points, factor.kind),
      meta: { ...factor, base_meta: BASE_BY_ID.get(factor.base)! },
    }
  }

  return {
    area_ha: round(areaHa, 2),
    centroid: { lng, lat },
    // The demo has no exact tier to refine into, and says so.
    precision: 'approx',
    steps,
    series,
  }
}

export function demoCells(geometry: GeoJSON.Polygon, resolution = 14): CellsResponse {
  const { lng, lat, areaHa } = validate(geometry)
  const ring = ringOf(geometry)
  const lngs = ring.map((p) => p[0])
  const lats = ring.map((p) => p[1])
  const west = Math.min(...lngs), east = Math.max(...lngs)
  const south = Math.min(...lats), north = Math.max(...lats)

  const n = resolution
  const dx = (east - west) / n
  const dy = (north - south) / n
  const cells: CellsResponse['cells'] = []

  for (let j = 0; j < n; j++) {
    for (let i = 0; i < n; i++) {
      const w = west + i * dx, e = west + (i + 1) * dx
      const s = south + j * dy, nn = south + (j + 1) * dy
      const cx = (w + e) / 2, cy = (s + nn) / 2
      if (!pointInRing(cx, cy, ring)) continue

      const k = `${round(cx, 5)}|${round(cy, 5)}`
      const h = unitNoise(k)
      // Smooth the field a little so neighbouring cells relate to each other
      // rather than looking like television static.
      const h2 = unitNoise(k, 's')
      cells.push({
        id: `${i}-${j}`,
        bbox: [round(w, 6), round(s, 6), round(e, 6), round(nn, 6)],
        offset: round((0.65 * h + 0.35 * h2) * 2 - 1, 4),
      })
    }
  }

  return { cells, area_ha: round(areaHa, 2), centroid: { lng, lat } }
}
