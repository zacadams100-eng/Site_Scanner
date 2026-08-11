import type { AskResponse, Brief, Catalog, CellsResponse, Comparison, SeriesResponse } from './types'

/**
 * The backend returns a plain-language `detail` for anything a user can fix
 * (area too big, drawn outside England). Surfacing that verbatim is better
 * than a generic failure message, so this preserves it.
 */
export class ApiError extends Error {
  readonly status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

/**
 * How long one request may take before the app stops waiting.
 *
 * Generous, because a real Earth Engine assessment across a dozen factors is
 * genuinely slow and cutting it off early would be worse than waiting. But not
 * unbounded: a backend that accepts a connection and never answers used to
 * leave the loading sequence running for as long as the tab stayed open, with
 * nothing to distinguish it from slow.
 */
const REQUEST_TIMEOUT_MS = 90_000

/** The caller's cancellation and the deadline, as one signal. Aborting for
 *  either reason stops the request; the two are told apart afterwards, because
 *  a user changing their mind is not a failure and a deadline is. */
function withDeadline(signal?: AbortSignal): AbortSignal {
  const deadline = AbortSignal.timeout(REQUEST_TIMEOUT_MS)
  return signal ? AbortSignal.any([signal, deadline]) : deadline
}

async function post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: withDeadline(signal),
    })
  } catch (e) {
    // `AbortSignal.timeout` aborts with a TimeoutError, which is how this is
    // distinguished from the caller cancelling — the store ignores the latter
    // and must not ignore this.
    if ((e as Error).name === 'TimeoutError') {
      throw new ApiError(
        'The server did not respond within 90 seconds. It may be busy — try again.', 504)
    }
    throw e
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const j = await res.json()
      if (typeof j.detail === 'string') detail = j.detail
      else if (Array.isArray(j.detail)) detail = j.detail.map((d: any) => d.msg).join('; ')
    } catch {
      /* keep the status line */
    }
    throw new ApiError(detail, res.status)
  }
  // A 200 carrying a truncated or non-JSON body is a server fault, not
  // something the reader can act on. Surfacing the parser's own words —
  // "Expected property name or '}' in JSON at position 12" — puts a stack
  // trace where an explanation belongs.
  try {
    return await res.json() as T
  } catch {
    throw new ApiError('The server sent a reply this app could not read.', res.status)
  }
}

export async function fetchCatalog(scanner?: string): Promise<Catalog> {
  const res = await fetch(`/api/catalog${scanner ? `?scanner=${encodeURIComponent(scanner)}` : ''}`)
  if (!res.ok) throw new ApiError(`Catalogue unavailable (${res.status})`, res.status)
  return res.json()
}

/**
 * Every request that runs an assessment names the scanner that runs it.
 *
 * This was missing, and it was not cosmetic: `ScannedRequest.scanner` defaults
 * to `land` on the backend, so a report requested from inside the Habitat
 * scanner came back assessed by Land's rules against Land's factor list. The
 * shell said HABITAT, the layers were habitat layers, and the findings were
 * not. Scanner identity has to travel with the work, not only with the
 * catalogue that describes it.
 */
export function fetchSeries(
  geometry: GeoJSON.Polygon,
  factorIds: string[],
  scanner: string,
  signal?: AbortSignal,
): Promise<SeriesResponse> {
  return post<SeriesResponse>('/api/series',
    { geometry, factor_ids: factorIds, scanner }, signal).then(assertSeries)
}

/**
 * The response is the shape the rest of the app assumes it is.
 *
 * `post` guarantees valid JSON and nothing more. A 200 carrying `{}` parses
 * perfectly and then fails several layers away, where the first consumer
 * reaches into `series` for a factor: the user saw "Cannot read properties of
 * undefined (reading 'ndvi')" in a panel that should have said the report
 * could not be built.
 *
 * Checked here, at the boundary, so the error names the actual problem and
 * every reader downstream can trust the type it was given.
 */
function assertSeries(r: SeriesResponse): SeriesResponse {
  if (!r || typeof r !== 'object' || !r.series || !Array.isArray(r.steps)) {
    throw new ApiError('The server returned a report with no data in it.', 502)
  }
  return r
}

/**
 * The Site Investigation Brief.
 *
 * Its own request rather than a key on the series response, because the Brief
 * carries the full assessment log and every attribution — payload that belongs
 * in a document someone asked for, not behind every map interaction.
 */
export function fetchBrief(
  geometry: GeoJSON.Polygon,
  factorIds: string[],
  siteName: string,
  scanner: string,
  signal?: AbortSignal,
): Promise<Brief> {
  return post<Brief>('/api/brief',
    { geometry, factor_ids: factorIds, site_name: siteName, scanner }, signal)
}

export function fetchCells(
  geometry: GeoJSON.Polygon,
  scanner: string,
  signal?: AbortSignal,
): Promise<CellsResponse> {
  return post<CellsResponse>('/api/cells', { geometry, resolution: 14, scanner }, signal)
}

/** True when the mock backend answered — surfaced in the UI so nobody mistakes
 *  generated numbers for real ones. */
export async function detectMock(): Promise<boolean> {
  try {
    const res = await fetch('/api/catalog', { method: 'HEAD' })
    if (res.headers.get('X-Contour-Mock') === 'true') return true
  } catch {
    /* fall through */
  }
  try {
    const res = await fetch('/')
    return res.headers.get('X-Contour-Mock') === 'true'
  } catch {
    return false
  }
}

/** Ask is scanner-scoped too.
 *
 *  `AskRequest` extends `ScannedRequest`, so the backend resolves a scanner for
 *  every question and reads the factor list through it. Omitting the field here
 *  did not fail — it silently took the default, and a question asked inside
 *  Habitat was answered from Land's factors. Same defect as the report path,
 *  one route further on. */
export function ask(
  geometry: GeoJSON.Polygon,
  question: string,
  scanner: string,
  signal?: AbortSignal,
): Promise<AskResponse> {
  return post<AskResponse>('/api/ask', { geometry, question, scanner }, signal)
}

/** Compare 2–4 saved sites' evidence profiles.
 *
 *  Every site is assessed on the same factor list — comparing a site screened
 *  on twelve factors against one screened on four is not a comparison of
 *  sites. See COMPARISON_CONTRACT.md. */
export function compareSites(
  sites: { id: string; name: string; geometry: GeoJSON.Polygon }[],
  factorIds: string[],
  scanner: string,
  signal?: AbortSignal,
): Promise<Comparison> {
  return post<Comparison>('/api/compare',
                          { sites, factor_ids: factorIds, scanner }, signal)
}
