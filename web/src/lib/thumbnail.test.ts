import { describe, expect, it } from 'vitest'
import { lonScale, relativeTime, thumbnailPath } from './thumbnail'

/**
 * The gallery thumbnail.
 *
 * Its whole job is recognition — you find a site by the shape you traced, not
 * by its name — so the tests are about the shape surviving the projection.
 * A squashed, flipped or stretched outline is not a smaller version of the
 * site; it is a different site, and it fails silently because it still looks
 * like a plausible field.
 */

const BOX = { width: 100, height: 70 }

/** A square on the ground near Guildford — equal metres each way, which in
 *  degrees means longitude spans more than latitude. */
function groundSquare(sideDeg = 0.01, lat = 51.24, lng = -0.57): GeoJSON.Polygon {
  const dLng = sideDeg / Math.cos((lat * Math.PI) / 180)
  return {
    type: 'Polygon',
    coordinates: [[
      [lng, lat], [lng + dLng, lat], [lng + dLng, lat + sideDeg],
      [lng, lat + sideDeg], [lng, lat],
    ]],
  }
}

function points(d: string): [number, number][] {
  return d.replace(/[MLZ]/g, ' ').trim().split(/\s+/)
    .reduce<number[][]>((acc, n, i) => {
      if (i % 2 === 0) acc.push([Number(n)])
      else acc[acc.length - 1].push(Number(n))
      return acc
    }, []).map((p) => [p[0], p[1]] as [number, number])
}

describe('thumbnailPath', () => {
  it('draws a square field as a square', () => {
    // The bug this exists to prevent: at 51°N a degree of longitude covers
    // about 0.63 of the ground a degree of latitude does, so normalising raw
    // coordinates stretches every English site sideways by roughly 1.6x.
    const pts = points(thumbnailPath(groundSquare(), BOX)!)
    const xs = pts.map((p) => p[0])
    const ys = pts.map((p) => p[1])
    const w = Math.max(...xs) - Math.min(...xs)
    const h = Math.max(...ys) - Math.min(...ys)
    expect(w / h).toBeCloseTo(1, 1)
  })

  it('puts north at the top', () => {
    // SVG y grows downward and latitude grows upward. Getting this wrong draws
    // every site upside down — subtle enough to ship, and fatal for the one
    // thing the thumbnail is for.
    const wedge: GeoJSON.Polygon = {
      type: 'Polygon',
      coordinates: [[[-0.57, 51.24], [-0.56, 51.24], [-0.565, 51.25], [-0.57, 51.24]]],
    }
    const pts = points(thumbnailPath(wedge, BOX)!)
    const northernmost = pts.reduce((a, b) => (b[1] < a[1] ? b : a))
    // The apex is the single northern point, so it must be the topmost drawn.
    expect(northernmost[1]).toBeLessThan(10)
  })

  it('keeps a long thin site long and thin', () => {
    const strip: GeoJSON.Polygon = {
      type: 'Polygon',
      coordinates: [[
        [-0.60, 51.240], [-0.50, 51.240], [-0.50, 51.2404], [-0.60, 51.2404],
        [-0.60, 51.240],
      ]],
    }
    const pts = points(thumbnailPath(strip, BOX)!)
    const w = Math.max(...pts.map((p) => p[0])) - Math.min(...pts.map((p) => p[0]))
    const h = Math.max(...pts.map((p) => p[1])) - Math.min(...pts.map((p) => p[1]))
    expect(w / h).toBeGreaterThan(20)
  })

  it('stays inside the box', () => {
    for (const g of [groundSquare(), groundSquare(0.2), groundSquare(0.0005)]) {
      for (const [x, y] of points(thumbnailPath(g, BOX)!)) {
        expect(x).toBeGreaterThanOrEqual(0)
        expect(y).toBeGreaterThanOrEqual(0)
        expect(x).toBeLessThanOrEqual(BOX.width)
        expect(y).toBeLessThanOrEqual(BOX.height)
      }
    }
  })

  it('centres what it draws', () => {
    // A wide site should sit in the middle of the card, not along its top edge.
    const wide: GeoJSON.Polygon = {
      type: 'Polygon',
      coordinates: [[
        [-0.60, 51.240], [-0.50, 51.240], [-0.50, 51.244], [-0.60, 51.244],
        [-0.60, 51.240],
      ]],
    }
    const ys = points(thumbnailPath(wide, BOX)!).map((p) => p[1])
    const mid = (Math.min(...ys) + Math.max(...ys)) / 2
    expect(mid).toBeCloseTo(BOX.height / 2, 0)
  })

  it('closes the path', () => {
    expect(thumbnailPath(groundSquare(), BOX)!.endsWith(' Z')).toBe(true)
  })

  it('returns null rather than drawing nothing meaningful', () => {
    // The caller must handle this. A card with no thumbnail is better than a
    // card with a dot in the middle pretending to be a site.
    expect(thumbnailPath(null, BOX)).toBeNull()
    expect(thumbnailPath(undefined, BOX)).toBeNull()
    expect(thumbnailPath({ type: 'Polygon', coordinates: [[]] }, BOX)).toBeNull()
    expect(thumbnailPath(
      { type: 'Polygon', coordinates: [[[-0.5, 51], [-0.5, 51]]] }, BOX)).toBeNull()
  })

  it('survives a degenerate zero-area shape', () => {
    const line: GeoJSON.Polygon = {
      type: 'Polygon',
      coordinates: [[[-0.5, 51], [-0.4, 51], [-0.3, 51], [-0.5, 51]]],
    }
    const d = thumbnailPath(line, BOX)
    expect(d === null || d.includes('NaN')).toBe(false)
  })
})

describe('lonScale', () => {
  it('narrows with latitude', () => {
    expect(lonScale(0)).toBeCloseTo(1, 3)
    expect(lonScale(51.24)).toBeCloseTo(0.626, 2)
    expect(lonScale(55)).toBeLessThan(lonScale(50))
  })
})

describe('relativeTime', () => {
  const now = Date.UTC(2026, 7, 9, 12, 0, 0)
  const ago = (ms: number) => relativeTime(now - ms, now)

  it('is coarse on purpose', () => {
    // A saved site is not an event log. Minute-level precision on a
    // three-week-old project implies a timeline nobody is tracking.
    expect(ago(30 * 1000)).toBe('just now')
    expect(ago(20 * 60 * 1000)).toBe('20 min ago')
    expect(ago(3 * 3600 * 1000)).toBe('3 hours ago')
    expect(ago(1 * 3600 * 1000)).toBe('1 hour ago')
    expect(ago(3 * 86400 * 1000)).toBe('3 days ago')
    expect(ago(1 * 86400 * 1000)).toBe('1 day ago')
    expect(ago(14 * 86400 * 1000)).toBe('2 weeks ago')
    expect(ago(60 * 86400 * 1000)).toBe('2 months ago')
    expect(ago(400 * 86400 * 1000)).toBe('1 year ago')
  })

  it('does not report the future as a long time ago', () => {
    // Clock skew between devices, or a restored backup written on a machine
    // running fast. "in -3 days" is worse than "just now".
    expect(relativeTime(now + 60_000, now)).toBe('just now')
  })
})
