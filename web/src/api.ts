import type { Catalog, CellsResponse, SeriesResponse } from './types'

/**
 * Standalone builds answer from `src/demo/` instead of the network — same
 * shapes, same error wording, no server. Set at build time rather than
 * discovered at runtime so a standalone page never reaches for a host that
 * is not there: under the strict CSP one is published behind, a blocked
 * request is a console error and a delay before the fallback, which is a
 * worse first impression than simply not asking.
 */
export const STANDALONE = import.meta.env.VITE_STANDALONE === '1'

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

/**
 * Runs the demo generator and re-throws its errors as ApiError, so callers
 * cannot tell which source answered. Async despite being synchronous work:
 * the whole app awaits these, and resolving on a microtask keeps the loading
 * states behaving as they do against a real server.
 */
async function local<T>(run: () => T): Promise<T> {
  const { DemoError } = await import('./demo/source')
  try {
    return run()
  } catch (e) {
    if (e instanceof DemoError) throw new ApiError(e.message, e.status)
    throw e
  }
}

export async function fetchCatalog(): Promise<Catalog> {
  if (STANDALONE) {
    const { demoCatalog } = await import('./demo/source')
    return demoCatalog()
  }
  const res = await fetch('/api/catalog')
  if (!res.ok) throw new ApiError(`Catalogue unavailable (${res.status})`, res.status)
  return res.json()
}

export async function fetchSeries(
  geometry: GeoJSON.Polygon,
  factorIds: string[],
  signal?: AbortSignal,
): Promise<SeriesResponse> {
  if (STANDALONE) {
    const { demoSeries } = await import('./demo/source')
    return local(() => demoSeries(geometry, factorIds))
  }
  return post<SeriesResponse>('/api/series', { geometry, factor_ids: factorIds }, signal)
}

export async function fetchCells(
  geometry: GeoJSON.Polygon,
  signal?: AbortSignal,
): Promise<CellsResponse> {
  if (STANDALONE) {
    const { demoCells } = await import('./demo/source')
    return local(() => demoCells(geometry))
  }
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
