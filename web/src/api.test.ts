import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, fetchSeries } from './api'

/**
 * What the user is told when a request goes wrong.
 *
 * Every case here was observed in a browser before it was written down: each
 * one produced a panel showing a stack trace, a parser message, or nothing at
 * all. The rule this suite defends is that a failure states what happened in
 * words a person can act on — the raw exception is a fact about our code, not
 * an explanation for the reader.
 */

const GEOM = { type: 'Polygon', coordinates: [[[0, 51], [0, 52], [1, 52], [0, 51]]] } as const
const call = () => fetchSeries(GEOM as never, ['ndvi'], 'land')

const respond = (body: string, init: ResponseInit = {}) => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
    new Response(body, { status: 200, headers: { 'Content-Type': 'application/json' }, ...init })))
}

afterEach(() => { vi.unstubAllGlobals() })

describe('assessment failures are explained, not dumped', () => {
  it('preserves the backend\'s own explanation, which is written for the user', async () => {
    respond(JSON.stringify({ detail: 'Area exceeds 250,000 ha' }), { status: 400 })
    await expect(call()).rejects.toThrow('Area exceeds 250,000 ha')
  })

  it('does not show the JSON parser\'s message for a truncated reply', async () => {
    respond('{"series": {')
    // Previously: "Expected property name or '}' in JSON at position 12".
    await expect(call()).rejects.toThrow(/could not read/i)
  })

  it('rejects a well-formed reply with no report in it', async () => {
    // A 200 carrying `{}` parses cleanly and used to fail several layers later
    // with "Cannot read properties of undefined (reading 'ndvi')".
    respond('{}')
    await expect(call()).rejects.toThrow(/no data in it/i)
  })

  it('rejects a reply whose series are missing even when other fields are present', async () => {
    respond(JSON.stringify({ area_ha: 100, steps: ['2024-01'] }))
    await expect(call()).rejects.toThrow(/no data in it/i)
  })

  it('reports a deadline as a wait that ended, not as an abort', async () => {
    // A backend that accepts the connection and never answers. Distinguishing
    // this from a user cancelling matters: the store deliberately swallows
    // AbortError, so a timeout arriving under that name would vanish and leave
    // the loading sequence running.
    const timeout = Object.assign(new Error('signal timed out'), { name: 'TimeoutError' })
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(timeout))
    await expect(call()).rejects.toThrow(/did not respond within 90 seconds/i)
    await expect(call()).rejects.toBeInstanceOf(ApiError)
  })

  it('lets a genuine cancellation through untouched', async () => {
    const abort = Object.assign(new Error('aborted'), { name: 'AbortError' })
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(abort))
    await expect(call()).rejects.toMatchObject({ name: 'AbortError' })
  })

  it('accepts a real report', async () => {
    respond(JSON.stringify({
      area_ha: 100, centroid: { lng: 0, lat: 51 }, precision: 'approx',
      steps: ['2024-01'], series: { ndvi: { values: [0.5] } },
    }))
    await expect(call()).resolves.toMatchObject({ area_ha: 100 })
  })
})
