import { beforeEach, describe, expect, it, vi } from 'vitest'
import { exportSites, parseSitesFile, sitesFile } from './exports'
import type { SavedAoi } from '../store'

/**
 * Saved sites live in localStorage — one cleared browser, one new laptop, and
 * a term's worth of curated sites is gone. These pin the way out and the way
 * back in, including what happens when the file is partly rubbish.
 */

const written: string[] = []

beforeEach(() => {
  written.length = 0
  vi.stubGlobal('Blob', class {
    text_: string
    constructor(parts: string[]) { this.text_ = parts.join('') }
  })
  vi.stubGlobal('URL', {
    createObjectURL: (b: { text_: string }) => { written.push(b.text_); return 'blob:x' },
    revokeObjectURL: () => {},
  })
  vi.stubGlobal('document', {
    createElement: () => ({ click() {}, set href(_: string) {}, set download(_: string) {} }),
  })
})

const square: GeoJSON.Polygon = {
  type: 'Polygon',
  coordinates: [[[-0.58, 51.235], [-0.56, 51.235], [-0.56, 51.245], [-0.58, 51.245], [-0.58, 51.235]]],
}

const site: SavedAoi = {
  id: '1',
  name: 'Home farm',
  geometry: square,
  area_ha: 23.9,
  savedAt: 1700000000000,
  factors: ['ndvi', 'lst_day'],
  timeIndex: 12,
  compareIndex: 4,
}

describe('sitesFile', () => {
  it('stamps a format and version so a later change can migrate', () => {
    const f = sitesFile([site])
    expect(f.format).toBe('site-scanner.sites')
    expect(f.version).toBe(1)
    expect(f.sites).toHaveLength(1)
  })
})

describe('exportSites / parseSitesFile', () => {
  it('round-trips a site with its factors and time position intact', () => {
    exportSites([site])
    const back = parseSitesFile(written[0])
    expect(back).toHaveLength(1)
    expect(back[0].name).toBe('Home farm')
    expect(back[0].factors).toEqual(['ndvi', 'lst_day'])
    expect(back[0].timeIndex).toBe(12)
    expect(back[0].compareIndex).toBe(4)
    expect(back[0].geometry.coordinates[0]).toHaveLength(5)
  })

  it('keeps compareIndex: null distinct from "not recorded"', () => {
    const back = parseSitesFile(JSON.stringify({ sites: [{ ...site, compareIndex: null }] }))
    expect(back[0].compareIndex).toBeNull()
    const older = parseSitesFile(JSON.stringify({ sites: [{ ...site, compareIndex: undefined }] }))
    expect('compareIndex' in older[0]).toBe(false)
  })

  it('reads a bare array, which is what a hand-edited file usually is', () => {
    expect(parseSitesFile(JSON.stringify([site]))).toHaveLength(1)
  })

  it('restores what it can rather than refusing a part-damaged file', () => {
    const back = parseSitesFile(JSON.stringify({
      sites: [site, { name: 'No shape' }, { ...site, id: '2', geometry: { type: 'Point', coordinates: [0, 0] } }],
    }))
    expect(back).toHaveLength(1)
    expect(back[0].name).toBe('Home farm')
  })

  it('fills in a usable name and area when they are missing', () => {
    const back = parseSitesFile(JSON.stringify({ sites: [{ geometry: square }] }))
    expect(back[0].name).toBe('Untitled site')
    expect(back[0].area_ha).toBe(0)
    expect(back[0].savedAt).toBeGreaterThan(0)
  })

  it('says plainly when the file is not a sites file at all', () => {
    expect(() => parseSitesFile('not json')).toThrow(/not valid JSON/)
    expect(() => parseSitesFile('{"hello":1}')).toThrow(/list of saved sites/)
    expect(() => parseSitesFile('{"sites":[{"name":"x"}]}')).toThrow(/No usable sites/)
  })
})
