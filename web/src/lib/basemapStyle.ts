/**
 * The close-range basemap: OpenStreetMap vector tiles, styled to match this app.
 *
 * Why vector rather than the raster tiles this replaced. Raster tiles arrive as
 * pictures with someone else's cartography already baked in, so the only way to
 * make them sit under our data was to wash them out — `raster-saturation: -0.8`
 * and 62% opacity. That is why zooming in used to hand you a grey OpenStreetMap
 * with the app's palette abandoned at the exact moment the map became detailed
 * enough to analyse. Vector tiles carry geometry instead, so every colour below
 * is ours and full detail costs no fidelity.
 *
 * Tiles come from OpenFreeMap: free, no API key, no usage ceiling, OSM data on
 * the OpenMapTiles schema. No key matters more than it sounds — this repository
 * is public, so a keyed provider means a secret to leak or an environment
 * variable to plumb through every deploy. It also retires the note in DEPLOY.md
 * about OSM's tile usage policy not covering production traffic.
 *
 * The palette is the bundled basemap's, deliberately. The two overlap between
 * about z10 and z12 and one must become the other without a visible seam.
 */

import type {
  ExpressionSpecification,
  LayerSpecification,
  VectorSourceSpecification,
} from 'maplibre-gl'

export const VECTOR_SOURCE_ID = 'ofm'

/** Every layer id this module adds, in draw order. Exported so MapCanvas can
 *  anchor the bundled basemap beneath them without knowing the ids. */
export const VECTOR_LAYER_IDS = [
  'ofm-landcover',
  'ofm-landuse',
  'ofm-park',
  'ofm-water',
  'ofm-waterway',
  'ofm-building',
  'ofm-rail',
  'ofm-road-casing',
  'ofm-road',
  'ofm-road-label',
  'ofm-place-major',
  'ofm-place-minor',
] as const

/**
 * Where place naming hands over from the bundled basemap to the vector tiles.
 *
 * The bundled places are Natural Earth populated points — cities and larger
 * towns, a few hundred across England. That is the right dataset for finding a
 * site and the wrong one for looking at it: zoom into a village and there is
 * simply no point in the file, so the labels stop exactly when you arrive.
 * OSM's `place` layer has villages, hamlets, suburbs and neighbourhoods.
 *
 * Both must not draw at once or every town gets named twice, so this is the
 * single zoom that switches one off and the other on.
 */
export const PLACE_HANDOVER_ZOOM = 11

/** Which bundled places are worth naming at this zoom.
 *
 *  A map with every town on it at national zoom is unreadable, and one with
 *  only London on it at county zoom is useless. The threshold falls as you
 *  come in, which is how a paper atlas does it too — until the handover, where
 *  an unreachable cutoff switches the bundled markers off entirely. Returning
 *  0 there drew every Natural Earth town on top of the vector label for the
 *  same town. */
export function placeCutoff(zoom: number): number {
  if (zoom < 6) return 700_000
  if (zoom < 7) return 400_000
  if (zoom < 8) return 200_000
  if (zoom < 9) return 90_000
  if (zoom < 10.5) return 40_000
  if (zoom >= PLACE_HANDOVER_ZOOM) return Infinity
  return 0
}

/**
 * Where a layer must be inserted to sit *below* the vector basemap.
 *
 * Both basemaps are added from async callbacks and both used to anchor on
 * `cells-fill`, so the one whose fetch resolved last ended up on top. That is
 * a race with a silent loser: the bundled `bm-land` is an opaque fill covering
 * all of England, so when it won, every vector layer beneath it was painted
 * over and the map looked exactly as though the tiles had never loaded.
 *
 * Anchoring the bundled layers to the first vector layer that exists — and the
 * vector layers to `cells-fill` — makes the stack the same either way:
 * sea, bundled basemap, vector basemap, then our data.
 */
