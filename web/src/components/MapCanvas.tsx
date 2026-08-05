import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import * as turf from '@turf/turf'

import { useStore } from '../store'
import { rampColor, rampPosition } from '../lib/format'
import {
  GLYPHS,
  VECTOR_SOURCE_ID,
  belowVectorBasemap,
  resolveVectorSource,
  vectorBasemapLayers,
} from '../lib/basemapStyle'

/**
 * The map is the canvas, not a widget in a frame — full bleed, with panels
 * floating over it.
 *
 * The drawing interaction is ported from the original prototype because it was
 * the best part of it: press, drag, release, with a live dashed preview. Only
 * the rendering target changed (Leaflet vector layers -> MapLibre GeoJSON
 * sources). The feel is deliberately identical.
 */

/**
 * The initial style contains no external sources at all — just a background
 * colour.
 *
 * This is deliberate and load-bearing. MapLibre refuses to paint *any* layer
 * while the style is not fully loaded, and a raster source whose tiles never
 * arrive keeps the style unloaded indefinitely. Putting the basemap in the
 * initial style therefore means a slow, blocked or rate-limited tile host
 * blanks the user's own data — which is not a hypothetical: OSM's tile usage
 * policy does not cover production traffic, and they do block.
 *
 * So the style loads instantly with nothing external in it, our data layers go
 * on top, and the basemap is added afterwards as pure decoration. If it never
 * arrives, the map is plain — but the AOI, the cells and every number still
 * render.
 */
// MapLibre computes its worker URL at runtime, which Vite cannot see, so the
// worker is never emitted and the app silently renders an empty map — see
// scripts/copy-maplibre-worker.mjs for the full failure mode. The worker and
// its shared chunk are copied verbatim into public/maplibre/ instead, which
// preserves the relative import between them.
maplibregl.setWorkerUrl('/maplibre/maplibre-gl-worker.mjs')

const BASE_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {},
  // Street names are the one place this app uses a glyph server, and it is a
  // departure from the rule two comments below, so it is worth stating why.
  // Place labels are DOM markers because "Guildford" is one word at one point
  // and a whole font pipeline to draw it is a bad trade. A street name is not:
  // it has to bend along the road it names, which no DOM element can do, and
  // at the zooms where someone is analysing a site rather than finding one it
  // is most of what makes the map legible. Nothing is fetched unless a text
  // layer actually draws, and if the glyph host is down the labels are simply
  // absent — same failure contract as the rest of the basemap.
  glyphs: GLYPHS,
  // Sea. The land polygons of the bundled basemap sit on top of this, which
  // is what gives the map a coastline before a single tile has loaded.
  layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#e6ecee' } }],
}

/**
 * The bundled basemap: coastline, urban areas, water, motorways, railways and
 * towns, generalised from Natural Earth (public domain) and shipped with the
 * app — see scripts/build_basemap.py.
 *
 * It exists because the raster underlay is the one part of this map that is
 * allowed to fail, and when it did the canvas was an empty rectangle: no
 * coast, no towns, no roads, nothing to say whether you were looking at Devon
 * or Durham. Cartography this basic should not depend on a third party being
 * up, and at 1:10 million it is exactly the right detail for the zooms where
 * someone is *finding* a site rather than drawing one.
 *
 * Vector tiles still earn their place at close range, so the two hand over: the
 * bundled layers carry the map to about z11 and fade as the vector layers fade
 * in. See lib/basemapStyle.ts.
 */
const BASEMAP_URL = '/basemap/england.json'

type PlaceFeature = GeoJSON.Feature<GeoJSON.Point, {
  name: string
  pop_max: number | null
  adm1name: string | null
  featurecla: string | null
}>

interface BasemapData {
  attribution: string
  land: GeoJSON.FeatureCollection
  urban: GeoJSON.FeatureCollection
  lakes: GeoJSON.FeatureCollection
  rivers: GeoJSON.FeatureCollection
  roads: GeoJSON.FeatureCollection
  rail: GeoJSON.FeatureCollection
  places: GeoJSON.FeatureCollection
}

/** Which places are worth naming at this zoom.
 *
 *  A map with every town on it at national zoom is unreadable, and one with
 *  only London on it at county zoom is useless. The threshold falls as you
 *  come in, which is how a paper atlas does it too. */
function placeCutoff(zoom: number): number {
  if (zoom < 6) return 700_000
  if (zoom < 7) return 400_000
  if (zoom < 8) return 200_000
  if (zoom < 9) return 90_000
  if (zoom < 10.5) return 40_000
  return 0
}

const EMPTY: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }

/**
 * How much of the map is covered by floating chrome, measured rather than
 * assumed.
 *
 * The map spans the whole window with the report panel and the timeline on
 * top, so a shape fitted to the full viewport centres itself underneath them.
 * The panel is a right-hand column on a desktop and a bottom sheet on a
 * phone — reading its actual rectangle handles both, where reading the
 * `--panel-w` variable handled only the first and left half of every drawn
 * area behind the sheet.
 */
