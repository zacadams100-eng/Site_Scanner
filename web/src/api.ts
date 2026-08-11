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

async function post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
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
  return res.json()
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
    { geometry, factor_ids: factorIds, scanner }, signal)
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

export function ask(
  geometry: GeoJSON.Polygon,
  question: string,
  signal?: AbortSignal,
): Promise<AskResponse> {
  return post<AskResponse>('/api/ask', { geometry, question }, signal)
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
