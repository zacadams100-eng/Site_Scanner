import { describe, expect, it } from 'vitest'
import { cropToAoi } from './mapImage'
import type { Map as MapLibreMap } from 'maplibre-gl'

/**
 * The crop is what makes the printed map look like a figure rather than a
 * screenshot. It is pure arithmetic over projected coordinates, so it can be
 * checked without a browser — and it is worth checking, because the failure
 * modes are quiet: an out-of-bounds source rectangle makes `drawImage`
 * produce transparent edges rather than an error, and a crop that misses the
 * boundary produces a report whose map does not show the site.
 */

/** A stub map: one pixel per 0.001° in both directions, 1000x800 canvas. */
function stubMap(clientWidth = 1000): MapLibreMap {
  return {
    project: ([lng, lat]: [number, number]) => ({
      x: (lng + 1) * 1000,
      y: (52 - lat) * 1000,
    }),
    getCanvas: () => ({ clientWidth }),
  } as unknown as MapLibreMap
}

function square(west: number, south: number, size: number): GeoJSON.Polygon {
  return {
    type: 'Polygon',
    coordinates: [[
      [west, south], [west + size, south], [west + size, south + size],
      [west, south + size], [west, south],
    ]],
  }
}

const CANVAS = { w: 1000, h: 800 }

describe('cropToAoi', () => {
  it('returns a 3:2 landscape frame', () => {
    const c = cropToAoi(stubMap(), square(-0.5, 51.5, 0.05), CANVAS.w, CANVAS.h)
    expect(c.w / c.h).toBeCloseTo(1.5, 2)
  })

  it('centres the frame on the site', () => {
    const aoi = square(-0.5, 51.5, 0.05)      // centre at (-0.475, 51.525)
    const c = cropToAoi(stubMap(), aoi, CANVAS.w, CANVAS.h)
    const centreX = c.x + c.w / 2
    const centreY = c.y + c.h / 2
    expect(centreX).toBeCloseTo(525, 0)       // (-0.475 + 1) * 1000
    expect(centreY).toBeCloseTo(475, 0)       // (52 - 51.525) * 1000
  })

  it('keeps the whole boundary inside the frame, with margin', () => {
    const aoi = square(-0.5, 51.5, 0.05)
    const c = cropToAoi(stubMap(), aoi, CANVAS.w, CANVAS.h)
    // The AOI spans x 500..550, y 450..500 in canvas pixels.
    expect(c.x).toBeLessThan(500)
    expect(c.x + c.w).toBeGreaterThan(550)
    expect(c.y).toBeLessThan(450)
    expect(c.y + c.h).toBeGreaterThan(500)
  })

  it('never leaves the canvas', () => {
    // A site hard against the corner: the frame has to slide, not overhang.
    for (const aoi of [square(-1, 51.95, 0.02), square(0.95, 51.0, 0.02)]) {
      const c = cropToAoi(stubMap(), aoi, CANVAS.w, CANVAS.h)
      expect(c.x).toBeGreaterThanOrEqual(0)
      expect(c.y).toBeGreaterThanOrEqual(0)
      expect(c.x + c.w).toBeLessThanOrEqual(CANVAS.w)
      expect(c.y + c.h).toBeLessThanOrEqual(CANVAS.h)
    }
  })

  it('gives a tiny site real context rather than magnifying one pixel', () => {
    const c = cropToAoi(stubMap(), square(-0.5, 51.5, 0.001), CANVAS.w, CANVAS.h)
    expect(c.w).toBeGreaterThan(200)
  })

  it('falls back to a centred band when nothing has been drawn', () => {
    const c = cropToAoi(stubMap(), null, CANVAS.w, CANVAS.h)
    expect(c.w / c.h).toBeCloseTo(1.5, 2)
    expect(c.x + c.w / 2).toBeCloseTo(CANVAS.w / 2, 0)
  })

  it('accounts for device pixel ratio', () => {
    // A retina canvas is twice the CSS size, so projected coordinates have to
    // be doubled before they mean anything in canvas pixels. Without this the
    // crop lands in the top-left quarter of the image.
    const aoi = square(-0.5, 51.5, 0.05)
    const c = cropToAoi(stubMap(1000), aoi, 2000, 1600)
    expect(c.x + c.w / 2).toBeCloseTo(1050, 0)   // 525 * 2
  })
})
