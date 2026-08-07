/**
 * How loudly to flag a year that was not fully observed — and, where the data
 * allows it, which way that year is wrong.
 *
 * ## The decision this file settles
 *
 * A year built from fewer than twelve months was marked with a `·` and a
 * tooltip, everywhere, at one volume. `HANDOFF.md` left open whether a dot is
 * loud enough for something that makes a row non-comparable.
 *
 * A single flat mark is wrong in both directions. A year missing one month in
 * December is very nearly comparable and does not deserve a warning. NDVI's
 * 2017 is missing January and February — Sentinel-2 starts in March — and
 * those are the two lowest NDVI months of the year, so that row reads as the
 * highest vegetation on record when it is really a year with its winter cut
 * off. The same dot on both is either noise or negligence depending on which
 * row you are looking at.
 *
 * So the caveat is graded, and the grade is computed rather than assumed.
 *
 * ## Count is the weak test; season is the real one
 *
 * How *many* months are missing matters less than *which*. A year missing
 * April and October is short two months and roughly unbiased, because it lost
 * one month from each side of the seasonal curve. A year missing January and
 * February is short the same two months and systematically biased upward on
 * any factor with a winter minimum.
 *
 * The direction is not a guess. Every factor here carries fifteen years of
 * monthly values, so the seasonal shape can be measured from the series
 * itself: average each calendar month across the whole record, then ask
 * whether the months a given year *did* observe sit above or below the average
 * of all twelve. That difference is the bias, in the factor's own units,
 * derived by arithmetic from numbers already on screen. No model, no
 * assumption about what the factor is.
 *
 * ## And it is checked against the noise floor
 *
 * A computed bias smaller than the series' own year-to-year movement is not
 * worth saying — it would be the same overclaiming this project refuses
 * everywhere else. The floor is the mean absolute step between consecutive
 * years, the same measure `nlq.py:_spread` uses for exactly the same reason.
 */

import type { AnnualRow, Point, Series } from '../types'

/** How much of a caveat a year has earned. */
export type CoverageGrade = 'complete' | 'slight' | 'severe'

/**
 * Missing up to two months can still leave every season represented, so it
 * stays a hint. Beyond that a whole season is at risk and the row stops being
 * comparable to its neighbours.
 */
const SLIGHT_MAX_MISSING = 2

/** A comparable year is twelve months. Every series here is on monthly points
 *  regardless of the source's own cadence — an annual or static factor is
 *  carried forward across the twelve — so this holds for all of them. */
const FULL_YEAR = 12

/**
 * Grade a year by how far it is from a full year *of this factor*.
 *
 * Two corrections to the obvious version, both of which the obvious version
 * gets backwards:
 *
 * **Not against `months_total`.** That counts the months of the year inside
 * the *requested range*, so asking for 2011-06 onward gives 2011 a
 * `months_total` of 7 and a 2-of-2 stub at a range edge would grade
 * "complete" while being ten months short of anything comparable.
 *
 * **Not against a flat twelve either.** Sentinel-2 never returns a January,
 * February or December, so NDVI's best possible year is nine months. Grading
 * those against twelve marks every NDVI year in the record "severe" and greys
 * out the entire column — while the caveat text on the same cell says the
 * years are comparable with each other, which is the truth. A factor's full
 * year is twelve minus the months it never observes at all.
 *
 * `series` is optional so the cheap check still works without it; pass it
 * wherever the series is to hand, which is everywhere it is actually called.
 */
