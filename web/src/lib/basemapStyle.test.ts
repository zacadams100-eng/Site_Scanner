import { describe, expect, it } from 'vitest'
import { validateStyleMin } from '@maplibre/maplibre-gl-style-spec'

import {
  GLYPHS,
  VECTOR_LAYER_IDS,
  VECTOR_SOURCE,
  VECTOR_SOURCE_ID,
  belowVectorBasemap,
  resolveVectorSource,
  vectorBasemapLayers,
} from './basemapStyle'

const styleResponse = (body: unknown, ok = true) =>
  (async () => ({ ok, json: async () => body })) as unknown as typeof fetch

/**
 * The tile URL is read from OpenFreeMap's published style rather than
 * hardcoded, because hardcoding it from memory is exactly what produced a
 * basemap that rendered nothing and reported no error.
 */
describe('resolveVectorSource', () => {
  it('takes the vector source the provider declares', async () => {
    const source = await resolveVectorSource(
      styleResponse({
        sources: {
          maptiler_attribution: { type: 'vector', url: 'https://example.test/tiles.json' },
        },
      }),
    )
    expect(source.url).toBe('https://example.test/tiles.json')
  })

  it('ignores non-vector sources', async () => {
    const source = await resolveVectorSource(
      styleResponse({
        sources: {
          hillshade: { type: 'raster-dem', url: 'https://example.test/dem' },
          base: { type: 'vector', url: 'https://example.test/vector' },
        },
      }),
    )
    expect(source.url).toBe('https://example.test/vector')
  })

  it('keeps our attribution rather than the provider style’s', async () => {
    const source = await resolveVectorSource(
      styleResponse({
        sources: { base: { type: 'vector', url: 'https://x.test', attribution: 'someone else' } },
      }),
    )
    expect(source.attribution).toMatch(/OpenStreetMap/)
  })

  it('falls back to the documented endpoint when the style is unreachable', async () => {
    const rejecting = (async () => {
      throw new Error('offline')
    }) as unknown as typeof fetch
    expect(await resolveVectorSource(rejecting)).toEqual(VECTOR_SOURCE)
    expect(await resolveVectorSource(styleResponse({}, false))).toEqual(VECTOR_SOURCE)
  })
})

/**
 * The bundled basemap and the vector basemap are both added from async
 * callbacks. When both anchored on 'cells-fill', whichever resolved last sat
 * on top — and the bundled land layer is an opaque fill over all of England,
 * so when it won the race every vector layer was painted over and the map
 * looked precisely as though the tiles had never loaded. Silent, intermittent,
 * and indistinguishable from a broken tile source.
 */
describe('belowVectorBasemap', () => {
  it('anchors to the first vector layer present', () => {
    const present = new Set(['ofm-water', 'ofm-road', 'cells-fill'])
    expect(belowVectorBasemap((id) => present.has(id), 'cells-fill')).toBe('ofm-water')
  })

  it('falls back when the vector basemap has not arrived yet', () => {
    expect(belowVectorBasemap(() => false, 'cells-fill')).toBe('cells-fill')
    expect(belowVectorBasemap(() => false, undefined)).toBeUndefined()
  })

  it('lists exactly the layers that get added', () => {
    // A drifted list silently reintroduces the race for whichever layer is
    // missing from it.
    expect([...VECTOR_LAYER_IDS]).toEqual(vectorBasemapLayers().map((l) => l.id))
  })
})

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
