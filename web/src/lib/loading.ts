import type { Factor } from '../types'

/**
 * What to say while a report is being built.
 *
 * Extracted from the component so the wording is testable, because the wording
 * is the part that can be wrong in a way that matters. Everything this file
 * produces is a claim about what the app is doing, and the project's rule
 * about not presenting an estimate as an observation does not stop applying
 * because the text is small and grey.
 *
 * The rule that constrains all of it: **nothing here may describe progress**.
 * `/api/series` is one POST returning every factor at once, so the client never
 * learns that one layer has landed and another has not. Any sentence implying
 * otherwise would be a guess, and this component used to be built entirely out
 * of them — "Rolling months into years…" appeared at 2.5 seconds whether or not
 * any months were being rolled.
 */

/** Rows drawn before the rest collapse into a count. Twelve factors is the
 *  selection cap, and twelve shimmering rows is a barcode rather than a list. */
export const MAX_ROWS = 7

/** When a slow request stops being "working" and starts being "something
 *  upstream is wrong". Chosen to sit past the point where a real Earth Engine
 *  query would normally have answered. */
export const SLOW_AFTER_S = 9

/**
 * Why this is taking as long as it is.
 *
 * A request's cost is almost entirely its real factors: a generated series is
 * microseconds of arithmetic and a real one is a round trip to Earth Engine or
 * a government endpoint. Naming that split explains the wait with a fact
 * rather than an apology, and it quietly teaches the thing the whole product
 * wants understood — that some of these numbers are observations and some are
 * not.
 */
export function explainWait(factors: Factor[]): string | null {
  if (!factors.length) return null
  const live = factors.filter((f) => f.real)

  if (live.length === 0) {
    // Not "nothing is being fetched". The request is still in flight, and
    // saying otherwise while the user watches a spinner is the small kind of
    // wrong that costs trust in the large kind.
    return factors.length === 1
      ? 'This layer is demo data, generated on the server.'
      : `All ${factors.length} layers are demo data, generated on the server.`
  }
  if (live.length === factors.length) {
    return `All ${live.length} are live sources, each one an upstream fetch.`
  }
  return live.length === 1
    ? `1 of ${factors.length} is a live source, and that is the one taking the time.`
    : `${live.length} of ${factors.length} are live sources, and those are the ones taking the time.`
}

/**
 * The hosts actually being waited on.
 *
 * Named rather than described, because "the data source is slow" is not
 * something a person can act on and "planning.data.gov.uk is slow" tells them
 * whose problem it is — and, if they are the one who wired it up, where to
 * look. Deduplicated: four designations behind one host is one host.
 */
export function waitingOn(factors: Factor[]): string[] {
  const hosts = factors
    .filter((f) => f.real)
    .map((f) => f.provenance?.endpoint)
    .filter((h): h is string => !!h)
  return [...new Set(hosts)]
}

/** Resolve selected ids against the catalogue, preserving the user's order and
 *  silently dropping anything the catalogue does not know — a stale permalink
 *  can name a factor that has since been renamed. */
export function selectedFactors(ids: string[], all: Factor[] | undefined): Factor[] {
  const by = new Map((all ?? []).map((f) => [f.id, f]))
  return ids.map((id) => by.get(id)).filter((f): f is Factor => !!f)
}
