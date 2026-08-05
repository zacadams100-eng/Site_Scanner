import { describe, expect, it } from 'vitest'
import { validateStyleMin } from '@maplibre/maplibre-gl-style-spec'

import {
  GLYPHS,
  VECTOR_SOURCE,
  VECTOR_SOURCE_ID,
  vectorBasemapLayers,
} from './basemapStyle'

/**
 * MapLibre validates a style at runtime, not at build time, so an invalid
 * expression is a blank basemap in production and a clean `tsc` and `vite
 * build` everywhere else. TypeScript does not help here: the expression types
 * are arrays of unknowns, so `['*', someInterpolate, 0.7]` type-checks
 * perfectly and is rejected by the renderer.
 *
 * That is not hypothetical — the first version of this style had four such
 * errors, all of them the same mistake of scaling a shared zoom interpolate,
 * and all four were caught here rather than by a person looking at a map.
 */
describe('vector basemap style', () => {
  const style = {
    version: 8 as const,
    glyphs: GLYPHS,
    sources: { [VECTOR_SOURCE_ID]: VECTOR_SOURCE },
    layers: [
      { id: 'bg', type: 'background' as const, paint: { 'background-color': '#e6ecee' } },
      ...vectorBasemapLayers(),
    ],
  }

  it('validates against the MapLibre style specification', () => {
    expect(validateStyleMin(style).map((e) => e.message)).toEqual([])
  })

  it('draws every layer from the one vector source', () => {
    for (const layer of vectorBasemapLayers()) {
      expect(layer).toHaveProperty('source', VECTOR_SOURCE_ID)
      expect(layer).toHaveProperty('source-layer')
    }
  })

  it('credits OpenStreetMap and OpenFreeMap', () => {
    // ODbL requires the credit, and this project's rule is that showing a
    // licence name is not the same as meeting its condition.
    expect(VECTOR_SOURCE.attribution).toMatch(/OpenStreetMap/)
    expect(VECTOR_SOURCE.attribution).toMatch(/OpenFreeMap/)
  })

  it('keeps labels above the zoom where place markers are drawn', () => {
    // Place names are DOM markers below ~z10.5; street labels starting any
    // earlier would collide with them.
    const label = vectorBasemapLayers().find((l) => l.type === 'symbol')
    expect(label?.minzoom).toBeGreaterThanOrEqual(13)
  })
})
