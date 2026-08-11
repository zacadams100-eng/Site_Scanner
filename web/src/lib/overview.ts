import type { Coverage, HistoricalEntry, Investigation } from '../types'
import { changeText, findingClass, findingLabel } from './historical'

/**
 * The site overview — presentation logic only.
 *
 * This is the screen someone is shown in a meeting, which makes it the screen
 * most likely to be read as a verdict. Two invariants do the work, and both
 * are enforced by tests rather than by care:
 *
 * **EM7 — nothing here is a score.** No total, no percentage of health, no
 * ordering of sites. Coverage is reported as coverage: how much of the site we
 * were able to look at. A summary screen is exactly where "Site health:
 * 72/100" gets added, because it is the screen that wants a headline.
 *
 * **EM11 — nothing here decides a finding state.** Every state comes from the
 * server. The subtle trap on this screen is *direction*: an overview naturally
 * wants to draw a falling number in red, and a −23% NDVI that the engine
 * called `clear` must still render as clear. So the arrow is computed from the
 * sign and the colour is computed from the state, and they are deliberately
 * two different functions — `changeArrow` never sees a state and
 * `findingClass` never sees a number.
 */

/** The four states, in a fixed order, with the counts the engine reached.
 *
 *  Order is deliberate and not by size: flagged, clear, informational, not
 *  assessed. Sorting by count would put whichever number is largest first and
 *  turn a coverage strip into a ranking of its own states.
 */
export interface EvidenceRow {
  key: 'flagged' | 'clear' | 'informational' | 'not_assessed'
  label: string
  count: number
}

export function evidenceRows(coverage: Coverage | undefined): EvidenceRow[] {
  const c = coverage
  return [
    { key: 'flagged', label: 'flagged', count: c?.flagged ?? 0 },
    { key: 'clear', label: 'checked · clear', count: c?.clear ?? 0 },
    { key: 'informational', label: 'informational', count: c?.informational ?? 0 },
    { key: 'not_assessed', label: 'not assessed', count: c?.not_assessed ?? 0 },
  ]
}

/**
 * "1 of 24 factors assessed".
 *
 * Rendered next to the counts always, never on its own and never omitted.
 * EM10's rule is written for comparison but the reasoning is general: a flag
 * count without its coverage misleads in favour of the least examined site,
 * and a site read in a meeting is being compared to something even when it is
 * the only one on screen.
 */
export function assessedText(coverage: Coverage | undefined): string {
  if (!coverage) return ''
  return `${coverage.assessed} of ${coverage.relevant} factors assessed`
}

/**
 * Why the four counts do not add up to the total, when they do not.
 *
 * They are **not a partition**, and the overview is the screen where a reader
 * will try to add them. `flagged` and `informational` are independent factor
 * sets in `radar._coverage` and a factor can be in both — one NDVI series
 * carrying a decline flag *and* a mean-vigour reading is counted once in each.
 * `clear` excludes anything in either set, so the honest arithmetic is
 * `assessed + not_assessed = relevant`, with the three assessed states
 * overlapping inside `assessed`.
 *
 * Returns an empty string when there is no overlap, so the screen stays quiet
 * unless it has something to explain. A note that is always present is
 * furniture and stops being read.
 */
export function overlapNote(coverage: Coverage | undefined): string {
  if (!coverage) return ''
  const stated = coverage.flagged + coverage.clear + coverage.informational
  const overlap = stated - coverage.assessed
  if (overlap <= 0) return ''
  return `${overlap} factor${overlap === 1 ? '' : 's'} carr${overlap === 1 ? 'ies' : 'y'} `
    + 'both a flag and an informational reading, so the states above overlap '
    + 'rather than divide the total.'
}

/**
 * Why the unassessed factors were unassessed, in counts.
 *
 * The split is the whole point of the section. `not_selected` is one click to
 * fix; `generated` is a wall that no amount of clicking moves. Presenting them
 * as one number — "18 not assessed" — makes a fixable gap and a permanent one
 * look like the same problem.
 */
export interface GapCause {
  key: 'not_selected' | 'generated'
  count: number
  text: string
}

export function gapCauses(coverage: Coverage | undefined): GapCause[] {
  if (!coverage) return []
  const out: GapCause[] = []
  if (coverage.not_selected > 0) {
    out.push({
      key: 'not_selected',
      count: coverage.not_selected,
      text: 'not loaded into this report',
    })
  }
  if (coverage.generated > 0) {
    out.push({
      key: 'generated',
      count: coverage.generated,
      text: 'have no live source yet — demo data cannot support a finding',
    })
  }
  return out
}

/**
 * The arrow beside a historical change.
 *
 * Reads the number and nothing else — it is formatting, not judgement. A
 * falling NDVI gets ↓ whether the engine called it flagged, clear or
 * informational, and the colour that says which comes from `findingClass`.
 * Keeping the two apart is what makes "red because it fell" impossible to
 * write by accident.
 */
