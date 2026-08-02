import type { Factor } from '../types'

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
 * A single sequential ramp, dark to accent. Deliberately one ramp rather than
 * per-factor palettes: with 118 factors, bespoke colour schemes become
 * impossible to keep coherent, and a consistent ramp means users learn to read
 * "darker = less" once.
 */
const RAMP: [number, number, number][] = [
  [26, 32, 34],
  [42, 66, 58],
  [74, 106, 74],
  [138, 154, 84],
  [206, 176, 92],
  [237, 206, 138],
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
const SERIES_COLORS = [
  '#DDAE5C', '#7FB3A3', '#C98A6B', '#8FA5C4',
  '#B48EAD', '#9BB068', '#D4A0A0', '#6FA8B8',
  '#C4923F', '#88A398', '#B9846B', '#7D8FB3',
]

export function seriesColor(i: number): string {
  return SERIES_COLORS[i % SERIES_COLORS.length]
}
