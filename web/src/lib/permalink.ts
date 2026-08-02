import type { DrawMode } from '../types'

/**
 * URL state.
 *
 * The single biggest failure of GEE workflows is irreproducibility — a
 * colleague asks "how did you get that number?" and the answer is a script
 * nobody can run. A URL that restores exact state is the cheapest credibility
 * feature available, and it is also the primary organic growth channel.
 *
 * Encoded in the hash rather than the query string so that restoring state
 * never round-trips to a server.
 */

export interface UrlState {
  aoi: GeoJSON.Polygon | null
  factors: string[]
  t: number
  compare: number | null
}

/** Polygons are the bulky part, so coordinates are quantised to ~1 m and
 *  delta-encoded before base64. A 60-vertex freehand shape fits in a URL that
 *  still pastes into Slack without wrapping. */
function encodeRing(ring: number[][]): string {
  const q = (v: number) => Math.round(v * 1e5)
  let px = 0
  let py = 0
  const parts: string[] = []
  for (const [lng, lat] of ring) {
    const x = q(lng)
    const y = q(lat)
    parts.push(`${x - px}.${y - py}`)
    px = x
    py = y
  }
  return parts.join('_')
}

function decodeRing(s: string): number[][] {
  let px = 0
  let py = 0
  const out: number[][] = []
  for (const part of s.split('_')) {
    const i = part.indexOf('.', part[0] === '-' ? 1 : 0)
    if (i < 0) continue
    px += Number(part.slice(0, i))
    py += Number(part.slice(i + 1))
    out.push([px / 1e5, py / 1e5])
  }
  return out
}

export function encodeState(s: UrlState): string {
  const parts: string[] = []
  if (s.aoi) parts.push('g=' + encodeRing(s.aoi.coordinates[0] as number[][]))
  if (s.factors.length) parts.push('f=' + s.factors.join('.'))
  parts.push('t=' + s.t)
  if (s.compare !== null) parts.push('c=' + s.compare)
  return parts.join('&')
}

export function decodeState(hash: string): Partial<UrlState> {
  const raw = hash.replace(/^#/, '')
  if (!raw) return {}
  const out: Partial<UrlState> = {}
  for (const kv of raw.split('&')) {
    const i = kv.indexOf('=')
    if (i < 0) continue
    const k = kv.slice(0, i)
    const v = kv.slice(i + 1)
    if (k === 'g') {
      const ring = decodeRing(v)
      // A polygon needs at least a triangle plus its closing vertex.
      if (ring.length >= 3) {
        const closed = ring[0][0] === ring[ring.length - 1][0] &&
          ring[0][1] === ring[ring.length - 1][1]
        out.aoi = {
          type: 'Polygon',
          coordinates: [closed ? ring : [...ring, ring[0]]],
        }
      }
    } else if (k === 'f') out.factors = v.split('.').filter(Boolean)
    else if (k === 't') out.t = Number(v)
    else if (k === 'c') out.compare = Number(v)
  }
  return out
}

export function writeUrl(s: UrlState): void {
  const encoded = encodeState(s)
  // replaceState, not pushState: scrubbing the timeline must not fill the
  // browser's back stack with 180 entries.
  history.replaceState(null, '', '#' + encoded)
}

export function shareUrl(s: UrlState): string {
  return `${location.origin}${location.pathname}#${encodeState(s)}`
}

/** Guided starting points. The target user knows GIS but not this interface;
 *  a template is a worked example that produces their answer on first visit,
 *  which solves onboarding without a tutorial. */
export interface Template {
  id: string
  name: string
  blurb: string
  factors: string[]
  tool: DrawMode
}

export const TEMPLATES: Template[] = [
  {
    id: 'vegetation',
    name: 'Vegetation change',
    blurb: 'Is this land getting greener or browner over 15 years?',
    factors: ['ndvi', 'lc_tree_pct', 'lc_grass_pct', 'precip_total'],
    tool: 'freehand',
  },
  {
    id: 'flood',
    name: 'Flood exposure',
    blurb: 'How exposed is this site to water, and is that changing?',
    factors: ['flood_zone3_pct', 'hand', 'water_occurrence', 'max_daily_precip'],
    tool: 'rect',
  },
  {
    id: 'urban',
    name: 'Urban growth',
    blurb: 'How fast is this area being built on?',
    factors: ['lc_built_pct', 'built_volume', 'population_density', 'nightlight_radiance'],
    tool: 'rect',
  },
  {
    id: 'solar',
    name: 'Solar suitability',
    blurb: 'Would a solar array work here?',
    factors: ['solar_ghi', 'slope_mean', 'solar_aspect_score', 'lc_built_pct'],
    tool: 'circle',
  },
  {
    id: 'heat',
    name: 'Urban heat',
    blurb: 'How much hotter is this area than its surroundings?',
    factors: ['lst_day', 'heat_anomaly', 'lc_tree_pct', 'impervious_pct'],
    tool: 'rect',
  },
  {
    id: 'agriculture',
    name: 'Crop performance',
    blurb: 'How has this field performed season by season?',
    factors: ['ndvi', 'soil_organic_carbon', 'soil_moisture', 'growing_degree_days'],
    tool: 'freehand',
  },
]