export function changeArrow(entry: HistoricalEntry): string {
  const m = entry.metric
  const v = m?.change_pct ?? m?.change
  if (v === null || v === undefined || v === 0) return ''
  return v > 0 ? '↑' : '↓'
}

/**
 * The change with its sign removed, for use beside an arrow.
 *
 * "↓ -23.0%" states the direction twice and reads as a double negative. The
 * arrow carries the sign on this screen, so the magnitude is what goes next to
 * it. `changeText` keeps its sign for the historical panel, where there is no
 * arrow and the sign is the only thing carrying direction.
 */
export function changeMagnitude(entry: HistoricalEntry): string {
  return changeText(entry).replace(/^[+−-]/, '')
}

/** A historical row: the name, the movement, and the state the engine reached.
 *  `state` and `stateLabel` are read; `arrow` and `change` are formatted. */
export interface HistoricalRow {
  id: string
  name: string
  arrow: string
  change: string
  stateLabel: string
  stateClass: string
  /** Whether there is a number to show at all. A metric that could not be
   *  computed still appears — a missing row reads as a clean one. */
  measured: boolean
}

export function historicalRows(entries: HistoricalEntry[] | undefined): HistoricalRow[] {
  if (!entries) return []
  return entries.map((e) => ({
    id: e.id,
    name: e.name,
    arrow: changeArrow(e),
    // Magnitude where an arrow carries the sign, the signed text where it does
    // not — "↓ -23.0%" states direction twice and reads as a double negative.
    change: changeArrow(e) ? changeMagnitude(e) : changeText(e),
    stateLabel: findingLabel(e),
    stateClass: findingClass(e),
    measured: e.metric?.change_pct !== null && e.metric?.change_pct !== undefined,
  }))
}

/**
 * The investigations, in the order the server ranked them.
 *
 * Not re-sorted here. The engine ranks by severity with one promotion rule
 * that depends on which factors the flags rest on, and a UI re-sort would be
 * a second opinion about priority — EM11 applied to ordering rather than to
 * state.
 */
export function attentionRows(investigations: Investigation[] | undefined): Investigation[] {
  return investigations ?? []
}

/**
 * The line under the site name.
 *
 * Area, and the centroid. **Never a county**, which is the interesting
 * constraint: a briefing header wants to read "24.6 ha · Surrey", and the only
 * source of an administrative area in this product is an explicit postcodes.io
 * search. A shape the user drew has no county attached, and deriving one from
 * a coordinate without a boundary dataset would be a guess printed in the
 * position a reader trusts most. Coordinates are less satisfying and true.
 */
export function locationLine(areaHa: number | undefined,
                            centroid: { lng: number; lat: number } | undefined): string {
  const parts: string[] = []
  if (areaHa !== undefined && areaHa !== null) parts.push(`${areaHa.toLocaleString()} ha`)
  if (centroid) parts.push(`${centroid.lat.toFixed(4)}, ${centroid.lng.toFixed(4)}`)
  return parts.join(' · ')
}

/**
 * The same facts, labelled, for the header block.
 *
 * A field assessment names its measurements rather than running them together
 * in a caption — "AREA 24.6 ha" is readable at a glance in a way that
 * "24.6 ha · 51.2400, -0.5700" is not. Same rule as `locationLine`: **no
 * county, ever.** A shape the user drew has no administrative area attached,
 * and deriving one from a coordinate without a boundary dataset would put a
 * guess in the position a reader trusts most.
 *
 * A fact that is missing is omitted rather than shown empty or filled with a
 * placeholder — a labelled blank reads as a value the product failed to load.
 */
export interface SiteFact { label: string; value: string }

export function siteFacts(areaHa: number | undefined,
                          centroid: { lng: number; lat: number } | undefined): SiteFact[] {
  const out: SiteFact[] = []
  if (areaHa !== undefined && areaHa !== null) {
    out.push({ label: 'Area', value: `${areaHa.toLocaleString()} ha` })
  }
  if (centroid) {
    out.push({ label: 'Latitude', value: centroid.lat.toFixed(4) })
    out.push({ label: 'Longitude', value: centroid.lng.toFixed(4) })
  }
  return out
}

/**
 * Evidence coverage as a proportion, for the bar.
 *
 * **This is not a score, and the distinction is the whole reason it is safe to
 * draw large.** EM7 forbids a number that rates the site; coverage rates *the
 * assessment*. It cannot flatter a site, because it falls when less is known —
 * the direction a score would move is the opposite of the direction this one
 * does. A site at 90% coverage is not better than one at 50%; more of it was
 * legible.
 *
 * `assessed / relevant`, both of which the engine computes. Returns null when
 * there is nothing to divide, so the bar is absent rather than showing a
 * confident 0% for a report that has not run.
 */
export interface CoverageBar { assessed: number; relevant: number; pct: number }

export function coverageBar(coverage: Coverage | undefined): CoverageBar | null {
  if (!coverage || !coverage.relevant) return null
  return {
    assessed: coverage.assessed,
    relevant: coverage.relevant,
    pct: Math.round((coverage.assessed / coverage.relevant) * 100),
  }
}
