import { beforeEach, describe, expect, it, vi } from 'vitest'
import { annualRows, exportAnnualCsv, exportGeoJson, exportXml } from './exports'
import { coverageValue, isPartialYear } from './format'
import type { AnnualRow, Series } from '../types'

/**
 * The caveat has to survive leaving the app.
 *
 * NDVI's first year is 2017, and Sentinel-2 only starts that March — so the
 * row averages ten months and is missing January and February, the two lowest
 * of the year. It reads as the highest NDVI on record when it is really a year
 * with its winter cut off. The table marked that with a dot; every export
 * dropped it, so a chart built in Excel showed a spike that does not exist.
 *
 * These tests pin the caveat to each way data leaves.
 */

/** Captures whatever the export helpers hand to Blob, so the assertions run
 *  against the real file contents rather than a mock of them. */
const written: string[] = []

beforeEach(() => {
  written.length = 0
  vi.stubGlobal('Blob', class {
    text_: string
    type?: string
    constructor(parts: string[], opts?: { type?: string }) {
      this.text_ = parts.join('')
      this.type = opts?.type
    }
  })
  vi.stubGlobal('URL', {
    createObjectURL: (b: { text_: string }) => { written.push(b.text_); return 'blob:x' },
    revokeObjectURL: () => {},
  })
  vi.stubGlobal('document', {
    createElement: () => ({ click() {}, set href(_: string) {}, set download(_: string) {} }),
  })
})

const row = (year: number, value: number | null, observed: number,
             total = 12): AnnualRow => ({
  year, value, min: 0, max: 1,
  months_observed: observed, months_total: total, confidence: observed / total,
})

const ndvi = {
  factor_id: 'ndvi',
  unit: 'index',
  source: 'earth-engine',
  meta: {
    name: 'NDVI', unit: 'index',
    base_meta: {
      id: 's2', name: 'Sentinel-2', source: 'ESA',
      licence: 'CC BY-SA 3.0 IGO', resolution_m: 10,
    },
  },
  points: [],
  annual: [row(2016, null, 0), row(2017, 0.8, 10), row(2018, 0.7, 12)],
} as unknown as Series

describe('isPartialYear', () => {
  it('is true for a year built from fewer months than it should be', () => {
    expect(isPartialYear(row(2017, 0.8, 10))).toBe(true)
  })

  it('is false for a complete year', () => {
    expect(isPartialYear(row(2018, 0.7, 12))).toBe(false)
  })

  it('is false when there is no value to caveat', () => {
    expect(isPartialYear(row(2016, null, 0))).toBe(false)
  })
})

describe('coverageValue', () => {
  it('is a bare integer — "10/12" is silently read as a date by Excel', () => {
    const v = coverageValue(row(2017, 0.8, 10))
    expect(v).toBe('10')
    expect(v).not.toContain('/')
  })

  it('is blank for a year with no value', () => {
    expect(coverageValue(row(2016, null, 0))).toBe('')
  })
})

describe('annualRows', () => {
  it('adds a months-observed column beside each factor', () => {
    expect(annualRows([ndvi]).header)
      .toEqual(['Year', 'NDVI (index)', 'NDVI months observed'])
  })

  it('carries the count through for short and full years alike', () => {
    const { rows } = annualRows([ndvi])
    expect(rows[1]).toEqual(['2017', '0.8', '10'])
    expect(rows[2]).toEqual(['2018', '0.7', '12'])
  })
})

describe('exportAnnualCsv', () => {
  it('writes the coverage column and says what it means', () => {
    exportAnnualCsv([ndvi], 23.9)
    const csv = written[0]
    expect(csv).toContain('NDVI months observed')
    expect(csv).toContain('2017,0.8,10')
    expect(csv).toMatch(/not comparable/)
  })
})

describe('exportGeoJson', () => {
  it('adds coverage without changing the shape anything already reads', () => {
    exportGeoJson({ type: 'Polygon', coordinates: [[]] } as GeoJSON.Polygon, [ndvi], 23.9)
    const props = JSON.parse(written[0]).features[0].properties
    expect(props.ndvi['2017']).toBe(0.8)
    expect(props.ndvi__months_observed['2017']).toBe(10)
    expect(props.ndvi__months_observed['2016']).toBeNull()
  })
})

describe('exportXml', () => {
  it('emits coverage as a real numeric column, since Excel is where a '
     + 'spurious spike gets charted', () => {
    exportXml([ndvi])
    expect(written[0]).toContain('NDVI months observed')
    expect(written[0]).toContain('<Data ss:Type="Number">10</Data>')
  })
})
