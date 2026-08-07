import { describe, expect, it } from 'vitest'
import { validateStyleMin } from '@maplibre/maplibre-gl-style-spec'
import { MIN_CONFIDENCE_ALPHA, confidenceAlpha, confidenceBand } from './format'

/**
 * Confidence on the map.
 *
 * Every general-purpose GIS tool renders all pixels at equal weight, so a
 * December mean scraped from 8% cloud-free coverage looks exactly as
 * authoritative as a clear June. The attribute table has said otherwise for a
 * while; the map — which is the thing people screenshot and paste into a
 * report — has not.
 *
 * The property being defended is narrow and worth stating: low confidence must
 * look *weaker*, never *absent*. A month with a poor observation still has a
 * value, and rendering nothing would replace an honest weak reading with the
 * appearance of no data, which is a different claim and a false one.
 */

describe('confidenceAlpha', () => {
  it('never renders a real observation invisible', () => {
    for (const f of [0, 0.01, 0.05, 0.1, 0.2]) {
      expect(confidenceAlpha(f)).toBeGreaterThanOrEqual(MIN_CONFIDENCE_ALPHA)
    }
  })

  it('paints a fully-observed month at full strength', () => {
    expect(confidenceAlpha(1)).toBeCloseTo(1, 5)
  })

  it('rises monotonically with coverage', () => {
    const steps = [0, 0.1, 0.25, 0.4, 0.6, 0.8, 1]
    const alphas = steps.map(confidenceAlpha)
    for (let i = 1; i < alphas.length; i++) {
      expect(alphas[i]).toBeGreaterThan(alphas[i - 1])
    }
  })

  it('separates the bands the rest of the UI already uses', () => {
    // A user should be able to tell a `poor` cell from a `good` one at a
    // glance, without reading a number. If these ever converge, the overlay
    // has stopped carrying the information it exists to carry.
    const poor = confidenceAlpha(0.2)
    const fair = confidenceAlpha(0.55)
    const good = confidenceAlpha(0.85)
    expect(confidenceBand(0.2)).toBe('poor')
    expect(confidenceBand(0.55)).toBe('fair')
    expect(confidenceBand(0.85)).toBe('good')
    expect(fair - poor).toBeGreaterThan(0.1)
    expect(good - fair).toBeGreaterThan(0.05)
  })

  it('does not collapse the low end into one indistinguishable smear', () => {
    // The reason for the square root. Under a linear ramp everything below
    // about 0.5 looked the same, which is exactly the range where the
    // distinction matters most.
    expect(confidenceAlpha(0.3) - confidenceAlpha(0.05)).toBeGreaterThan(0.1)
  })

  it('treats a missing fraction as full confidence rather than none', () => {
    // Static factors — a designation, a census figure — have no observed
    // fraction at all. Fading those would invent a doubt nobody claimed.
    expect(confidenceAlpha(undefined)).toBe(1)
    expect(confidenceAlpha(NaN)).toBe(1)
  })

  it('clamps a fraction outside 0..1', () => {
    expect(confidenceAlpha(-0.5)).toBe(MIN_CONFIDENCE_ALPHA)
    expect(confidenceAlpha(3)).toBeCloseTo(1, 5)
  })
})

describe('the cell paint expression', () => {
  /** The expression MapCanvas installs, in both the initial layer and the
   *  overlay-slider effect. Kept here so a change to one that is not made to
   *  the other is caught. */
  const paintExpression = (overlay: number) =>
    ['*', ['coalesce', ['get', 'alpha'], 1], overlay]

  it('is a valid MapLibre expression', () => {
    const errors = validateStyleMin({
      version: 8,
      sources: { cells: { type: 'geojson', data: { type: 'FeatureCollection', features: [] } } },
      layers: [{
        id: 'cells-fill',
        type: 'fill',
        source: 'cells',
        paint: {
          'fill-color': ['get', 'color'],
          'fill-opacity': paintExpression(0.72),
        },
      }],
    } as never)
    expect(errors.map((e) => e.message)).toEqual([])
  })

  it('composes confidence with the user overlay rather than replacing it', () => {
    // The bug this guards against: `setPaintProperty(..., overlayOpacity)`
    // with a bare number, which silently discards every cell's confidence the
    // first time the slider is touched.
    const expr = paintExpression(0.5)
    expect(expr[0]).toBe('*')
    expect(expr[2]).toBe(0.5)
    expect(JSON.stringify(expr)).toContain('alpha')
  })

  it('defaults a cell with no alpha to full strength', () => {
    // Cells are set on the source before the first repaint computes an alpha.
    // Without the coalesce those render at zero opacity — an invisible map
    // that looks exactly like a failed query.
    expect(paintExpression(0.72)[1]).toEqual(['coalesce', ['get', 'alpha'], 1])
  })
})
