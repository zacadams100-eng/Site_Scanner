import { describe, expect, it } from 'vitest'
import {
  buildField, contourLevels, fbm, formatCoord, marchingSquares, pickLabels, project,
} from './heroField'

const BBOX = { minLon: -6, minLat: 49.9, maxLon: 1.8, maxLat: 55.8 }

describe('projection', () => {
  it('puts north above south and east right of west', () => {
    const p = project(BBOX, 800, 600)
    const [, yNorth] = p(0, 55)
    const [, ySouth] = p(0, 50)
    expect(yNorth).toBeLessThan(ySouth)
    const [xWest] = p(-5, 52)
    const [xEast] = p(1, 52)
    expect(xWest).toBeLessThan(xEast)
  })

  it('keeps the whole bbox inside the canvas', () => {
    const p = project(BBOX, 800, 600)
    for (const [lon, lat] of [
      [BBOX.minLon, BBOX.minLat], [BBOX.maxLon, BBOX.maxLat],
      [BBOX.minLon, BBOX.maxLat], [BBOX.maxLon, BBOX.minLat],
    ]) {
      const [x, y] = p(lon, lat)
      expect(x).toBeGreaterThanOrEqual(-0.001)
      expect(x).toBeLessThanOrEqual(800.001)
      expect(y).toBeGreaterThanOrEqual(-0.001)
      expect(y).toBeLessThanOrEqual(600.001)
    }
  })

  it('corrects for latitude rather than stretching the coastline sideways', () => {
    // One degree of longitude is shorter than one of latitude at 53°N. Without
    // the cosine term England comes out visibly too wide.
    const p = project(BBOX, 1000, 1000)
    const [x0] = p(0, 53); const [x1] = p(1, 53)
    const [, y0] = p(0, 53); const [, y1] = p(0, 54)
    expect(x1 - x0).toBeLessThan(y0 - y1)
  })
})

describe('noise is deterministic', () => {
  it('returns the same value for the same input, always', () => {
    expect(fbm(0.4, 0.7, 3)).toBe(fbm(0.4, 0.7, 3))
    expect(buildField(8, 8, 5).data).toEqual(buildField(8, 8, 5).data)
  })

  it('changes with the seed, so the sheet is choosable rather than fixed', () => {
    expect(fbm(0.4, 0.7, 1)).not.toBe(fbm(0.4, 0.7, 2))
  })

  it('stays inside 0..1, which the contour levels assume', () => {
    const f = buildField(24, 24, 9)
    for (const v of f.data) {
      expect(v).toBeGreaterThanOrEqual(0)
      expect(v).toBeLessThanOrEqual(1)
    }
  })
})

describe('contours', () => {
  it('produces no segments for a field entirely above or below the level', () => {
    const flat: { w: number; h: number; data: Float32Array } =
      { w: 4, h: 4, data: new Float32Array(16).fill(0.9) }
    expect(marchingSquares(flat, 0.5)).toEqual([])
    flat.data.fill(0.1)
    expect(marchingSquares(flat, 0.5)).toEqual([])
  })

  it('cuts a straight line across a simple gradient', () => {
    // Left half low, right half high: the 0.5 iso-line is one vertical run.
    const w = 4, h = 4
    const data = new Float32Array(w * h)
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) data[y * w + x] = x < 2 ? 0 : 1
    const segs = marchingSquares({ w, h, data }, 0.5)
    expect(segs.length).toBeGreaterThan(0)
    // Every segment sits on the same x, between the two columns.
    for (const [x1, , x2] of segs) {
      expect(x1).toBeCloseTo(1.5, 5)
      expect(x2).toBeCloseTo(1.5, 5)
    }
  })

  it('keeps every segment inside the field', () => {
    const f = buildField(32, 32, 4)
    for (const level of contourLevels(6)) {
      for (const [x1, y1, x2, y2] of marchingSquares(f, level)) {
        for (const v of [x1, x2]) expect(v).toBeLessThanOrEqual(f.w - 1)
        for (const v of [y1, y2]) expect(v).toBeLessThanOrEqual(f.h - 1)
        for (const v of [x1, y1, x2, y2]) expect(v).toBeGreaterThanOrEqual(0)
      }
    }
  })

  it('spaces levels evenly and excludes the degenerate extremes', () => {
    const levels = contourLevels(5)
    expect(levels).toHaveLength(5)
    expect(levels[0]).toBeGreaterThan(0)
    expect(levels[4]).toBeLessThan(1)
    const gaps = levels.slice(1).map((v, i) => v - levels[i])
    for (const g of gaps) expect(g).toBeCloseTo(gaps[0], 6)
  })
})

describe('label selection', () => {
  const place = (name: string, lon: number, lat: number, population: number) =>
    ({ properties: { name, population }, geometry: { coordinates: [lon, lat] as [number, number] } })

  it('takes the largest places first', () => {
    const picked = pickLabels(
      [place('Small', 0, 50, 10), place('Big', 3, 54, 900), place('Mid', -4, 52, 400)], 3)
    expect(picked.map((p) => p.name)).toEqual(['Big', 'Mid', 'Small'])
  })

  it('never stacks two labels on the same spot', () => {
    // Three towns within a tenth of a degree: only one may survive.
    const picked = pickLabels(
      [place('A', 0, 51, 900), place('B', 0.05, 51.02, 800), place('C', 0.02, 51.01, 700)], 3)
    expect(picked).toHaveLength(1)
    expect(picked[0].name).toBe('A')
  })

  it('numbers the survivors in order, so they can arrive in sequence', () => {
    const picked = pickLabels(
      [place('A', 0, 51, 900), place('B', 4, 54, 800), place('C', -4, 52, 700)], 3)
    expect(picked.map((p) => p.order)).toEqual([0, 1, 2])
  })

  it('ignores features with no name or no coordinates', () => {
    expect(pickLabels([
      { properties: { name: '', population: 900 }, geometry: { coordinates: [0, 51] } },
      { properties: { name: 'Real', population: 10 }, geometry: { coordinates: [3, 54] } },
      { properties: { name: 'Nowhere', population: 999 } },
    ], 5).map((p) => p.name)).toEqual(['Real'])
  })
})

describe('coordinate formatting', () => {
  it('reads like field equipment', () => {
    expect(formatCoord(51.2526, 'lat')).toBe('51.253°N')
    expect(formatCoord(-0.5761, 'lon')).toBe('0.576°W')
    expect(formatCoord(1.8, 'lon')).toBe('1.800°E')
  })
})
