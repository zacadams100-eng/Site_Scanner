import { beforeEach, describe, expect, it, vi } from 'vitest'
import { compareRows, exportCompareCsv } from './exports'
import type { Point, Series } from '../types'

/**
 * The change table, on its way out of the app.
 *
 * A spreadsheet is exactly where an invented zero would be read as a measured
 * "no change", so the rules the Compare panel applies — no delta across a gap,
 * changed/no change for a class code — have to survive the export.
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

const pt = (t: string, value: number | string | null): Point =>
  ({ t, value, valid_fraction: value === null ? 0 : 0.9, interpolated: false })

function series(id: string, name: string, unit: string, points: Point[]): Series {
  return {
    factor_id: id, unit, source: 'earth-engine', points, annual: [],
    meta: {
      name, unit,
      base_meta: { name: 'Sentinel-2', attribution: 'Contains modified Copernicus data' },
    },
  } as unknown as Series
}

const ndvi = series('ndvi', 'NDVI', 'index',
  [pt('2023-07', 0.4), pt('2024-07', 0.5), pt('2025-07', null)])
const cover = series('lc_dominant', 'Dominant land cover', 'class',
  [pt('2023-07', 'Cropland'), pt('2024-07', 'Built-up'), pt('2025-07', 'Built-up')])

describe('compareRows', () => {
  it('reports the difference and the percentage for a number', () => {
    const { header, rows } = compareRows([ndvi], 0, 1)
    expect(header).toEqual(['Factor', 'Unit', '2023-07', '2024-07', 'Change', 'Change %'])
    expect(rows[0]).toEqual(['NDVI', 'index', '0.4', '0.5', '0.1', '25.0'])
  })

  it('orders the pair by time whichever way round it was pinned', () => {
    expect(compareRows([ndvi], 1, 0).rows[0]).toEqual(compareRows([ndvi], 0, 1).rows[0])
  })

  it('never averages a class — it says changed or not', () => {
    expect(compareRows([cover], 0, 1).rows[0][4]).toBe('changed')
    expect(compareRows([cover], 1, 2).rows[0][4]).toBe('no change')
  })

  it('leaves the change blank across a gap rather than implying zero', () => {
    const r = compareRows([ndvi], 1, 2).rows[0]
    expect(r[3]).toBe('')       // the gap end has no value
    expect(r[4]).toBe('')       // and therefore no delta
    expect(r[5]).toBe('')
  })

  it('omits the percentage when the earlier value is zero', () => {
    const zero = series('z', 'Zero start', 'mm', [pt('2023-07', 0), pt('2024-07', 5)])
    expect(compareRows([zero], 0, 1).rows[0]).toEqual(
      ['Zero start', 'mm', '0', '5', '5', ''])
  })
})

describe('exportCompareCsv', () => {
  it('carries the both-months caveat and the licence notice into the file', () => {
    exportCompareCsv([ndvi, cover], 0, 1)
    const csv = written[0]
    expect(csv).toContain('NDVI,index,0.4,0.5,0.1,25.0')
    expect(csv).toContain('Dominant land cover,class,Cropland,Built-up,changed')
    expect(csv).toMatch(/carries their weather with it/)
    expect(csv).toContain('Contains modified Copernicus data')
  })
})