export function belowVectorBasemap(
  hasLayer: (id: string) => boolean,
  fallback: string | undefined,
): string | undefined {
  return VECTOR_LAYER_IDS.find(hasLayer) ?? fallback
}

/** ODbL requires the OSM credit; OpenFreeMap asks for its own. This project
 *  carries the notice every licence actually requires rather than just naming
 *  the licence, so both appear. */
const ATTRIBUTION =
  '<a href="https://openfreemap.org" target="_blank" rel="noreferrer">OpenFreeMap</a> ' +
  '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a>'

/** OpenFreeMap's published style. Not used for its layers — those are ours —
 *  but for the one fact only it can state authoritatively: where its tiles
 *  actually live. */
const PUBLISHED_STYLE = 'https://tiles.openfreemap.org/styles/liberty'

/** The documented tile endpoint, used only if the style above is unreachable. */
export const VECTOR_SOURCE: VectorSourceSpecification = {
  type: 'vector',
  url: 'https://tiles.openfreemap.org/planet',
  attribution: ATTRIBUTION,
}

/**
 * Resolve the vector source by reading OpenFreeMap's own style.
 *
 * The first version of this file hardcoded the TileJSON URL from memory and
 * the basemap silently rendered nothing — a wrong source produces no error a
 * user can see, just an absence, which is the same class of failure as the
 * MapLibre worker returning index.html. Asking the provider where its tiles
 * are removes the guess: whatever URL its own style declares is by definition
 * the right one, and it keeps working if they move.
 *
 * Falls back to the documented endpoint so an unreachable style file costs a
 * round trip rather than the basemap.
 */
export async function resolveVectorSource(
  fetchImpl: typeof fetch = fetch,
): Promise<VectorSourceSpecification> {
  try {
    const res = await fetchImpl(PUBLISHED_STYLE)
    if (!res.ok) return VECTOR_SOURCE
    const style = (await res.json()) as { sources?: Record<string, unknown> }
    const vector = Object.values(style.sources ?? {}).find(
      (s): s is VectorSourceSpecification =>
        !!s && typeof s === 'object' && (s as { type?: string }).type === 'vector',
    )
    return vector ? { ...vector, attribution: ATTRIBUTION } : VECTOR_SOURCE
  } catch {
    return VECTOR_SOURCE
  }
}

/** Glyphs for street labels. Only fetched when a text layer is actually drawn. */
export const GLYPHS = 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf'

/**
 * Handover with the bundled basemap. Those layers fade out across 10.5–13;
 * these fade in just under that so there is always something on screen. Full
 * opacity at the top by default: unlike the raster this replaced, the palette
 * is already ours, so there is nothing to suppress.
 *
 * Written as a function returning a complete interpolate rather than a
 * constant that callers scale, because MapLibre requires `zoom` to be the
 * direct input of a top-level `interpolate` or `step`. Multiplying a shared
 * FADE constant by 0.7 nests the zoom expression and the style is rejected at
 * runtime — which the build does not catch, so `npm run validate:style` does.
 */
const fade = (max = 1): ExpressionSpecification => [
  'interpolate', ['linear'], ['zoom'],
  9.5, 0,
  11.5, max,
]

/* The cartography is a bone ground with khaki vegetation and a muted mineral
   water — a vintage topographic sheet rather than a road atlas. Deliberately
   low-contrast: this is the surface the drawn site, the value ramp and the
   signal-orange markers sit on top of, and every step it takes towards being
   interesting is a step the data takes towards being unreadable. */
const LAND = '#f6f3ea'
const URBAN = '#e7e2d4'
const GREEN = '#e2e7d8'
const WATER = '#dae4e2'
const WATER_LINE = '#b3c5c0'
const BUILDING = '#e3ddcd'
const BUILDING_LINE = '#d2cbb8'
const ROAD_CASING = '#fdfcf7'
const ROAD_MAJOR = '#9aa184'
const ROAD_MINOR = '#c6c0ad'
const RAIL = '#a8a291'
const LABEL = '#6a6a5b'
const PLACE_LABEL = '#3f453c'
const LABEL_HALO = '#f6f3ea'

