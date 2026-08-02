import type { Series } from '../types'

/**
 * Automatic chart selection.
 *
 * The rule that keeps this honest: charts are a projection of the table, so
 * they only ever show factors the user has actually selected, over the time
 * range the table covers. There is no separate chart data path to drift.
 *
 * Two constraints shape the output:
 *
 *  1. **Never mix units on one axis.** °C and mm on a shared y-axis is a lie
 *     told with a straight face. Continuous factors are grouped by unit and
 *     each group gets its own chart.
 *  2. **Cap the output.** The failure mode of auto-generation is twelve charts
 *     nobody reads. Four is the ceiling.
 */

export type ChartSpec =
  | { type: 'line'; unit: string; factorIds: string[]; title: string; reason: string }
  | { type: 'stacked'; factorIds: string[]; title: string; reason: string }
  | { type: 'bar'; factorId: string; title: string; reason: string }
  | { type: 'scatter'; x: string; y: string; r: number; title: string; reason: string }

const MAX_CHARTS = 4

function pearson(a: number[], b: number[]): number {
  const n = Math.min(a.length, b.length)
  if (n < 5) return 0
  const ma = a.reduce((s, v) => s + v, 0) / n
  const mb = b.reduce((s, v) => s + v, 0) / n
  let num = 0, da = 0, db = 0
  for (let i = 0; i < n; i++) {
    const x = a[i] - ma, y = b[i] - mb
    num += x * y; da += x * x; db += y * y
  }
  const d = Math.sqrt(da * db)
  return d === 0 ? 0 : num / d
}

/** Annual means, aligned by year, for correlation testing. */
function annualValues(s: Series): Map<number, number> {
  const m = new Map<number, number>()
  for (const r of s.annual) {
    if (typeof r.value === 'number') m.set(r.year, r.value)
  }
  return m
}

function alignedPairs(a: Series, b: Series): [number[], number[]] {
  const ma = annualValues(a), mb = annualValues(b)
  const xs: number[] = [], ys: number[] = []
  for (const [year, v] of ma) {
    const w = mb.get(year)
    if (w !== undefined) { xs.push(v); ys.push(w) }
  }
  return [xs, ys]
}

export function inferCharts(all: Series[]): ChartSpec[] {
  const continuous = all.filter((s) => s.kind === 'continuous')
  const categorical = all.filter((s) => s.kind === 'categorical')
  const specs: ChartSpec[] = []

  // 1. Time series, grouped by unit. This is the default view of a temporal
  //    question and should always come first.
  const byUnit = new Map<string, Series[]>()
  for (const s of continuous) {
    const key = s.unit || 'value'
    if (!byUnit.has(key)) byUnit.set(key, [])
    byUnit.get(key)!.push(s)
  }
  for (const [unit, group] of byUnit) {
    specs.push({
      type: 'line',
      unit,
      factorIds: group.map((g) => g.factor_id),
      title: group.length === 1
        ? `${group[0].meta.name} over time`
        : `${group.map((g) => g.meta.name).join(', ')} over time`,
      reason: `${group.length} factor${group.length > 1 ? 's' : ''} measured in ${unit}`,
    })
  }

  // 2. Percentage factors that sum toward a whole are a composition question,
  //    and a stacked area answers it better than overlaid lines.
  const pctLandCover = continuous.filter(
    (s) => s.unit === '%' && s.factor_id.startsWith('lc_'),
  )
  if (pctLandCover.length >= 2) {
    specs.push({
      type: 'stacked',
      factorIds: pctLandCover.map((s) => s.factor_id),
      title: 'Land cover composition',
      reason: 'Shares of one whole read better stacked than overlaid',
    })
  }

  // 3. Categorical factors get a frequency bar — averaging them is meaningless
  //    (TECHNICAL_PLAN.md §8.5), so a count of years per class is the honest
  //    summary.
  for (const s of categorical) {
    specs.push({
      type: 'bar',
      factorId: s.factor_id,
      title: `${s.meta.name} — years per class`,
      reason: 'Categorical data cannot be averaged, so this counts instead',
    })
  }

  // 4. Strongly correlated pairs are worth surfacing, but only when the
  //    relationship is real. A weak scatter is noise dressed as insight.
  if (continuous.length >= 2) {
    let best: { a: Series; b: Series; r: number } | null = null
    for (let i = 0; i < continuous.length; i++) {
      for (let j = i + 1; j < continuous.length; j++) {
        const [xs, ys] = alignedPairs(continuous[i], continuous[j])
        const r = pearson(xs, ys)
        if (Math.abs(r) > 0.6 && (!best || Math.abs(r) > Math.abs(best.r))) {
          best = { a: continuous[i], b: continuous[j], r }
        }
      }
    }
    if (best) {
      specs.push({
        type: 'scatter',
        x: best.a.factor_id,
        y: best.b.factor_id,
        r: best.r,
        title: `${best.a.meta.name} vs ${best.b.meta.name}`,
        reason: `Correlated at r = ${best.r.toFixed(2)} across the years shown`,
      })
    }
  }

  return specs.slice(0, MAX_CHARTS)
}