function chromePadding(): { top: number; left: number; right: number; bottom: number } {
  const timeline = parseInt(getComputedStyle(document.documentElement)
    .getPropertyValue('--timeline-h')) || 0
  const panel = document.querySelector('.data-panel')?.getBoundingClientRect()
  const asSheet = !!panel && panel.top > 1
  return {
    top: 80,
    left: asSheet ? 40 : 100,
    right: asSheet ? 40 : (panel?.width ?? 0) + 60,
    bottom: (asSheet ? window.innerHeight - panel.top : timeline) + 40,
  }
}

export default function MapCanvas() {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  // React state rather than a ref: when the style becomes ready the AOI and
  // cell effects must re-run, and flipping a ref would not re-render.
  const [ready, setReady] = useState(false)
  // Place labels are DOM markers rather than a symbol layer: MapLibre needs a
  // glyph server to render text, and standing one up — or depending on
  // someone else's — to write "Guildford" on a map is the wrong trade. As
  // markers they also get the interface's own typeface for free.
  const [places, setPlaces] = useState<PlaceFeature[]>([])
  const placeMarkers = useRef<maplibregl.Marker[]>([])
  // The vector basemap resolves its tile URL over the network, so `install`
  // can run again mid-flight; this makes that idempotent.
  const vectorPending = useRef<Promise<void> | null>(null)
  const userMarkers = useRef<maplibregl.Marker[]>([])

  const drawMode = useStore((s) => s.drawMode)
  const setAoi = useStore((s) => s.setAoi)
  const aoi = useStore((s) => s.aoi)
  const cells = useStore((s) => s.cells)
  const data = useStore((s) => s.data)
  const selected = useStore((s) => s.selected)
  const timeIndex = useStore((s) => s.timeIndex)
  const catalog = useStore((s) => s.catalog)
  const flyTo = useStore((s) => s.flyTo)
  const overlayOpacity = useStore((s) => s.overlayOpacity)
  const setCursor = useStore((s) => s.setCursor)
  const setView = useStore((s) => s.setView)
  const markers = useStore((s) => s.markers)
  const addMarker = useStore((s) => s.addMarker)
  const moveMarker = useStore((s) => s.moveMarker)
  const setDrawMode = useStore((s) => s.setDrawMode)

  // Drawing state lives in refs, not React state: it changes on every
  // mousemove and re-rendering the tree at that rate would drop frames.
  const drawing = useRef(false)
  const startLngLat = useRef<maplibregl.LngLat | null>(null)
  const freePoints = useRef<[number, number][]>([])
  const modeRef = useRef(drawMode)
  modeRef.current = drawMode
  // Set when a change came from nudging an existing shape rather than drawing
  // a new one, so the camera does not refit on every small adjustment.
  const skipFit = useRef(false)

  // ---- init ---------------------------------------------------------------
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: BASE_STYLE,
      center: [-0.57, 51.24],
      zoom: 11,
      attributionControl: false,
      // WebGL clears its drawing buffer after every frame unless told not to,
      // so `canvas.toDataURL()` returns a blank image. The printable report
      // puts the map at the top of the page, and this is what makes that
      // possible. It costs a little GPU memory; nothing else. (MapLibre 5
      // moved this under canvasContextAttributes.)
      canvasContextAttributes: { preserveDrawingBuffer: true },
    })
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right')
    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right')
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: 'metric' }), 'bottom-left')

    // A failing basemap must never stop our own layers being installed. `load`
    // waits on the first tiles, so this hangs off `styledata` — which fires as
    // soon as the (inline) style is parsed — and guards against running twice.
    const install = () => {
      if (!map.style || map.getSource('cells')) return
      map.addSource('cells', { type: 'geojson', data: EMPTY })
      map.addLayer({
        id: 'cells-fill',
        type: 'fill',
        source: 'cells',
        paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.72 },
      })

      map.addSource('aoi', { type: 'geojson', data: EMPTY })
      map.addLayer({
        id: 'aoi-fill',
        type: 'fill',
        source: 'aoi',
        paint: { 'fill-color': '#4d6048', 'fill-opacity': 0.07 },
      })
      map.addLayer({
        id: 'aoi-line',
        type: 'line',
        source: 'aoi',
        paint: { 'line-color': '#4d6048', 'line-width': 2 },
      })

      // Corner handles for resizing. Above the outline so they stay grabbable
      // when the shape is small.
      map.addSource('handles', { type: 'geojson', data: EMPTY })

      map.addSource('draft', { type: 'geojson', data: EMPTY })
      map.addLayer({
        id: 'draft-fill',
        type: 'fill',
        source: 'draft',
        paint: { 'fill-color': '#1f88b4', 'fill-opacity': 0.08 },
      })
      map.addLayer({
        id: 'draft-line',
        type: 'line',
        source: 'draft',
        paint: { 'line-color': '#1f88b4', 'line-width': 2, 'line-dasharray': [2, 1.5] },
      })

      map.addLayer({
        id: 'handles-circle',
        type: 'circle',
        source: 'handles',
        paint: {
          'circle-radius': 6,
          'circle-color': '#ffffff',
          'circle-stroke-width': 2,
          'circle-stroke-color': '#4d6048',
        },
      })

      // The bundled basemap goes underneath everything of ours, and underneath
      // the vector basemap. Anchoring it to the first vector layer rather than
      // to 'cells-fill' is what makes that true regardless of which of the two
      // fetches resolves first — see belowVectorBasemap.
      void fetch(BASEMAP_URL)
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
        .then((b: BasemapData) => {
          if (!map.style || map.getSource('bm-land')) return
          const first = belowVectorBasemap(
            (id) => !!map.getLayer(id),
            map.getLayer('cells-fill') ? 'cells-fill' : undefined,
          )

          const add = (id: string, data: GeoJSON.FeatureCollection,
                       layer: Omit<maplibregl.LayerSpecification, 'id' | 'source'>) => {
            map.addSource(id, {
              type: 'geojson', data,
              ...(id === 'bm-land' ? { attribution: b.attribution } : {}),
            })
            map.addLayer({ id, source: id, ...layer } as maplibregl.LayerSpecification, first)
          }

          // Land on sea, towns on land, water over both, then the network.
          add('bm-land', b.land, {
            type: 'fill',
            paint: { 'fill-color': '#fdfcfa', 'fill-outline-color': '#c9c3b7' },
          })
          add('bm-urban', b.urban, {
            type: 'fill',
            paint: {
              'fill-color': '#ebe7de',
              'fill-opacity': ['interpolate', ['linear'], ['zoom'], 5, 0.9, 11, 0.5, 13, 0],
            },
          })
          add('bm-lakes', b.lakes, {
            type: 'fill',
            paint: { 'fill-color': '#dbe7ec', 'fill-outline-color': '#b7cdd6' },
          })
          add('bm-rivers', b.rivers, {
            type: 'line',
            paint: {
              'line-color': '#b7cdd6',
              'line-width': ['interpolate', ['linear'], ['zoom'], 5, 0.6, 10, 1.6],
              'line-opacity': ['interpolate', ['linear'], ['zoom'], 9, 0.9, 12.5, 0],
            },
          })
          add('bm-rail', b.rail, {
            type: 'line',
            paint: {
              'line-color': '#a9a396', 'line-width': 0.7, 'line-dasharray': [3, 2],
              'line-opacity': ['interpolate', ['linear'], ['zoom'], 7, 0, 8.5, 0.8, 12, 0],
            },
          })
          // Two passes so a road reads as a road: a pale casing under a
          // darker line, which is what stops a network turning into spaghetti.
          add('bm-roads-casing', b.roads, {
            type: 'line',
            layout: { 'line-cap': 'round', 'line-join': 'round' },
            paint: {
              'line-color': '#ffffff',
              'line-width': ['interpolate', ['linear'], ['zoom'],
                             5, ['case', ['==', ['get', 'type'], 'Major Highway'], 2.4, 1.4],
                             11, ['case', ['==', ['get', 'type'], 'Major Highway'], 7, 4]],
              'line-opacity': ['interpolate', ['linear'], ['zoom'], 10.5, 0.9, 12.5, 0],
            },
          })
          add('bm-roads', b.roads, {
            type: 'line',
            layout: { 'line-cap': 'round', 'line-join': 'round' },
            paint: {
              'line-color': ['case', ['==', ['get', 'type'], 'Major Highway'], '#8a9a7e', '#c2bcae'],
              'line-width': ['interpolate', ['linear'], ['zoom'],
                             5, ['case', ['==', ['get', 'type'], 'Major Highway'], 1.1, 0.6],
                             11, ['case', ['==', ['get', 'type'], 'Major Highway'], 4, 2]],
              'line-opacity': ['interpolate', ['linear'], ['zoom'], 10.5, 0.95, 12.5, 0],
            },
          })
          // The coast last, so it sits over the fills it bounds.
          add('bm-coast', b.land, {
            type: 'line',
            paint: {
              'line-color': '#8c9aa0',
              'line-width': ['interpolate', ['linear'], ['zoom'], 5, 0.7, 10, 1.4],
              'line-opacity': ['interpolate', ['linear'], ['zoom'], 11, 0.9, 13, 0],
            },
          })

          setPlaces(b.places.features as PlaceFeature[])
          map.getSource('bm-land') && setReady(true)
        })
        .catch(() => {
          // A missing bundle costs context and nothing else — the same
          // contract the raster has always had.
        })

      // Close-range detail: OSM vector tiles drawn in this app's own palette.
      // See lib/basemapStyle.ts — the short version is that the raster this
      // replaced could only be washed out, never restyled, so zooming in used
      // to abandon the palette exactly when the map became detailed enough to
      // analyse.
      //
      // Added last and beneath 'cells-fill', so it is decoration in the same
      // sense the raster was: if the tile host is unreachable these layers draw
      // nothing and the bundled basemap carries the map alone.
      if (!map.getSource(VECTOR_SOURCE_ID)) {
        // Marked before the await so a second `styledata` during the round trip
        // cannot add the source twice.
        vectorPending.current = vectorPending.current || (async () => {
          const source = await resolveVectorSource()
          if (!map.style || map.getSource(VECTOR_SOURCE_ID)) return
          map.addSource(VECTOR_SOURCE_ID, source)
          const under = map.getLayer('cells-fill') ? 'cells-fill' : undefined
          for (const layer of vectorBasemapLayers()) map.addLayer(layer, under)
        })().catch(() => {
          // Decoration only. The bundled basemap carries the map without it.
        })
      }

      setReady(true)
    }

    map.on('styledata', install)
    map.on('load', install)
    // The style is inline and has no external sources, so it may already be
    // loaded by the time the listeners attach.
    if (map.isStyleLoaded()) install()
    // Tile fetch failures are noisy and not actionable — the data layers are
    // ours and render regardless. Swallow them rather than filling the console.
    map.on('error', (e) => {
      if (!String(e?.error?.message ?? '').includes('Failed to fetch')) console.warn(e?.error)
    })

    // Feed the status bar. A GIS that cannot tell you where the pointer is,
    // how far across the picture is, and in what projection, is a picture of a
    // map rather than a map.
    const report = () => {
      const c = map.getCenter()
      // Metres per pixel at this latitude, times the CSS reference of 96dpi,
      // gives the denominator of a real representative fraction.
      const mPerPx = 156543.03392 * Math.cos((c.lat * Math.PI) / 180) / Math.pow(2, map.getZoom())
      setView({ zoom: map.getZoom(), scale: mPerPx * 96 / 0.0254 })
    }
    const onMouseMove = (e: maplibregl.MapMouseEvent) =>
      setCursor({ lng: e.lngLat.lng, lat: e.lngLat.lat })
    const onMouseOut = () => setCursor(null)
    map.on('move', report)
    map.on('zoom', report)
    map.on('mousemove', onMouseMove)
    map.on('mouseout', onMouseOut)
    report()

    mapRef.current = map
    // Readable from a test driving the camera. One line, and the alternative
    // is scripting scroll-wheel gestures to hit an exact zoom.
    ;(window as unknown as { __map?: maplibregl.Map }).__map = map
    return () => {
      map.off('move', report)
      map.off('zoom', report)
      map.off('mousemove', onMouseMove)
      map.off('mouseout', onMouseOut)
      map.remove(); mapRef.current = null; setReady(false)
    }
  }, [setCursor, setView])

  // ---- drawing ------------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    // Dragging the map and drawing on it are the same gesture, so panning has
    // to yield while a tool is active. On touch that goes further: a one-finger
    // drag must draw rather than pan, and pinch-rotate has to stop hijacking
    // the gesture mid-stroke.
    if (drawMode) {
      map.dragPan.disable()
      map.doubleClickZoom.disable()
      map.touchZoomRotate.disable()
      map.touchPitch.disable()
      map.getCanvas().style.cursor = 'crosshair'
      // Without this the browser scrolls the page under the finger instead of
      // delivering touchmove to us.
      map.getCanvas().style.touchAction = 'none'
    } else {
      map.dragPan.enable()
      map.doubleClickZoom.enable()
      map.touchZoomRotate.enable()
      map.touchPitch.enable()
      map.getCanvas().style.cursor = ''
      map.getCanvas().style.touchAction = ''
    }

    const setDraft = (g: GeoJSON.Polygon | null) => {
      const src = map.getSource('draft') as maplibregl.GeoJSONSource | undefined
      src?.setData(g ? { type: 'Feature', geometry: g, properties: {} } : EMPTY)
    }

    const rectPolygon = (a: maplibregl.LngLat, b: maplibregl.LngLat): GeoJSON.Polygon => ({
      type: 'Polygon',
      coordinates: [[
        [a.lng, a.lat], [b.lng, a.lat], [b.lng, b.lat], [a.lng, b.lat], [a.lng, a.lat],
      ]],
    })

    const circlePolygon = (c: maplibregl.LngLat, edge: maplibregl.LngLat): GeoJSON.Polygon => {
      const km = turf.distance([c.lng, c.lat], [edge.lng, edge.lat], { units: 'kilometers' })
      return turf.circle([c.lng, c.lat], Math.max(km, 0.01), { steps: 64 }).geometry
    }

    // The handlers take a plain LngLat rather than an event, so mouse and
    // touch share one implementation. The prototype supported both and the
    // first React rebuild quietly dropped touch — on a tablet, which is where
    // the whole tactile premise of this tool lives.
    const onDown = (ll: maplibregl.LngLat) => {
      if (!modeRef.current) return
      drawing.current = true
      startLngLat.current = ll
      freePoints.current = [[ll.lng, ll.lat]]
    }

    const onMove = (ll: maplibregl.LngLat) => {
      if (!drawing.current || !modeRef.current || !startLngLat.current) return
      const mode = modeRef.current
      if (mode === 'rect') setDraft(rectPolygon(startLngLat.current, ll))
      else if (mode === 'circle') setDraft(circlePolygon(startLngLat.current, ll))
      else {
        freePoints.current.push([ll.lng, ll.lat])
        if (freePoints.current.length > 2) {
          setDraft({ type: 'Polygon', coordinates: [[...freePoints.current, freePoints.current[0]]] })
        }
      }
    }

    const onUp = (ll: maplibregl.LngLat) => {
      if (!drawing.current || !modeRef.current || !startLngLat.current) return
      const mode = modeRef.current
      drawing.current = false
      setDraft(null)

      let poly: GeoJSON.Polygon | null = null
      if (mode === 'rect') {
        const a = startLngLat.current
        if (Math.abs(a.lng - ll.lng) < 1e-5) return
        poly = rectPolygon(a, ll)
      } else if (mode === 'circle') {
        poly = circlePolygon(startLngLat.current, ll)
      } else {
        if (freePoints.current.length < 4) return
        const ring = [...freePoints.current, freePoints.current[0]]
        const raw: GeoJSON.Feature<GeoJSON.Polygon> = {
          type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [ring] },
        }
        // A two-second scribble is several hundred vertices. Simplifying on
        // release keeps every downstream call fast, and the shape looks the
        // same at the zoom it was drawn at.
        const tol = 0.00004 * Math.pow(2, Math.max(0, 13 - map.getZoom()))
        const simplified = turf.simplify(raw, { tolerance: tol, highQuality: true })
        poly = simplified.geometry

        // Freehand shapes self-intersect constantly. Catching it here produces
        // a message the user can act on; letting it through produces an opaque
        // failure three calls later.
        if (turf.kinks(simplified).features.length > 0) {
          const hull = turf.convex(turf.explode(simplified))
          if (hull) poly = hull.geometry as GeoJSON.Polygon
        }
      }

      startLngLat.current = null
      freePoints.current = []
      if (poly) setAoi(poly)
    }

    const mouseDown = (e: maplibregl.MapMouseEvent) => onDown(e.lngLat)
    const mouseMove = (e: maplibregl.MapMouseEvent) => onMove(e.lngLat)
    const mouseUp = (e: maplibregl.MapMouseEvent) => onUp(e.lngLat)

    // MapTouchEvent.lngLat is the centroid of the active touches, which for a
    // single-finger stroke is exactly the finger. On touchend the touch list
    // is already empty, so the last known position is used instead.
    let lastTouch: maplibregl.LngLat | null = null
    const touchStart = (e: maplibregl.MapTouchEvent) => {
      if (e.points.length > 1) return          // let multi-touch gestures be
      lastTouch = e.lngLat
      onDown(e.lngLat)
    }
    const touchMove = (e: maplibregl.MapTouchEvent) => {
      if (!drawing.current) return
      e.preventDefault()
      lastTouch = e.lngLat
      onMove(e.lngLat)
    }
    const touchEnd = () => { if (lastTouch) onUp(lastTouch) }
    // A stroke interrupted by a system gesture must not leave a half-drawn
    // shape stuck on screen.
    const touchCancel = () => {
      drawing.current = false
      startLngLat.current = null
      freePoints.current = []
      setDraft(null)
    }

    // A stroke released outside the canvas — over the report panel, which
    // covers half the map on a small screen — never reached MapLibre's own
    // mouseup, so the shape was silently discarded and the tool stayed armed.
    // The window sees every release; the last position on the map is where the
    // shape was.
    let lastSeen: maplibregl.LngLat | null = null
    const trackMove = (e: maplibregl.MapMouseEvent) => { lastSeen = e.lngLat }
    const windowUp = () => {
      if (drawing.current && lastSeen) onUp(lastSeen)
    }

    map.on('mousedown', mouseDown)
    map.on('mousemove', mouseMove)
    map.on('mousemove', trackMove)
    map.on('mouseup', mouseUp)
    map.on('touchstart', touchStart)
    map.on('touchmove', touchMove)
    map.on('touchend', touchEnd)
    map.on('touchcancel', touchCancel)
    window.addEventListener('mouseup', windowUp)
    window.addEventListener('touchend', windowUp)
    return () => {
      map.off('mousedown', mouseDown)
      map.off('mousemove', mouseMove)
      map.off('mousemove', trackMove)
      map.off('mouseup', mouseUp)
      map.off('touchstart', touchStart)
      map.off('touchmove', touchMove)
      map.off('touchend', touchEnd)
      map.off('touchcancel', touchCancel)
      window.removeEventListener('mouseup', windowUp)
      window.removeEventListener('touchend', windowUp)
    }
  }, [drawMode, setAoi])

  // ---- move and resize the drawn area -------------------------------------
  /**
   * Drag inside the shape to move it; drag a corner to resize it.
   *
   * Before this the only way to adjust an area was to draw it again, which is
   * cheap for a rectangle and destroys a hand-traced outline. "Almost right,
   * ten metres north" is the most common thing a user wants next, and redrawing
   * is the worst possible answer to it.
   *
   * Only active with no drawing tool selected, so the tools always win the
   * gesture — and the map still pans normally anywhere outside the shape.
   */
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || !aoi || drawMode) return

    const ring = aoi.coordinates[0]
    const lngs = ring.map((p) => p[0])
    const lats = ring.map((p) => p[1])
    const west = Math.min(...lngs), east = Math.max(...lngs)
    const south = Math.min(...lats), north = Math.max(...lats)

    const handleSrc = map.getSource('handles') as maplibregl.GeoJSONSource | undefined
    const aoiSrc = map.getSource('aoi') as maplibregl.GeoJSONSource | undefined
    const corners: [string, number, number][] = [
      ['sw', west, south], ['se', east, south], ['ne', east, north], ['nw', west, north],
    ]
    handleSrc?.setData({
      type: 'FeatureCollection',
      features: corners.map(([id, lng, lat]) => ({
        type: 'Feature',
        properties: { corner: id },
        geometry: { type: 'Point', coordinates: [lng, lat] },
      })),
    })

    let mode: 'move' | 'resize' | null = null
    let anchor: [number, number] = [0, 0]     // the corner held still while resizing
    let start: maplibregl.LngLat | null = null
    let last: maplibregl.LngLat | null = null

    const preview = (g: GeoJSON.Polygon) => {
      aoiSrc?.setData({ type: 'Feature', geometry: g, properties: {} })
      const r = g.coordinates[0]
      const xs = r.map((p) => p[0]), ys = r.map((p) => p[1])
      const w = Math.min(...xs), e = Math.max(...xs), s = Math.min(...ys), n = Math.max(...ys)
      handleSrc?.setData({
        type: 'FeatureCollection',
        features: ([['sw', w, s], ['se', e, s], ['ne', e, n], ['nw', w, n]] as [string, number, number][])
          .map(([id, lng, lat]) => ({
            type: 'Feature', properties: { corner: id },
            geometry: { type: 'Point', coordinates: [lng, lat] },
          })),
      })
    }

    const moved = (ll: maplibregl.LngLat): GeoJSON.Polygon | null => {
      if (!start) return null
      if (mode === 'move') {
        const dx = ll.lng - start.lng
        const dy = ll.lat - start.lat
        return {
          type: 'Polygon',
          coordinates: [ring.map(([x, y]) => [x + dx, y + dy])],
        }
      }
      // Resize scales about the opposite corner. The guard stops a shape being
      // dragged through its own anchor and coming back inside out — and stops
      // a division by nearly zero turning a field into a continent.
      const [ax, ay] = anchor
      const sx = (ll.lng - ax) / ((start.lng - ax) || 1e-9)
      const sy = (ll.lat - ay) / ((start.lat - ay) || 1e-9)
      if (!Number.isFinite(sx) || !Number.isFinite(sy)) return null
      const clamp = (s: number) => Math.max(0.05, Math.min(20, s))
      const cx = clamp(Math.abs(sx)), cy = clamp(Math.abs(sy))
      return {
        type: 'Polygon',
        coordinates: [ring.map(([x, y]) => [ax + (x - ax) * cx, ay + (y - ay) * cy])],
      }
    }

    const hitHandle = (pt: maplibregl.Point) => {
      // A few pixels of slack: a 6px circle is an unfair target on a tablet.
      const box: [maplibregl.PointLike, maplibregl.PointLike] = [
        [pt.x - 10, pt.y - 10], [pt.x + 10, pt.y + 10],
      ]
      return map.queryRenderedFeatures(box, { layers: ['handles-circle'] })[0]
    }

    const onDown = (pt: maplibregl.Point, ll: maplibregl.LngLat): boolean => {
      const handle = hitHandle(pt)
      if (handle) {
        mode = 'resize'
        const corner = handle.properties?.corner as string
        anchor = [
          corner.includes('w') ? east : west,
          corner.includes('s') ? north : south,
        ]
      } else if (map.queryRenderedFeatures(pt, { layers: ['aoi-fill'] }).length) {
        mode = 'move'
      } else {
        return false
      }
      start = ll
      map.dragPan.disable()
      return true
    }

    const onMove = (ll: maplibregl.LngLat) => {
      if (!mode) return
      last = ll
      const g = moved(ll)
      if (g) preview(g)
    }

    const onUp = (ll: maplibregl.LngLat | null) => {
      if (!mode) return
      const g = ll ? moved(ll) : null
      mode = null
      start = null
      map.dragPan.enable()
      // A click with no drag must not spend a query on an identical shape.
      if (g && JSON.stringify(g) !== JSON.stringify(aoi)) {
        // The refit belongs to a newly drawn shape, not to a nudge — flying
        // the camera after every small adjustment makes editing unusable.
        skipFit.current = true
        setAoi(g)
      } else {
        preview(aoi)
      }
    }

    const mouseDown = (e: maplibregl.MapMouseEvent) => {
      if (onDown(e.point, e.lngLat)) e.preventDefault()
    }
    const mouseMove = (e: maplibregl.MapMouseEvent) => {
      if (mode) { onMove(e.lngLat); return }
      // Cursor is the only affordance saying the shape can be grabbed at all.
      const canvas = map.getCanvas()
      if (hitHandle(e.point)) canvas.style.cursor = 'nwse-resize'
      else if (map.queryRenderedFeatures(e.point, { layers: ['aoi-fill'] }).length) canvas.style.cursor = 'move'
      else canvas.style.cursor = ''
    }
    const mouseUp = (e: maplibregl.MapMouseEvent) => onUp(e.lngLat)

    let lastTouch: maplibregl.LngLat | null = null
    const touchStart = (e: maplibregl.MapTouchEvent) => {
      if (e.points.length > 1) return
      lastTouch = e.lngLat
      if (onDown(e.point, e.lngLat)) e.preventDefault()
    }
    const touchMove = (e: maplibregl.MapTouchEvent) => {
      if (!mode) return
      e.preventDefault()
      lastTouch = e.lngLat
      onMove(e.lngLat)
    }
    const touchEnd = () => { if (lastTouch) onUp(lastTouch) }

    // MapLibre's own mouseup stops at the edge of the canvas, and half of this
    // map is under a floating panel — releasing the button there would leave
    // the edit uncommitted and panning switched off. The window sees every
    // release, and the last position on the canvas is where the shape was.
    const windowUp = () => { if (mode) onUp(last ?? start) }

    map.on('mousedown', mouseDown)
    map.on('mousemove', mouseMove)
    map.on('mouseup', mouseUp)
    map.on('touchstart', touchStart)
    map.on('touchmove', touchMove)
    map.on('touchend', touchEnd)
    window.addEventListener('mouseup', windowUp)
    window.addEventListener('touchend', windowUp)
    return () => {
      map.off('mousedown', mouseDown)
      map.off('mousemove', mouseMove)
      map.off('mouseup', mouseUp)
      map.off('touchstart', touchStart)
      map.off('touchmove', touchMove)
      map.off('touchend', touchEnd)
      window.removeEventListener('mouseup', windowUp)
      window.removeEventListener('touchend', windowUp)
      // React runs this cleanup *after* the drawing effect has re-run, so
      // clearing these unconditionally would undo the crosshair and the
      // pan-lock a freshly selected tool had just set.
      if (!modeRef.current) {
        map.getCanvas().style.cursor = ''
        map.dragPan.enable()
      }
      const src = map.getSource('handles') as maplibregl.GeoJSONSource | undefined
      src?.setData(EMPTY)
    }
  }, [aoi, drawMode, ready, setAoi])

  // ---- AOI outline --------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const src = map.getSource('aoi') as maplibregl.GeoJSONSource | undefined
    if (!src) return
    if (!aoi) { src.setData(EMPTY); return }
    src.setData({ type: 'Feature', geometry: aoi, properties: {} })
    if (skipFit.current) { skipFit.current = false; return }
    const [w, s, e, n] = turf.bbox({ type: 'Feature', geometry: aoi, properties: {} }) as
      [number, number, number, number]
    map.fitBounds([[w, s], [e, n]], {
      padding: chromePadding(),
      duration: 600,
      maxZoom: 15,
    })
  }, [aoi, ready])

  // ---- markers ------------------------------------------------------------
  /**
   * Drop a pin with the point tool, then drag it to correct it.
   *
   * Kept out of the drawing effect on purpose: a marker is a note about where
   * something is, not an area to measure, so it must never trigger a query or
   * disturb the drawn shape.
   */
  useEffect(() => {
    const map = mapRef.current
    if (!map || drawMode !== 'point') return
    const onClick = (e: maplibregl.MapMouseEvent) => {
      addMarker(e.lngLat.lng, e.lngLat.lat)
      // One pin per press of the tool, the way every GIS does it — staying
      // armed is how you end up with nine pins and one intention.
      setDrawMode(null)
    }
    map.getCanvas().style.cursor = 'crosshair'
    map.on('click', onClick)
    return () => {
      map.off('click', onClick)
      if (!modeRef.current) map.getCanvas().style.cursor = ''
    }
  }, [drawMode, addMarker, setDrawMode])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    for (const m of userMarkers.current) m.remove()
    userMarkers.current = markers.map((mk) => {
      const el = document.createElement('div')
      el.className = 'map-marker'
      el.innerHTML =
        '<svg viewBox="0 0 24 24" width="26" height="26" aria-hidden>' +
        '<path d="M12 22s7.5-6.4 7.5-12a7.5 7.5 0 1 0-15 0c0 5.6 7.5 12 7.5 12Z"' +
        ' fill="currentColor" stroke="#fff" stroke-width="1.6"/>' +
        '<circle cx="12" cy="10" r="2.6" fill="#fff"/></svg>' +
        '<span class="map-marker-name"></span>'
      el.querySelector('.map-marker-name')!.textContent = mk.name
      el.title = `${mk.name} — ${mk.lat.toFixed(5)}, ${mk.lng.toFixed(5)}`
      const marker = new maplibregl.Marker({ element: el, anchor: 'bottom', draggable: true })
        .setLngLat([mk.lng, mk.lat])
        .addTo(map)
      marker.on('dragend', () => {
        const p = marker.getLngLat()
        moveMarker(mk.id, p.lng, p.lat)
      })
      return marker
    })
    return () => {
      for (const m of userMarkers.current) m.remove()
      userMarkers.current = []
    }
  }, [markers, moveMarker])

  // ---- place labels -------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map || !places.length) return

    const render = () => {
      const cutoff = placeCutoff(map.getZoom())
      const bounds = map.getBounds()
      const wanted = places.filter((f) => {
        const [lng, lat] = f.geometry.coordinates
        return (f.properties.pop_max ?? 0) >= cutoff &&
               lng >= bounds.getWest() && lng <= bounds.getEast() &&
               lat >= bounds.getSouth() && lat <= bounds.getNorth()
      // A cap as well as a cutoff: zoomed into a conurbation, "every place
      // above 40,000" is still forty labels on top of each other.
      }).slice(0, 40)

      for (const m of placeMarkers.current) m.remove()
      placeMarkers.current = wanted.map((f) => {
        const el = document.createElement('div')
        const big = (f.properties.pop_max ?? 0) >= 250_000
        el.className = `map-place${big ? ' is-major' : ''}`
        el.innerHTML = '<span class="map-place-dot"></span>' +
                       `<span class="map-place-name"></span>`
        el.querySelector('.map-place-name')!.textContent = f.properties.name
        return new maplibregl.Marker({ element: el, anchor: 'left' })
          .setLngLat(f.geometry.coordinates as [number, number])
          .addTo(map)
      })
    }

    render()
    map.on('moveend', render)
    map.on('zoomend', render)
    return () => {
      map.off('moveend', render)
      map.off('zoomend', render)
      for (const m of placeMarkers.current) m.remove()
      placeMarkers.current = []
    }
  }, [places])

  // ---- overlay opacity ----------------------------------------------------
  // A layer you cannot fade is a layer you cannot check against the ground
  // beneath it, which is most of what a value overlay is for.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || !map.getLayer('cells-fill')) return
    map.setPaintProperty('cells-fill', 'fill-opacity', overlayOpacity)
    // Readable from a test, so "the slider moved" and "the map changed" can be
    // asserted separately rather than assumed to be the same thing.
    ;(window as unknown as { __cellsOpacity?: number }).__cellsOpacity = overlayOpacity
  }, [overlayOpacity, ready])

  // ---- go to a searched place --------------------------------------------
  // The panels float over the map, so centring on a place would put it behind
  // the report panel. The offset shifts the target into the visible strip of
  // canvas — the same correction the AOI fit makes with its padding.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !flyTo) return
    const pad = chromePadding()
    map.flyTo({
      center: [flyTo.lng, flyTo.lat],
      zoom: flyTo.zoom,
      // Shift the target into the strip of canvas that is actually visible:
      // sideways past the report column, or upwards past the report sheet.
      offset: [(pad.left - pad.right) / 2, (pad.top - pad.bottom) / 2],
      duration: 900,
      essential: true,
    })
  }, [flyTo])

  // ---- cell repaint on time change ---------------------------------------
  // This is the piece that makes scrubbing feel instant: the cell geometry and
  // each cell's offset were fetched once at draw time, so moving the slider is
  // pure client-side arithmetic. No request is made while scrubbing.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const src = map.getSource('cells') as maplibregl.GeoJSONSource | undefined
    if (!src) return

    const primary = selected[0]
    const series = data?.series[primary]
    const factor = catalog?.factors.find((f) => f.id === primary)
    if (!cells.length || !series || !factor || factor.kind === 'categorical') {
      src.setData(EMPTY)
      return
    }

    const point = series.points[timeIndex]
    if (!point || point.value === null || typeof point.value !== 'number') {
      src.setData(EMPTY)
      return
    }

    const lo = factor.lo ?? 0
    const hi = factor.hi ?? 1
    const spread = (hi - lo) * 0.16

    const features: GeoJSON.Feature[] = cells.map((c) => {
      const v = (point.value as number) + c.offset * spread
      return {
        type: 'Feature',
        properties: { color: rampColor(rampPosition(v, factor)) },
        geometry: {
          type: 'Polygon',
          coordinates: [[
            [c.bbox[0], c.bbox[1]], [c.bbox[2], c.bbox[1]],
            [c.bbox[2], c.bbox[3]], [c.bbox[0], c.bbox[3]], [c.bbox[0], c.bbox[1]],
          ]],
        },
      }
    })
    src.setData({ type: 'FeatureCollection', features })
  }, [cells, data, selected, timeIndex, catalog, ready])

  return <div ref={containerRef} className="map-canvas" />
}