/** Road classes, widest first — the order they must be drawn in. */
const MAJOR = ['motorway', 'trunk', 'primary']

/** Relative width by road class. A motorway and a service road are not the
 *  same object, and drawing them the same width is what turns a street network
 *  into spaghetti. */
const classScale: ExpressionSpecification = [
  'match', ['get', 'class'],
  'motorway', 1.5,
  'trunk', 1.3,
  'primary', 1.1,
  'secondary', 0.9,
  'tertiary', 0.75,
  'minor', 0.6,
  'service', 0.45,
  ['path', 'track'], 0.3,
  0.5,
]

/** Width ramp, class scaling applied to each stop.
 *
 *  The class factor has to live inside the stops rather than multiplying the
 *  whole ramp, for the same reason `fade` is a function: `zoom` must be the
 *  direct input of the top-level interpolate. Stop *outputs* may be arbitrary
 *  expressions, which is what makes this legal. */
const widthFor = (mult: number): ExpressionSpecification => [
  'interpolate', ['exponential', 1.4], ['zoom'],
  10, ['*', classScale, 0.6 * mult],
  14, ['*', classScale, 2.2 * mult],
  18, ['*', classScale, 9 * mult],
]

/**
 * Layers for the vector basemap, in draw order.
 *
 * All of them are inserted beneath the app's own layers, and every one is
 * decoration: if the tile host is unreachable, nothing here renders and the
 * bundled basemap continues to carry the map. That is the same contract the
 * raster had, and it is the reason the basemap is never part of the initial
 * style — an unloaded source keeps the whole style unloaded, which would block
 * the user's own data behind a third party being up.
 */