export function coverageGrade(
  r: Pick<AnnualRow, 'months_observed' | 'months_total' | 'value'>,
  series?: Series,
): CoverageGrade {
  if (r.value === null || r.value === undefined) return 'severe'
  const fullYear = series
    ? FULL_YEAR - neverObservedMonths(series).length
    : FULL_YEAR
  const missing = fullYear - r.months_observed
  if (missing <= 0) return 'complete'
  return missing <= SLIGHT_MAX_MISSING ? 'slight' : 'severe'
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** Which calendar months a year has no value for. */
export function missingMonths(points: Point[], year: number): string[] {
  const seen = new Set<number>()
  for (const p of points) {
    if (Number(p.t.slice(0, 4)) !== year) continue
    if (p.value === null || p.value === undefined) continue
    seen.add(Number(p.t.slice(5, 7)))
  }
  const out: string[] = []
  for (let m = 1; m <= 12; m++) if (!seen.has(m)) out.push(MONTHS[m - 1])
  return out
}

/**
 * Calendar months this factor has no value for in any year of the record.
 *
 * A property of the dataset rather than of any one row, which is why it is
 * computed separately: it is true even of a year with no gaps of its own, and
 * `seasonalBias` returns null for exactly those years.
 */
export function neverObservedMonths(series: Series): string[] {
  const seen = new Set<number>()
  for (const p of series.points) {
    if (typeof p.value !== 'number' || !Number.isFinite(p.value)) continue
    seen.add(Number(p.t.slice(5, 7)))
  }
  return MONTHS.filter((_, i) => !seen.has(i + 1))
}

export interface SeasonalBias {
  /** Which way this year's mean is pushed, relative to a typical year of the
   *  same factor as the record is actually able to measure it. */
  direction: 'high' | 'low' | 'none'
  /** Size of the push, in the factor's own units. */
  magnitude: number
  /** Typical year-to-year movement, for scale. */
  noise: number
  /** Months this year has no value for, and other years do. These are what
   *  make this year different from its neighbours. */
  missing: string[]
  /** Months no year in the record has a value for. These make every year
   *  equally incomplete, which is a different problem with a different answer:
   *  the years stay comparable with each other, and none of them is a true
   *  annual figure. Sentinel-2's winter is the standing example — the
   *  generator, and the satellite, produce nothing for Jan, Feb or Dec. */
  neverObserved: string[]
}

/**
 * Estimate which way a partial year's mean is wrong.
 *
 * The baseline is deliberately "a typical year *of this factor*", not "a true
 * twelve-month mean". A calendar month that never appears anywhere in the
 * record has no climatology to compare against, so including it in the
 * baseline would mean estimating the bias from an average that is itself
 * biased in the same direction — the error this function exists to catch,
 * applied silently to its own reference point.
 *
 * Excluding those months instead makes the comparison honest and the result
 * useful: every year shares that hole, so the years remain comparable with
 * each other. `neverObserved` carries that fact out separately rather than
 * dropping it, because "none of these is a real annual mean" is exactly the
 * sort of thing a reader needs before quoting one.
 *
 * Returns null for a categorical factor — halfway between Grassland and
 * Cropland is Built-up, and the same objection applies to averaging their
 * seasonality.
 */
export function seasonalBias(series: Series, year: number): SeasonalBias | null {
  if (series.kind === 'categorical') return null

  // Climatology: the mean of each calendar month across the whole record.
  const byMonth: number[][] = Array.from({ length: 12 }, () => [])
  for (const p of series.points) {
    if (typeof p.value !== 'number' || !Number.isFinite(p.value)) continue
    byMonth[Number(p.t.slice(5, 7)) - 1].push(p.value)
  }

  const observable = byMonth
    .map((v, i) => (v.length ? i : -1))
    .filter((i) => i >= 0)
  const neverObserved = MONTHS.filter((_, i) => !byMonth[i].length)
  // Fewer than two measurable months is not a seasonal shape.
  if (observable.length < 2) return null

  const climatology = byMonth.map((v) => (v.length ? v.reduce((a, b) => a + b, 0) / v.length : NaN))
  const baseline = observable.reduce((a, i) => a + climatology[i], 0) / observable.length

  const seen = new Set<number>()
  for (const p of series.points) {
    if (Number(p.t.slice(0, 4)) !== year) continue
    if (typeof p.value !== 'number' || !Number.isFinite(p.value)) continue
    seen.add(Number(p.t.slice(5, 7)) - 1)
  }
  if (!seen.size || seen.size >= observable.length) return null

  const observedMean = [...seen].reduce((a, i) => a + climatology[i], 0) / seen.size
  const magnitude = observedMean - baseline
  const noise = yearToYearNoise(series.annual)

  // What this year is missing that other years have. A month nobody ever
  // observed is not this year's problem and must not be listed as though it
  // were — it would send the reader looking for a fault in one row that is
  // really a property of the whole record.
  const missing = MONTHS.filter((m, i) => !seen.has(i) && byMonth[i].length > 0)

  // Below the noise floor there is nothing worth telling anyone. Announcing a
  // bias the series' own wobble would swamp is how a caveat becomes clutter.
  const direction = Math.abs(magnitude) <= noise ? 'none'
                  : magnitude > 0 ? 'high' : 'low'

  return { direction, magnitude, noise, missing, neverObserved }
}

/**
 * Typical movement between consecutive years — the noise floor.
 *
 * The same measure, for the same reason, as `nlq.py:_spread`. Kept numerically
 * identical on purpose: a caveat the table shows and the written answer omits
 * (or the reverse) is worse than either behaviour on its own.
 */
export function yearToYearNoise(annual: AnnualRow[]): number {
  const vals = annual
    .filter((a) => typeof a.value === 'number' && Number.isFinite(a.value))
    .map((a) => a.value as number)
  if (vals.length < 2) return 0
  let total = 0
  for (let i = 1; i < vals.length; i++) total += Math.abs(vals[i] - vals[i - 1])
  return total / (vals.length - 1)
}

/** Join a list the way a person would. */
function list(items: string[]): string {
  if (items.length <= 1) return items[0] ?? ''
  if (items.length === 2) return `${items[0]} and ${items[1]}`
  if (items.length > 4) return `${items.slice(0, 3).join(', ')} and ${items.length - 3} more`
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
}

/**
 * The caveat in words, or null when the year needs none.
 *
 * This is the text that travels — table tooltip, chart, CSV, printed report —
 * so it says the same thing everywhere by construction rather than by four
 * copies staying in sync.
 */
export function coverageCaveat(series: Series, r: AnnualRow): string | null {
  const grade = coverageGrade(r, series)
  if (grade === 'complete') return null
  if (r.value === null) return 'No usable observation this year.'

  // Two different reasons a year can be short, and they are not the same
  // problem. Months outside the requested range were never asked for; months
  // inside it with no value were asked for and not answered. Reporting the
  // first as though the data were missing sends people looking for a fault
  // that is really just the range they chose.
  if (r.months_total < FULL_YEAR) {
    const inRange = r.months_observed < r.months_total
      ? ` (${r.months_observed} of those ${r.months_total} observed)`
      : ''
    return `Only ${r.months_total} of this year's 12 months are inside the selected range` +
           `${inRange}. Not comparable with a full year.`
  }

  const head = `${r.months_observed} of ${r.months_total} months observed`

  const bias = seasonalBias(series, r.year)
  if (!bias || !bias.missing.length) return `${head}.`

  const missing = `missing ${list(bias.missing)}`
  if (bias.direction === 'none') {
    const gaps = bias.missing.length === 1 ? 'The gap does not' : 'The gaps are spread across the year, so they do not'
    return `${head} — ${missing}. ${gaps} obviously bias the mean.`
  }
  const isAre = bias.missing.length === 1 ? 'which is' : 'which are'
  return `${head} — ${missing}, ${isAre} ${bias.direction === 'high' ? 'below' : 'above'} ` +
         `this factor's typical year, so ${r.year}'s figure reads ${bias.direction}. ` +
         `Not comparable with the other years.`
}

/**
 * What is true of the whole column, said once.
 *
 * A month the record never observes *anywhere* is a property of the dataset,
 * not of any one row — Sentinel-2 returns nothing for January in any year of
 * its life. That belongs beside the factor's name, not repeated in fifteen
 * identical tooltips down a column, where it stops being read by the third
 * row and crowds out the caveats that are about a specific year.
 *
 * The conclusion is the useful part and it is not the obvious one: because
 * every year has the same hole, the years remain comparable **with each
 * other**, even though none of them is a twelve-month mean. Someone about to
 * quote one as an annual figure needs both halves of that.
 */
export function seriesCoverageNote(series: Series): string | null {
  const never = neverObservedMonths(series)
  if (!never.length) return null
  if (never.length >= 12) return 'This factor has no observations at all.'
  return `Never observed in ${list(never)} in any year, so no annual figure ` +
         `here is a true 12-month average — but the years are comparable with ` +
         `each other.`
}

/**
 * Short marker for the cell itself, where there is no room for a sentence.
 *
 * A severe year gets the month count rather than a dot: `10 mo` states the
 * problem where a `·` only hints that one exists, and the row is the last
 * place a reader looks before quoting the number.
 */
export function coverageMark(r: AnnualRow, series?: Series): string | null {
  const grade = coverageGrade(r, series)
  if (grade === 'complete' || r.value === null) return null
  return grade === 'severe' ? `${r.months_observed} mo` : '·'
}
