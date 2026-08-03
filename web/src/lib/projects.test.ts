import { describe, expect, it } from 'vitest'
import { coerceProjects, copyName, relativeTime, thumbnailPath } from './projects'

const DEFAULTS = ['ndvi', 'lc_tree_pct']

/** A unit square, clockwise from the south-west corner. */
const SQUARE: GeoJSON.Polygon = {
  type: 'Polygon',
  coordinates: [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
}

function pointsOf(path: string): [number, number][] {
  return path
    .replace(/^M/, '')
    .replace(/Z$/, '')
    .split('L')
    .map((p) => p.split(',').map(Number) as [number, number])
}

describe('coerceProjects', () => {
  it('carries a legacy save forward, filling in what it never stored', () => {
    const legacy = [{
      id: 'a1', name: 'North field', geometry: SQUARE, area_ha: 12.5, savedAt: 1700000000000,
    }]
    const [p] = coerceProjects(legacy, DEFAULTS)

    expect(p.id).toBe('a1')
    expect(p.name).toBe('North field')
    expect(p.area_ha).toBe(12.5)
    // The two fields a legacy entry cannot have: factors fall back to the
    // app's defaults, and time means "latest" rather than a stale index.
    expect(p.factors).toEqual(DEFAULTS)
    expect(p.timeIndex).toBeNull()
    // savedAt is the only timestamp it had, so it seeds both.
    expect(p.createdAt).toBe(1700000000000)
    expect(p.updatedAt).toBe(1700000000000)
  })

  it('keeps a modern entry exactly as stored', () => {
    const stored = [{
      id: 'p9', name: 'Coppice', geometry: SQUARE, area_ha: 3,
      factors: ['ndvi'], timeIndex: 42, createdAt: 10, updatedAt: 99,
    }]
    expect(coerceProjects(stored, DEFAULTS)[0]).toMatchObject({
      id: 'p9', factors: ['ndvi'], timeIndex: 42, createdAt: 10, updatedAt: 99,
    })
  })

  it('drops entries without usable geometry rather than throwing', () => {
    // localStorage is user-writable and outlives any one version of the app,
    // so one bad row must not take the whole gallery down.
    const raw = [
      { id: 'ok', name: 'Fine', geometry: SQUARE, area_ha: 1 },
      { id: 'bad1', name: 'No geometry' },
      { id: 'bad2', name: 'Wrong type', geometry: { type: 'Point', coordinates: [0, 0] } },
      null,
      'not an object',
    ]
    const out = coerceProjects(raw, DEFAULTS)
    expect(out).toHaveLength(1)
    expect(out[0].id).toBe('ok')
  })

  it('returns nothing for a non-array', () => {
    expect(coerceProjects(null, DEFAULTS)).toEqual([])
    expect(coerceProjects({ nope: true }, DEFAULTS)).toEqual([])
  })

  it('substitutes a name and area when they are missing or unusable', () => {
    const [p] = coerceProjects(
      [{ geometry: SQUARE, name: '   ', area_ha: Number.NaN }], DEFAULTS)
    expect(p.name).toBe('Untitled site')
    expect(p.area_ha).toBe(0)
    expect(p.id).toBeTruthy()
  })
})

describe('thumbnailPath', () => {
  const box = { width: 200, height: 100, pad: 10 }

  it('fits the shape inside the padded box', () => {
    const pts = pointsOf(thumbnailPath(SQUARE, box))
    for (const [x, y] of pts) {
      expect(x).toBeGreaterThanOrEqual(box.pad - 0.05)
      expect(x).toBeLessThanOrEqual(box.width - box.pad + 0.05)
      expect(y).toBeGreaterThanOrEqual(box.pad - 0.05)
      expect(y).toBeLessThanOrEqual(box.height - box.pad + 0.05)
    }
  })

  it('puts north at the top', () => {
    // Latitude grows north; SVG y grows down. Without the flip every
    // thumbnail is its site upside down — which looks plausible on a square
    // and wrong on everything else.
    const pts = pointsOf(thumbnailPath(SQUARE, box))
    const southWest = pts[0]      // [0, 0]
    const northWest = pts[1]      // [0, 1]
    expect(northWest[1]).toBeLessThan(southWest[1])
  })

  it('preserves aspect ratio, so a long thin site still reads as one', () => {
    const wide: GeoJSON.Polygon = {
      type: 'Polygon',
      coordinates: [[[0, 0], [0, 1], [8, 1], [8, 0], [0, 0]]],
    }
    const pts = pointsOf(thumbnailPath(wide, box))
    const w = Math.max(...pts.map((p) => p[0])) - Math.min(...pts.map((p) => p[0]))
    const h = Math.max(...pts.map((p) => p[1])) - Math.min(...pts.map((p) => p[1]))
    expect(w / h).toBeCloseTo(8, 1)
  })

  it('centres the axis with slack', () => {
    // The square is limited by height in a 200x100 box, so it should sit in
    // the middle horizontally rather than hard against the left edge.
    const pts = pointsOf(thumbnailPath(SQUARE, box))
    const minX = Math.min(...pts.map((p) => p[0]))
    const maxX = Math.max(...pts.map((p) => p[0]))
    expect(minX + maxX).toBeCloseTo(box.width, 1)
  })

  it('survives degenerate and empty geometry', () => {
    const dot: GeoJSON.Polygon = {
      type: 'Polygon', coordinates: [[[5, 5], [5, 5], [5, 5], [5, 5]]],
    }
    // A zero-span ring would divide by zero; it must still produce something
    // finite rather than a path full of NaN.
    expect(thumbnailPath(dot, box)).not.toContain('NaN')
    expect(thumbnailPath({ type: 'Polygon', coordinates: [] }, box)).toBe('')
    expect(thumbnailPath({ type: 'Polygon', coordinates: [[[0, 0]]] }, box)).toBe('')
  })
})

describe('copyName', () => {
  it('numbers duplicates so two cards are never identical', () => {
    expect(copyName('Field', [])).toBe('Field copy')
    expect(copyName('Field', ['Field copy'])).toBe('Field copy 2')
    expect(copyName('Field', ['Field copy', 'Field copy 2'])).toBe('Field copy 3')
  })
})

describe('relativeTime', () => {
  const now = 1_700_000_000_000
  const ago = (ms: number) => relativeTime(now - ms, now)

  it('reads the way a gallery caption should', () => {
    expect(ago(5_000)).toBe('just now')
    expect(ago(5 * 60_000)).toBe('5 min ago')
    expect(ago(3 * 3_600_000)).toBe('3 hr ago')
    expect(ago(24 * 3_600_000)).toBe('yesterday')
    expect(ago(5 * 86_400_000)).toBe('5 days ago')
    expect(ago(400 * 86_400_000)).toBe('1 yr ago')
  })

  it('never reports the future as elapsed time', () => {
    expect(relativeTime(now + 60_000, now)).toBe('just now')
  })
})
