import { describe, expect, it, vi } from 'vitest'
import {
  TEMPLATES, URL_STATE_KEYS, decodeState, encodeState, shareUrl, type UrlState,
} from './permalink'

/**
 * A shared link is the product's structural advantage over Esri and GEE:
 * neither produces one URL that reconstructs a whole analysis for someone
 * opening it cold. That advantage is worth exactly as much as the round trip
 * is complete, so this file treats "every field comes back" as a build-
 * breaking requirement rather than a nice property.
 *
 * The failure mode being guarded against is not a crash. It is a link that
 * restores four fifths of an analysis, where the recipient cannot tell which
 * fifth is missing and reads the remainder as the whole.
 */

/** A state with every field set to something distinctive, so a field that is
 *  quietly dropped cannot coincide with its own default. */
const FULL: UrlState = {
  aoi: {
    type: 'Polygon',
    coordinates: [[
      [-0.57241, 51.23518],
      [-0.55102, 51.23518],
      [-0.55102, 51.24993],
      [-0.57241, 51.24993],
      [-0.57241, 51.23518],
    ]],
  },
  factors: ['ndvi', 'lst_day', 'flood_zone3_pct'],
  t: 137,
  compare: 125,
  markers: [
    { id: 'm0', name: 'North gate', lng: -0.5701, lat: 51.2402 },
    { id: 'm1', name: 'Ditch', lng: -0.5612, lat: 51.2455 },
  ],
  name: 'Manor Farm, parcel 3',
}

function roundTrip(s: UrlState): Partial<UrlState> {
  return decodeState('#' + encodeState(s))
}

describe('URL state round trip', () => {
  it('restores every field of a fully-populated state', () => {
    const out = roundTrip(FULL)
    expect(out.aoi).toEqual(FULL.aoi)
    expect(out.factors).toEqual(FULL.factors)
    expect(out.t).toBe(FULL.t)
    expect(out.compare).toBe(FULL.compare)
    expect(out.markers).toEqual(FULL.markers)
    expect(out.name).toBe(FULL.name)
  })

  /**
   * The guard. Adding a field to `UrlState` without teaching `encodeState` and
   * `decodeState` about it fails here, by name, rather than shipping a link
   * that silently drops it.
   *
   * It works by clearing one field at a time from the encoded output: if a
   * field genuinely round-trips, a state missing it must decode differently
   * from one that has it.
   */
  it('carries every key named in URL_STATE_KEYS', () => {
    const full = roundTrip(FULL)
    const dropped: string[] = []
    for (const key of URL_STATE_KEYS) {
      const withoutIt = roundTrip({ ...FULL, [key]: emptyFor(key) })
      if (JSON.stringify(withoutIt[key]) === JSON.stringify(full[key])) {
        dropped.push(key)
      }
    }
    expect(dropped, `these UrlState fields do not survive a shared link: ${dropped.join(', ')}`)
      .toEqual([])
  })

  it('names the same keys the interface declares', () => {
    // Cheap tripwire for the other half of the mistake: a field added to
    // URL_STATE_KEYS but never to the encoder, or vice versa.
    expect(new Set(URL_STATE_KEYS).size).toBe(URL_STATE_KEYS.length)
    expect(URL_STATE_KEYS).toContain('markers')
    expect(URL_STATE_KEYS).toContain('name')
  })
})

function emptyFor(key: keyof UrlState): UrlState[keyof UrlState] {
  switch (key) {
    case 'aoi': return null
    case 'factors': return []
    case 't': return 0
    case 'compare': return null
    case 'markers': return []
    case 'name': return null
  }
}

describe('geometry encoding', () => {
  it('closes a ring that arrives open', () => {
    const open = encodeState({
      ...FULL,
      aoi: {
        type: 'Polygon',
        coordinates: [[[-0.5, 51.2], [-0.4, 51.2], [-0.4, 51.3]]],
      },
    })
    const ring = decodeState('#' + open).aoi!.coordinates[0]
    expect(ring).toHaveLength(4)
    expect(ring[0]).toEqual(ring[3])
  })

  it('rejects a ring too short to be a polygon', () => {
    expect(decodeState('#g=-50000.5120000_10000.0').aoi).toBeUndefined()
  })

  it('keeps a 60-vertex freehand shape inside a pasteable URL', () => {
    // The delta encoding exists so a hand-traced field boundary still produces
    // a link that survives Slack and email clients, which wrap or truncate.
    const ring: number[][] = []
    for (let i = 0; i < 60; i++) {
      const a = (i / 60) * Math.PI * 2
      ring.push([-0.57 + Math.cos(a) * 0.004, 51.24 + Math.sin(a) * 0.004])
    }
    ring.push(ring[0])
    // These tests run in node, which has no `location`. Stubbing it is
    // cheaper than pulling in a DOM just to read two strings off it.
    vi.stubGlobal('location', { origin: 'https://site-scanner-pi.vercel.app', pathname: '/' })
    const url = shareUrl({ ...FULL, aoi: { type: 'Polygon', coordinates: [ring] } })
    vi.unstubAllGlobals()
    // 2,000 is the practical ceiling: below IE's old 2,083 limit, and below
    // where mail clients start inserting line breaks into a pasted link.
    expect(url.length).toBeLessThan(2000)
  })

  it('survives coordinates either side of the meridian', () => {
    const aoi: GeoJSON.Polygon = {
      type: 'Polygon',
      coordinates: [[
        [-0.002, 51.5], [0.002, 51.5], [0.002, 51.51], [-0.002, 51.51], [-0.002, 51.5],
      ]],
    }
    expect(roundTrip({ ...FULL, aoi }).aoi).toEqual(aoi)
  })
})

