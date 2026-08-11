import type { AnnualRow, Factor } from '../types'

/**
 * Whether a year was built from fewer months than it should have been.
 *
 * This matters more than it looks. NDVI's first year is 2017, and Sentinel-2
 * only starts in March — so that row averages ten months and is missing
 * January and February, the two lowest of the year. It reads as the highest
 * NDVI on record when it is really just a year with its winter cut off.
 *
 * The table has always marked this with a dot. Exports did not, so the caveat
 * died at the boundary where it matters most: a chart built in Excel from
 * exported data showed a spike that does not exist. Every export path goes
 * through here now.
 */
export function isPartialYear(r: Pick<AnnualRow, 'months_observed' | 'months_total' | 'value'>): boolean {
  return r.value !== null && r.months_observed < r.months_total
}

/** Column header for the coverage that travels beside an exported value. */
export function coverageHeader(name: string): string {
  return `${name} months observed`
}

/**
 * Months behind an exported value, as a plain integer.
 *
 * Deliberately not "10/12": Excel silently reads that as a date and turns the
 * caveat into 10 December, which is worse than omitting it.
 */
export function coverageValue(r?: AnnualRow): string {
  if (!r || r.value === null) return ''
  return String(r.months_observed)
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** '2024-07' -> 'Jul 2024' */
export function labelStep(step: string): string {
  const [y, m] = step.split('-')
  return `${MONTHS[Number(m) - 1]} ${y}`
}

export function stepToDate(step: string): Date {
  const [y, m] = step.split('-').map(Number)
  return new Date(y, m - 1, 1)
}

/**
 * Formats a value the way its unit implies. Money gets no decimals and a
 * thousands separator; indices get two; counts get none. Getting this wrong is
 * how a data table starts to look untrustworthy.
 */
export function formatValue(v: number | string | null, factor?: Factor): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'string') return v
  if (!Number.isFinite(v)) return '—'

  const unit = factor?.unit ?? ''
  if (unit === '£') return '£' + Math.round(v).toLocaleString('en-GB')
  if (unit === '£/m²') return '£' + Math.round(v).toLocaleString('en-GB')
  if (unit === '%') return v.toFixed(1) + '%'
  if (unit === '°') return v.toFixed(1) + '°'
  if (unit === '°C') return v.toFixed(1)
  if (unit === 'm' || unit === 'mm') return Math.abs(v) >= 100 ? Math.round(v).toLocaleString('en-GB') : v.toFixed(1)
  if (unit === 'days' || unit === 'sales' || unit === 'cells') return Math.round(v).toLocaleString('en-GB')
  if (Math.abs(v) >= 10000) return Math.round(v).toLocaleString('en-GB')
  if (Math.abs(v) >= 100) return v.toFixed(1)
  return v.toFixed(2)
}

/** Short form for axis ticks and the timeline readout. */
export function compact(v: number | string | null): string {
  if (v === null) return '—'
  if (typeof v === 'string') return v
  const a = Math.abs(v)
  if (a >= 1e6) return (v / 1e6).toFixed(1) + 'M'
  if (a >= 1e3) return (v / 1e3).toFixed(1) + 'k'
  if (a >= 10) return v.toFixed(0)
  return v.toFixed(2)
}

export function formatArea(ha: number): string {
  if (ha >= 10000) return (ha / 100).toFixed(0) + ' km²'
  if (ha >= 100) return Math.round(ha).toLocaleString('en-GB') + ' ha'
  return ha.toFixed(1) + ' ha'
}

/**
 * Confidence bands. Below 0.4 the UI greys the number out — a mean built from
 * a handful of cloud-free pixels should not look as solid as one built from
 * thousands (TECHNICAL_PLAN.md §6.4).
 */
export function confidenceBand(c: number): 'good' | 'fair' | 'poor' {
  if (c >= 0.7) return 'good'
  if (c >= 0.4) return 'fair'
  return 'poor'
}

/** Deterministic colour ramp position for a value within a factor's range. */
export function rampPosition(v: number, factor: Factor): number {
  const lo = factor.lo ?? 0
  const hi = factor.hi ?? 1
  if (hi === lo) return 0.5
  return Math.max(0, Math.min(1, (v - lo) / (hi - lo)))
}

/**
 * A single sequential ramp, pale to deep. Deliberately one ramp rather than
 * per-factor palettes: with 118 factors, bespoke colour schemes become
 * impossible to keep coherent, and a consistent ramp means users learn to read
 * it once.
 *
 * Built for a bone ground: it starts near the page so a low value recedes into
 * it, runs through khaki and lichen, and lands on the brand's deep forest. The
 * lightness falls monotonically along the ramp, which is what keeps it
 * readable in greyscale and to a colour-blind reader — the ordering survives
 * even when the hue does not.
 *
 * Signal orange is deliberately absent. The ramp describes magnitude, and
 * orange in this system means attention; a high value is not a warning.
 */
const RAMP: [number, number, number][] = [
  [241, 238, 229],
  [211, 214, 195],
  [166, 181, 145],
  [107, 141, 106],
  [52, 97, 74],
  [13, 32, 25],
]

export function rampColor(t: number, alpha = 1): string {
  const x = Math.max(0, Math.min(0.999, t)) * (RAMP.length - 1)
  const i = Math.floor(x)
  const f = x - i
  const a = RAMP[i]
  const b = RAMP[Math.min(RAMP.length - 1, i + 1)]
  const c = a.map((v, k) => Math.round(v + (b[k] - v) * f))
  return `rgba(${c[0]},${c[1]},${c[2]},${alpha})`
}

/** Stable colour per series, for multi-line charts and legends. */
// Forest leads, because the first series is the one drawn on the map and the
// map draws it in the brand's green. The rest fan out in hue at a lightness
// that holds against bone — nothing fluorescent, nothing that vibrates next to
// its neighbour, and no two adjacent entries confusable in greyscale.
const SERIES_COLORS = [
  '#16352a', '#a8410f', '#3f6b96', '#7b5ea7',
  '#5f7c42', '#96742f', '#2f7d6b', '#8a5a78',
  '#b4534f', '#547a5c', '#7a4f3a', '#4a5a75',
]

export function seriesColor(i: number): string {
  return SERIES_COLORS[i % SERIES_COLORS.length]
}

/** Both real sources count. Half the real catalogue now comes from
 *  planning.data.gov.uk and the Land Registry rather than from a satellite,
 *  and only "generated" means demo data. */
export function isReal(source?: string): boolean {
  return source === 'earth-engine' || source === 'open-data'
}
