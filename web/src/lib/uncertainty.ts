/**
 * How certain a month's reading is, drawn on the map rather than left in a
 * tooltip.
 *
 * The data has always carried this. `valid_fraction` on every point says what
 * share of the site actually had a usable observation that month, and
 * `annual[].confidence` carries it up to the year. The attribute table greys a
 * poor number out and the timeline whispers "low confidence" beside the
 * readout — but the map, which is the thing people look at, painted a month
 * built from 8% of its pixels exactly as confidently as one built from 95%.
 *
 * That is the failure worth fixing. A cloudy January and a clear July are the
 * same colour on screen, and the colour is the claim.
 *
 * ## Why hatching and not transparency
 *
 * The obvious move is to fade uncertain cells. It is wrong here: the value
 * ramp already starts near the paper colour, so a low value recedes into the
 * page by design. Fading low-confidence cells would make "a small number" and
 * "a number we do not trust" the same picture, which is worse than saying
 * nothing — the reader cannot tell which they are looking at.
 *
 * Hatching is a separate channel. It sits over the colour instead of altering
 * it, so the value stays readable and the doubt is additional information.
 * It is also the long-standing cartographic convention for unreliable or
 * absent data, so it needs less explaining than a bespoke encoding.
 *
 * ## Two states, not one
 *
 * - **Low confidence** — there is a value, but little of the site was
 *   observed. Sparse hatch, value still visible underneath.
 * - **No observation** — `value` is null. The map used to clear the overlay
 *   entirely, which is honest about the number and silent about the reason: a
 *   blank site looks identical to one where no factor is selected. Dense hatch
 *   with no fill, so the site reads as "asked, not answered".
 *
 * Never interpolate across the second one. `HANDOFF.md` is explicit that a
 * gap is the correct answer, not a bug to paper over, and a hatch is how you
 * show a gap without filling it in.
 */

import { confidenceBand } from './format'
import type { Point } from '../types'

/** What the overlay is saying about the current month. */
export type Certainty = 'ok' | 'low' | 'absent'

/**
 * Classify the month being displayed.
 *
 * The threshold is `confidenceBand`'s existing 'poor' cut at 0.4, deliberately
 * reused rather than redefined. Two independent definitions of "low
 * confidence" in one app is how a table and a map come to disagree about the
 * same number, and the user has no way to tell which is lying.
 */
export function certaintyOf(point: Point | undefined | null): Certainty {
  if (!point || point.value === null || point.value === undefined) return 'absent'
  if (typeof point.value === 'number' && !Number.isFinite(point.value)) return 'absent'
  return confidenceBand(point.valid_fraction) === 'poor' ? 'low' : 'ok'
}

/**
 * The sentence that goes with the hatch.
 *
 * A pattern nobody can read is decoration. This is shown next to the overlay
 * whenever the hatch is drawn, and it carries the actual figure rather than
 * an adjective — "12% of the site" is checkable, "low confidence" is not.
 */
export function certaintyNote(point: Point | undefined | null, step?: string): string | null {
  const c = certaintyOf(point)
  if (c === 'ok') return null
  const when = step ? ` in ${step}` : ''
  if (c === 'absent') return `No usable observation${when} — the hatched area was not measured, not measured as zero.`
  const pct = Math.round((point!.valid_fraction ?? 0) * 100)
  return `Only ${pct}% of the site had a usable observation${when}. The value is shown, hatched, because it is an average over that fraction.`
}

/** Ink for the hatch: the brand's neutral, never a colour from the value ramp. */
const HATCH_INK: [number, number, number] = [35, 35, 35]

/**
 * A diagonal-hatch tile for MapLibre's `fill-pattern`.
 *
 * Built as raw RGBA rather than loaded as an asset because it must exist
 * before the first paint and must not depend on a network fetch — the map
 * already has one silent-failure mode from a runtime asset request
 * (`HANDOFF.md`, the MapLibre worker), and this is not worth a second.
 *
 * `size` must divide evenly by the line spacing or the tile will not repeat
 * seamlessly; the default 8px tile with 45° lines every 4px does.
 */
export function hatchTile(
  { size = 8, spacing = 4, thickness = 1, alpha = 0.55 } = {},
): { width: number; height: number; data: Uint8Array } {
  const data = new Uint8Array(size * size * 4)
  const a = Math.round(Math.max(0, Math.min(1, alpha)) * 255)

  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      // 45° lines: every pixel where (x + y) lands on a spacing boundary.
      // Wrapping with the tile size is what makes the seams invisible.
      const on = ((x + y) % spacing) < thickness
      const i = (y * size + x) * 4
      if (on) {
        data[i] = HATCH_INK[0]
        data[i + 1] = HATCH_INK[1]
        data[i + 2] = HATCH_INK[2]
        data[i + 3] = a
      }
      // else left at 0,0,0,0 — transparent, so the value colour shows through
    }
  }
  return { width: size, height: size, data }
}

/** Sparse hatch for a value we half-trust; the colour underneath still reads. */
export const HATCH_LOW = { size: 8, spacing: 4, thickness: 1, alpha: 0.5 }
/** Dense hatch for a month with no observation at all. Nothing underneath. */
export const HATCH_ABSENT = { size: 8, spacing: 2, thickness: 1, alpha: 0.42 }