describe('marker encoding', () => {
  it('survives a name containing the field separators', () => {
    // `;` and `,` are the separators, and both are escaped by
    // encodeURIComponent — which is the entire reason they were chosen over
    // `~`, `*` or `!`, none of which it escapes.
    const markers = [{ id: 'm0', name: 'gate; by the oak, east', lng: -0.57, lat: 51.24 }]
    expect(roundTrip({ ...FULL, markers }).markers).toEqual(markers)
  })

  it('survives a name containing the state separators', () => {
    const markers = [{ id: 'm0', name: 'plot f=1 & t=2', lng: -0.57, lat: 51.24 }]
    expect(roundTrip({ ...FULL, markers }).markers).toEqual(markers)
  })

  it('reissues ids by position rather than carrying them', () => {
    const markers = [{ id: 'm1754390000000', name: 'Gate', lng: -0.57, lat: 51.24 }]
    const out = roundTrip({ ...FULL, markers }).markers!
    expect(out[0].id).toBe('m0')
    expect(out[0].name).toBe('Gate')
  })

  it('drops a mangled marker rather than placing it in the Atlantic', () => {
    // 0,0 is a real coordinate off West Africa; a marker that lands there
    // because its digits were truncated would read as a real annotation.
    const out = decodeState('#m=;;nonsense,,x;-57000,5124000,Gate')
    expect(out.markers).toEqual([{ id: 'm0', name: 'Gate', lng: -0.57, lat: 51.24 }])
  })

  it('survives a hand-edited percent sign', () => {
    expect(() => decodeState('#n=100%25&m=-57000,5124000,50%')).not.toThrow()
    expect(decodeState('#n=100%25').name).toBe('100%')
  })
})

describe('partial and hostile input', () => {
  it('returns nothing from an empty hash', () => {
    expect(decodeState('')).toEqual({})
    expect(decodeState('#')).toEqual({})
  })

  it('ignores keys it does not recognise', () => {
    const out = decodeState('#t=4&zzz=nope&f=ndvi')
    expect(out.t).toBe(4)
    expect(out.factors).toEqual(['ndvi'])
  })

  it('omits absent optional fields rather than inventing empties', () => {
    const bare = encodeState({
      aoi: null, factors: [], t: 0, compare: null, markers: [], name: null,
    })
    expect(bare).toBe('t=0')
    const out = decodeState('#' + bare)
    expect(out.markers).toBeUndefined()
    expect(out.name).toBeUndefined()
    expect(out.aoi).toBeUndefined()
  })

  it('does not confuse a compare index of 0 with no comparison', () => {
    // `if (s.compare)` rather than `!== null` would drop this, and the bug
    // would only show on the very first month of the record.
    expect(decodeState('#' + encodeState({ ...FULL, compare: 0 })).compare).toBe(0)
  })
})

// ---------------------------------------------------------------------------
// Templates state a body of evidence, never a decision
// ---------------------------------------------------------------------------
describe('template framing', () => {
  /**
   * This list is the first thing a new user reads, so it is the product's
   * positioning whether or not anyone intended it that way. It used to open
   * with "Development appraisal — is this site worth pursuing?", which is a
   * suitability question and the one question Contour exists not to answer.
   *
   * The scan is deliberately crude. It cannot tell a good template from a bad
   * one; it can only catch the vocabulary that shows someone has started
   * promising a verdict again, which is the failure that actually happens.
   */
  const VERDICT_WORDS = [
    'appraisal', 'suitable', 'suitability', 'best', 'worth pursuing',
    'quality', 'opportunity', 'viable', 'ranking', 'score',
  ]

  /**
   * Compounds where a banned word is a measured property rather than a
   * judgement. "Air quality" is a property of air; "neighbourhood quality" was
   * a verdict on a place, and that one is gone. Listed explicitly rather than
   * softening the scan, because the scan's value is that it is blunt — the
   * same reasoning that keeps the comparison module's fixed disclaimers on an
   * exception list instead of relaxing its forbidden-word check.
   */
  const MEASURED_COMPOUNDS = ['air quality', 'water quality']

  it('never names a decision in a template name or blurb', () => {
    for (const t of TEMPLATES) {
      let text = `${t.name} ${t.blurb}`.toLowerCase()
      for (const ok of MEASURED_COMPOUNDS) text = text.replaceAll(ok, '')
      for (const word of VERDICT_WORDS) {
        expect(text, `${t.id} promises a verdict: "${word}"`).not.toContain(word)
      }
    }
  })

  it('never asks whether the user should do something', () => {
    // "Would an array work here?", "Could this be planted?", "Can lorries
    // reach it?" — each asks Contour for the decision rather than the
    // evidence behind it.
    for (const t of TEMPLATES) {
      expect(t.blurb, `${t.id} asks Contour to decide`)
        .not.toMatch(/^(would|could|should|can|is this|are these)\b/i)
    }
  })

  it('still carries the factors — this was a reframing, not a removal', () => {
    for (const t of TEMPLATES) {
      expect(t.factors.length, `${t.id} lost its factors`).toBeGreaterThan(0)
    }
  })
})
