import { describe, expect, it, vi } from 'vitest'
import { looksLikePostcode, parseCoordinates, searchPlaces, withinCoverage } from './places'

const ENGLAND = { west: -6.42, south: 49.86, east: 1.77, north: 55.81 }

/** A stub `fetch` that answers by URL fragment, so the merge and failure paths
 *  are tested against the real response shapes rather than a mock of them. */
function stubFetch(routes: Record<string, unknown>, fail: string[] = []) {
  return vi.fn(async (url: string) => {
    if (fail.some((f) => url.includes(f))) return { ok: false, status: 503, json: async () => ({}) }
    const key = Object.keys(routes).find((k) => url.includes(k))
    return { ok: true, status: 200, json: async () => routes[key ?? ''] ?? { result: [] } }
  }) as unknown as typeof fetch
}

const PLACE = {
  result: [{ name_1: 'Guildford', county_unitary: 'Surrey', region: 'South East',
             code: 'osgb1', longitude: -0.57, latitude: 51.235 }],
}
const POSTCODE = {
  result: [{ postcode: 'GU2 7XH', admin_ward: 'Onslow', admin_district: 'Guildford',
             longitude: -0.589, latitude: 51.243 }],
}

describe('looksLikePostcode', () => {
  it('accepts whole and partial UK postcodes', () => {
    for (const q of ['GU2', 'gu2 7xh', 'GU27XH', 'M1', 'EC1A 1BB']) {
      expect(looksLikePostcode(q)).toBe(true)
    }
  })
  it('rejects place names', () => {
    for (const q of ['Guildford', 'York', '51.2, -0.5']) {
      expect(looksLikePostcode(q)).toBe(false)
    }
  })
})

describe('parseCoordinates', () => {
  it('reads lat, lng the way a user pastes it', () => {
    const p = parseCoordinates('51.235, -0.57')!
    expect(p.lat).toBeCloseTo(51.235)
    expect(p.lng).toBeCloseTo(-0.57)
    expect(p.kind).toBe('coords')
  })

  it('accepts a space instead of a comma', () => {
    expect(parseCoordinates('51.235 -0.57')!.lat).toBeCloseTo(51.235)
  })

  it('swaps a pair that can only be lng, lat rather than sending the user to sea', () => {
    const p = parseCoordinates('-179.5, 51.235')!
    expect(p.lat).toBeCloseTo(51.235)
    expect(p.lng).toBeCloseTo(-179.5)
  })

  it('refuses a pair that is not coordinates at all', () => {
    expect(parseCoordinates('200, 300')).toBeNull()
    expect(parseCoordinates('Guildford')).toBeNull()
  })
})

describe('withinCoverage', () => {
  it('knows England from not-England', () => {
    expect(withinCoverage({ lng: -0.57, lat: 51.235 }, ENGLAND)).toBe(true)
    expect(withinCoverage({ lng: -3.18, lat: 55.95 }, ENGLAND)).toBe(false)  // Edinburgh
  })
})

describe('searchPlaces', () => {
  it('does nothing for a query too short to mean anything', async () => {
    const f = stubFetch({})
    expect(await searchPlaces('g', undefined, f)).toEqual([])
    expect(f).not.toHaveBeenCalled()
  })

  it('answers typed coordinates without touching the network', async () => {
    const f = stubFetch({})
    const r = await searchPlaces('51.235, -0.57', undefined, f)
    expect(r).toHaveLength(1)
    expect(r[0].kind).toBe('coords')
    expect(f).not.toHaveBeenCalled()
  })

  it('looks up place names only, when the query is not postcode-shaped', async () => {
    const f = stubFetch({ '/places': PLACE, '/postcodes': POSTCODE })
    const r = await searchPlaces('Guildford', undefined, f)
    expect(r.map((p) => p.kind)).toEqual(['place'])
    expect(r[0].name).toBe('Guildford')
    expect(r[0].detail).toBe('Surrey, South East')
  })

  it('puts the postcode first when the query looks like one', async () => {
    const f = stubFetch({ '/places': PLACE, '/postcodes': POSTCODE })
    const r = await searchPlaces('GU2', undefined, f)
    expect(r[0].kind).toBe('postcode')
    expect(r[0].name).toBe('GU2 7XH')
    expect(r.some((p) => p.kind === 'place')).toBe(true)
  })

  it('zooms further into a postcode than into a town', async () => {
    const f = stubFetch({ '/places': PLACE, '/postcodes': POSTCODE })
    const r = await searchPlaces('GU2', undefined, f)
    const pc = r.find((p) => p.kind === 'postcode')!
    const place = r.find((p) => p.kind === 'place')!
    expect(pc.zoom).toBeGreaterThan(place.zoom)
  })

  it('still works when one of the two lookups is down', async () => {
    const f = stubFetch({ '/places': PLACE, '/postcodes': POSTCODE }, ['/postcodes'])
    const r = await searchPlaces('GU2', undefined, f)
    expect(r.map((p) => p.kind)).toEqual(['place'])
  })

  it('says what to do instead when the lookup is unreachable', async () => {
    const f = stubFetch({}, ['/places', '/postcodes'])
    await expect(searchPlaces('Guildford', undefined, f)).rejects.toThrow(/coordinates/)
  })

  it('treats a 404 as an empty result, not a failure', async () => {
    const f = vi.fn(async () => ({ ok: false, status: 404, json: async () => ({ result: null }) }))
    expect(await searchPlaces('Nowhere', undefined, f as unknown as typeof fetch)).toEqual([])
  })

  it('drops results with no coordinates rather than flying to null island', async () => {
    const f = stubFetch({ '/places': { result: [{ name_1: 'Broken' }] } })
    expect(await searchPlaces('Broken', undefined, f)).toEqual([])
  })
})
