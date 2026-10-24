import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import * as turf from '@turf/turf'

import { useStore } from '../store'
import type { Layer } from '../types'
import { BASEMAPS } from '../lib/basemaps'

/**
 * The map is the canvas, not a widget in a frame — full bleed, with panels
 * floating over it. It shows the red line, the 1 km and 2 km rings, and every
 * feature each publisher returned, styled as on the PDF sheet.
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
 * arrives, the map is plain — but the red line and every finding still render.
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
  layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#0b1220' } }],
}


const EMPTY: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }

// The same red as the PDF, so the screen and the sheet agree.
const RED_LINE = '#e41a1c'
const RINGS_M = [1000, 2000]

/** Broad fills first, then outlines, lines and points, so nothing small is
 *  buried under a Green Belt that covers the whole view. */
function drawOrder(l: Layer): number {
  if (l.geom === 'point') return 3
  if (l.geom === 'line') return 2
  return l.style.fill === 'none' || l.style.hatched ? 1 : 0
}

export default function MapCanvas() {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  // React state rather than a ref: when the style becomes ready the red line
  // and findings effects must re-run, and flipping a ref would not re-render.
  const [ready, setReady] = useState(false)

  const drawMode = useStore((s) => s.drawMode)
  const setAoi = useStore((s) => s.setRedLine)
  const aoi = useStore((s) => s.redLine)
  const sheet = useStore((s) => s.sheet)
  const layers = useStore((s) => s.layers)
  const hidden = useStore((s) => s.hidden)
  const basemap = useStore((s) => s.basemap)

  // Drawing state lives in refs, not React state: it changes on every
  // mousemove and re-rendering the tree at that rate would drop frames.
  const drawing = useRef(false)
  const startLngLat = useRef<maplibregl.LngLat | null>(null)
  const freePoints = useRef<[number, number][]>([])
  const modeRef = useRef(drawMode)
  modeRef.current = drawMode

  // ---- init ---------------------------------------------------------------
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: BASE_STYLE,
      center: [-0.57, 51.24],
      zoom: 11,
      attributionControl: false,
    })
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right')
    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right')
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: 'metric' }), 'bottom-left')

    // A failing basemap must never stop our own layers being installed. `load`
    // waits on the first tiles, so this hangs off `styledata` — which fires as
    // soon as the (inline) style is parsed — and guards against running twice.
    const install = () => {
      if (!map.style || map.getSource('rings')) return
      // Findings layers are inserted below this marker when a sheet arrives,
      // so the rings and the red line always sit on top of them.
      map.addSource('rings', { type: 'geojson', data: EMPTY })
      map.addLayer({
        id: 'rings',
        type: 'line',
        source: 'rings',
        paint: { 'line-color': '#e9e5dc', 'line-width': 1, 'line-opacity': 0.55, 'line-dasharray': [3, 3] },
      })
      map.addLayer({
        id: 'rings-label',
        type: 'symbol',
        source: 'rings',
        layout: { 'symbol-placement': 'line', 'text-field': ['get', 'label'], 'text-size': 10 },
        paint: { 'text-color': '#e9e5dc', 'text-halo-color': '#121822', 'text-halo-width': 1.2 },
      })

      map.addSource('aoi', { type: 'geojson', data: EMPTY })
      map.addLayer({
        id: 'aoi-fill',
        type: 'fill',
        source: 'aoi',
        paint: { 'fill-color': RED_LINE, 'fill-opacity': 0.06 },
      })
      map.addLayer({
        id: 'aoi-line',
        type: 'line',
        source: 'aoi',
        paint: { 'line-color': RED_LINE, 'line-width': 2.5 },
      })

      map.addSource('draft', { type: 'geojson', data: EMPTY })
      map.addLayer({
        id: 'draft-fill',
        type: 'fill',
        source: 'draft',
        paint: { 'fill-color': RED_LINE, 'fill-opacity': 0.1 },
      })
      map.addLayer({
        id: 'draft-line',
        type: 'line',
        source: 'draft',
        paint: { 'line-color': RED_LINE, 'line-width': 2, 'line-dasharray': [2, 1.5] },
      })

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

    mapRef.current = map
    return () => { map.remove(); mapRef.current = null; setReady(false) }
  }, [])

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

    map.on('mousedown', mouseDown)
    map.on('mousemove', mouseMove)
    map.on('mouseup', mouseUp)
    map.on('touchstart', touchStart)
    map.on('touchmove', touchMove)
    map.on('touchend', touchEnd)
    map.on('touchcancel', touchCancel)
    return () => {
      map.off('mousedown', mouseDown)
      map.off('mousemove', mouseMove)
      map.off('mouseup', mouseUp)
      map.off('touchstart', touchStart)
      map.off('touchmove', touchMove)
      map.off('touchend', touchEnd)
      map.off('touchcancel', touchCancel)
    }
  }, [drawMode, setAoi])

  // ---- AOI outline --------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const src = map.getSource('aoi') as maplibregl.GeoJSONSource | undefined
    if (!src) return
    const rings = map.getSource('rings') as maplibregl.GeoJSONSource | undefined
    if (!aoi) { src.setData(EMPTY); rings?.setData(EMPTY); return }
    src.setData({ type: 'Feature', geometry: aoi, properties: {} })
    const site: GeoJSON.Feature<GeoJSON.Polygon> = { type: 'Feature', geometry: aoi, properties: {} }
    rings?.setData({
      type: 'FeatureCollection',
      features: RINGS_M.flatMap((m) => {
        const b = turf.buffer(site, m, { units: 'meters' })
        return b ? [{ ...b, properties: { label: `${m / 1000} km` } }] : []
      }),
    })
    // Frame the 1 km ring, as the PDF does, so the nearest findings are in view.
    const frame = turf.buffer(site, RINGS_M[0], { units: 'meters' }) ?? site
    const [w, s, e, n] = turf.bbox(frame) as [number, number, number, number]
    // The map spans the full window, but the findings panel sits on top of it. Without asymmetric padding the drawn shape centres itself
    // underneath the panel, which is exactly where the user cannot see it.
    const css = getComputedStyle(document.documentElement)
    const panel = parseInt(css.getPropertyValue('--panel-w')) || 0
    const timeline = parseInt(css.getPropertyValue('--timeline-h')) || 0
    map.fitBounds([[w, s], [e, n]], {
      padding: { top: 80, left: 100, right: panel + 60, bottom: timeline + 40 },
      duration: 600,
      maxZoom: 15,
    })
  }, [aoi, ready])

  // ---- basemap ------------------------------------------------------------
  // Added after our own layers and slotted beneath all of them, so a slow or
  // blocked tile host costs context and nothing else.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const style = map.getStyle()
    for (const l of style.layers ?? []) if (l.id.startsWith('base-')) map.removeLayer(l.id)
    for (const id of Object.keys(style.sources ?? {})) if (id.startsWith('base-')) map.removeSource(id)
    const bm = BASEMAPS.find((b) => b.id === basemap) ?? BASEMAPS[0]
    // Beneath the first layer of ours, whatever it is (findings come and go).
    const below = (map.getStyle().layers ?? []).find((l) => l.id !== 'bg')?.id
    bm.tiles.forEach((url, i) => {
      const id = `base-${bm.id}-${i}`
      map.addSource(id, {
        type: 'raster', tiles: [url], tileSize: 256, maxzoom: bm.maxzoom,
        // One credit per basemap, not one per stacked layer.
        attribution: i === 0 ? bm.attribution : undefined,
      })
      map.addLayer({
        id, type: 'raster', source: id,
        paint: bm.dim ? { 'raster-opacity': 0.5, 'raster-saturation': -0.7 } : {},
      }, below)
    })
  }, [basemap, ready])

  // ---- what each publisher returned -------------------------------------
  // Rebuilt whenever a sheet arrives or goes. Layers that returned nothing
  // have no source at all, which is the honest picture of "none found".
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const style = map.getStyle()
    for (const l of style.layers ?? []) if (l.id.startsWith('res-')) map.removeLayer(l.id)
    for (const id of Object.keys(style.sources ?? {})) if (id.startsWith('res-')) map.removeSource(id)
    if (!sheet) return

    const shown = layers.filter((l) => sheet.map[l.id]).sort((a, b) => drawOrder(a) - drawOrder(b))
    for (const l of shown) {
      const src = `res-${l.id}`
      map.addSource(src, { type: 'geojson', data: sheet.map[l.id] })
      const { fill, edge, alpha, hatched } = l.style
      if (l.geom === 'point') {
        map.addLayer({
          id: `${src}-pt`, type: 'circle', source: src,
          paint: { 'circle-radius': 4.5, 'circle-color': fill === 'none' ? edge : fill,
                   'circle-stroke-color': edge, 'circle-stroke-width': 1 },
        }, 'rings')
        continue
      }
      if (l.geom === 'polygon' && (fill !== 'none' || hatched)) {
        // MapLibre has no hatching; a hatched layer shows as a faint wash of
        // its edge colour instead, and the PDF keeps the real pattern.
        map.addLayer({
          id: `${src}-fill`, type: 'fill', source: src,
          paint: { 'fill-color': fill === 'none' || hatched ? edge : fill,
                   'fill-opacity': hatched ? 0.14 : Math.max(alpha, 0.25) },
        }, 'rings')
      }
      map.addLayer({
        id: `${src}-line`, type: 'line', source: src,
        paint: { 'line-color': edge, 'line-width': l.geom === 'line' ? 2.5 : 1.3 },
      }, 'rings')
    }
  }, [sheet, layers, ready])

  // ---- show / hide from the panel ----------------------------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || !sheet) return
    for (const l of map.getStyle().layers ?? []) {
      if (!l.id.startsWith('res-')) continue
      const id = l.id.slice(4).replace(/-(fill|line|pt)$/, '')
      map.setLayoutProperty(l.id, 'visibility', hidden.includes(id) ? 'none' : 'visible')
    }
  }, [hidden, sheet, ready])

  // ---- click a feature for its name --------------------------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const byId = new Map(layers.map((l) => [l.id, l]))
    let popup: maplibregl.Popup | null = null
    const onClick = (e: maplibregl.MapMouseEvent) => {
      if (modeRef.current) return
      const hits = map.queryRenderedFeatures(e.point)
        .filter((f) => f.layer.id.startsWith('res-'))
      popup?.remove()
      if (!hits.length) return
      const seen = new Set<string>()
      const rows: string[] = []
      for (const f of hits) {
        const id = f.layer.id.slice(4).replace(/-(fill|line|pt)$/, '')
        const label = String(f.properties?.label || 'Unnamed')
        const key = `${id}|${label}`
        if (seen.has(key)) continue
        seen.add(key)
        rows.push(`<b>${esc(byId.get(id)?.name ?? id)}</b><br>${esc(label)}`)
      }
      popup = new maplibregl.Popup({ closeButton: false, maxWidth: '260px' })
        .setLngLat(e.lngLat).setHTML(rows.join('<hr>')).addTo(map)
    }
    map.on('click', onClick)
    return () => { map.off('click', onClick); popup?.remove() }
  }, [layers, ready])

  return <div ref={containerRef} className="map-canvas" />
}

function esc(s: string): string {
  return s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!)
}
