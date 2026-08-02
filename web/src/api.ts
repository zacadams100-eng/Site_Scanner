import type { Catalog, CellsResponse, SeriesResponse } from './types'

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

export async function fetchCatalog(): Promise<Catalog> {
  const res = await fetch('/api/catalog')
  if (!res.ok) throw new ApiError(`Catalogue unavailable (${res.status})`, res.status)
  return res.json()
}

export function fetchSeries(
  geometry: GeoJSON.Polygon,
  factorIds: string[],
  signal?: AbortSignal,
): Promise<SeriesResponse> {
  return post<SeriesResponse>('/api/series', { geometry, factor_ids: factorIds }, signal)
}

export function fetchCells(
  geometry: GeoJSON.Polygon,
  signal?: AbortSignal,
): Promise<CellsResponse> {
  return post<CellsResponse>('/api/cells', { geometry, resolution: 14 }, signal)
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