export function vectorBasemapLayers(): LayerSpecification[] {
  const s = VECTOR_SOURCE_ID
  return [
    {
      id: 'ofm-landcover',
      type: 'fill',
      source: s,
      'source-layer': 'landcover',
      filter: ['match', ['get', 'class'], ['wood', 'grass', 'farmland'], true, false],
      paint: { 'fill-color': GREEN, 'fill-opacity': fade() },
    },
    {
      id: 'ofm-landuse',
      type: 'fill',
      source: s,
      'source-layer': 'landuse',
      filter: ['match', ['get', 'class'], ['residential', 'commercial', 'industrial'], true, false],
      paint: { 'fill-color': URBAN, 'fill-opacity': fade(0.7) },
    },
    {
      id: 'ofm-park',
      type: 'fill',
      source: s,
      'source-layer': 'park',
      paint: { 'fill-color': GREEN, 'fill-opacity': fade(0.8) },
    },
    {
      id: 'ofm-water',
      type: 'fill',
      source: s,
      'source-layer': 'water',
      paint: { 'fill-color': WATER, 'fill-opacity': fade() },
    },
    {
      id: 'ofm-waterway',
      type: 'line',
      source: s,
      'source-layer': 'waterway',
      paint: {
        'line-color': WATER_LINE,
        'line-width': ['interpolate', ['linear'], ['zoom'], 11, 0.6, 17, 3],
        'line-opacity': fade(),
      },
    },
    {
      // The single biggest reason close-up detail reads as a real map. Buildings
      // only exist in OSM above about z13, hence the later fade.
      id: 'ofm-building',
      type: 'fill',
      source: s,
      'source-layer': 'building',
      minzoom: 13,
      paint: {
        'fill-color': BUILDING,
        'fill-outline-color': BUILDING_LINE,
        'fill-opacity': ['interpolate', ['linear'], ['zoom'], 13, 0, 15, 0.9],
      },
    },
    {
      id: 'ofm-rail',
      type: 'line',
      source: s,
      'source-layer': 'transportation',
      filter: ['==', ['get', 'class'], 'rail'],
      paint: {
        'line-color': RAIL,
        'line-width': ['interpolate', ['linear'], ['zoom'], 11, 0.6, 17, 2],
        'line-dasharray': [3, 2],
        'line-opacity': fade(0.8),
      },
    },
    {
      // Casing under fill, so a junction reads as one road crossing another
      // rather than as a blob.
      id: 'ofm-road-casing',
      type: 'line',
      source: s,
      'source-layer': 'transportation',
      filter: ['!=', ['get', 'class'], 'rail'],
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: {
        'line-color': ROAD_CASING,
        'line-width': widthFor(2.1),
        'line-opacity': fade(),
      },
    },
    {
      id: 'ofm-road',
      type: 'line',
      source: s,
      'source-layer': 'transportation',
      filter: ['!=', ['get', 'class'], 'rail'],
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: {
        'line-color': [
          'match', ['get', 'class'], MAJOR, ROAD_MAJOR, ROAD_MINOR,
        ] as ExpressionSpecification,
        'line-width': widthFor(1),
        'line-opacity': fade(),
      },
    },
    {
      // Street names. Held back to z14 — earlier than that they crowd out the
      // app's own place labels, which are drawn from the bundled basemap.
      id: 'ofm-road-label',
      type: 'symbol',
      source: s,
      'source-layer': 'transportation_name',
      minzoom: 14,
      layout: {
        'symbol-placement': 'line',
        'text-field': ['coalesce', ['get', 'name:en'], ['get', 'name']],
        'text-font': ['Noto Sans Regular'],
        'text-size': ['interpolate', ['linear'], ['zoom'], 14, 10, 18, 13],
        'text-max-angle': 30,
      } as LayerSpecification['layout'],
      paint: {
        'text-color': LABEL,
        'text-halo-color': LABEL_HALO,
        'text-halo-width': 1.4,
      },
    },
    {
      // Towns and cities, taking over from the DOM markers at the handover
      // zoom. Sized by class so a city does not read as a hamlet.
      id: 'ofm-place-major',
      type: 'symbol',
      source: s,
      'source-layer': 'place',
      minzoom: PLACE_HANDOVER_ZOOM,
      filter: ['match', ['get', 'class'], ['city', 'town'], true, false],
      layout: {
        'text-field': ['coalesce', ['get', 'name:en'], ['get', 'name']],
        'text-font': ['Noto Sans Regular'],
        'text-size': [
          'match', ['get', 'class'], 'city', 15, 13,
        ] as ExpressionSpecification,
        'text-max-width': 8,
        'text-padding': 6,
      } as LayerSpecification['layout'],
      paint: {
        'text-color': PLACE_LABEL,
        'text-halo-color': LABEL_HALO,
        'text-halo-width': 1.8,
      },
    },
    {
      // Villages, suburbs and neighbourhoods — the ones Natural Earth has
      // never heard of, and the whole reason close-up naming was empty. Held
      // back to z13 so they arrive as the map becomes local rather than
      // crowding the towns.
      id: 'ofm-place-minor',
      type: 'symbol',
      source: s,
      'source-layer': 'place',
      minzoom: 13,
      filter: [
        'match', ['get', 'class'],
        ['village', 'hamlet', 'suburb', 'neighbourhood', 'quarter'], true, false,
      ],
      layout: {
        'text-field': ['coalesce', ['get', 'name:en'], ['get', 'name']],
        'text-font': ['Noto Sans Regular'],
        'text-size': ['interpolate', ['linear'], ['zoom'], 13, 11, 17, 13],
        'text-max-width': 8,
        'text-padding': 4,
      } as LayerSpecification['layout'],
      paint: {
        'text-color': LABEL,
        'text-halo-color': LABEL_HALO,
        'text-halo-width': 1.6,
      },
    },
  ]
}

export const LAND_COLOR = LAND
