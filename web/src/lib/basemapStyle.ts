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

export const VECTOR_SOURCE: VectorSourceSpecification = {
  type: 'vector',
  url: 'https://tiles.openfreemap.org/planet',
  // ODbL requires the OSM credit; OpenFreeMap asks for its own. This project
  // carries the notice every licence actually requires rather than just naming
  // the licence, so both appear.
  attribution:
    '<a href="https://openfreemap.org" target="_blank" rel="noreferrer">OpenFreeMap</a> ' +
    '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a>',
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

const LAND = '#fdfcfa'
const URBAN = '#ebe7de'
const GREEN = '#e4ebdf'
const WATER = '#dbe7ec'
const WATER_LINE = '#b7cdd6'
const BUILDING = '#e8e3d9'
const BUILDING_LINE = '#d8d1c4'
const ROAD_CASING = '#ffffff'
const ROAD_MAJOR = '#8a9a7e'
const ROAD_MINOR = '#c2bcae'
const RAIL = '#a9a396'
const LABEL = '#6b6559'
const LABEL_HALO = '#fdfcfa'

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
  ]
}

export const LAND_COLOR = LAND
