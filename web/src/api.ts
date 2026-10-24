import type { Info, Layer, SheetRecord } from './types'

/**
 * The backend returns a plain-language `detail` for anything a user can fix
 * (red line too big, not an area). Surfacing that verbatim is better than a
 * generic failure message, so this preserves it.
 */
export class ApiError extends Error {
  readonly status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
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

export const fetchInfo = () => call<Info>('/api/info')
export const fetchLayers = () => call<Layer[]>('/api/layers')

export function makeSheet(
  redLine: GeoJSON.Polygon, title: string, clientRef: string, signal?: AbortSignal,
): Promise<SheetRecord> {
  return call<SheetRecord>('/api/sheet', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ red_line: redLine, title, client_ref: clientRef }),
    signal,
  })
}
