import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import * as turf from '@turf/turf'
import { useStore } from '../store'
import { rampColor, rampPosition } from '../lib/format'

/**
 * The map is the canvas, not a widget in a frame — full bleed, with panels
 * floating over it.
 *
 * The drawing interaction is ported from the original prototype because it was
 * the best part of it: press, drag, release, with a live dashed preview. Only
 * the rendering target changed (Leaflet vector layers -> MapLibre GeoJSON
 * sources). The feel is deliberately identical.
 */

const OSM_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      attribution: '© OpenStreetMap contributors',
    },
  },
  layers: [
    { id: 'bg', type: 'background', paint: { 'background-color': '#12161a' } },
    {
      id: 'osm',
      type: 'raster',
      source: 'osm',
      // Desaturated and dimmed so data layers read as the foreground. The
      // basemap is context, not content.
      paint: { 'raster-opacity': 0.5, 'raster-saturation': -0.7, 'raster-brightness-max': 0.85 },
    },
  ],
}

const EMPTY: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }

export default function MapCanvas() {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  // React state rather than a ref: when the style becomes ready the AOI and
  // cell effects must re-run, and flipping a ref would not re-render.
  const [ready, setReady] = useState(false)

  const drawMode = useStore((s) => s.drawMode)
  const setAoi = useStore((s) => s.setAoi)
  const aoi = useStore((s) => s.aoi)
  const cells = useStore((s) => s.cells)
  const data = useStore((s) => s.data)
  const selected = useStore((s) => s.selected)
  const timeIndex = useStore((s) => s.timeIndex)
  const catalog = useStore((s) => s.catalog)

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
      style: OSM_STYLE,
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
        paint: { 'fill-color': '#DDAE5C', 'fill-opacity': 0.06 },
      })
      map.addLayer({
        id: 'aoi-line',
        type: 'line',
        source: 'aoi',
        paint: { 'line-color': '#DDAE5C', 'line-width': 2.5 },
      })

      map.addSource('draft', { type: 'geojson', data: EMPTY })
      map.addLayer({
        id: 'draft-fill',
        type: 'fill',
        source: 'draft',
        paint: { 'fill-color': '#C4923F', 'fill-opacity': 0.1 },
      })
      map.addLayer({
        id: 'draft-line',
        type: 'line',
        source: 'draft',
        paint: { 'line-color': '#C4923F', 'line-width': 2, 'line-dasharray': [2, 1.5] },
      })

      setReady(true)
    }

    map.on('styledata', install)
    map.on('load', install)
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
    // to yield while a tool is active.
    if (drawMode) {
      map.dragPan.disable()
      map.doubleClickZoom.disable()
      map.getCanvas().style.cursor = 'crosshair'
    } else {
      map.dragPan.enable()
      map.doubleClickZoom.enable()
      map.getCanvas().style.cursor = ''
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

    const onDown = (e: maplibregl.MapMouseEvent) => {
      if (!modeRef.current) return
      drawing.current = true
      startLngLat.current = e.lngLat
      freePoints.current = [[e.lngLat.lng, e.lngLat.lat]]
    }

    const onMove = (e: maplibregl.MapMouseEvent) => {
      if (!drawing.current || !modeRef.current || !startLngLat.current) return
      const mode = modeRef.current
      if (mode === 'rect') setDraft(rectPolygon(startLngLat.current, e.lngLat))
      else if (mode === 'circle') setDraft(circlePolygon(startLngLat.current, e.lngLat))
      else {
        freePoints.current.push([e.lngLat.lng, e.lngLat.lat])
        if (freePoints.current.length > 2) {
          setDraft({ type: 'Polygon', coordinates: [[...freePoints.current, freePoints.current[0]]] })
        }
      }
    }

    const onUp = (e: maplibregl.MapMouseEvent) => {
      if (!drawing.current || !modeRef.current || !startLngLat.current) return
      const mode = modeRef.current
      drawing.current = false
      setDraft(null)

      let poly: GeoJSON.Polygon | null = null
      if (mode === 'rect') {
        const a = startLngLat.current
        if (Math.abs(a.lng - e.lngLat.lng) < 1e-5) return
        poly = rectPolygon(a, e.lngLat)
      } else if (mode === 'circle') {
        poly = circlePolygon(startLngLat.current, e.lngLat)
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

    map.on('mousedown', onDown)
    map.on('mousemove', onMove)
    map.on('mouseup', onUp)
    return () => {
      map.off('mousedown', onDown)
      map.off('mousemove', onMove)
      map.off('mouseup', onUp)
    }
  }, [drawMode, setAoi])

  // ---- AOI outline --------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const src = map.getSource('aoi') as maplibregl.GeoJSONSource | undefined
    if (!src) return
    if (!aoi) { src.setData(EMPTY); return }
    src.setData({ type: 'Feature', geometry: aoi, properties: {} })
    const [w, s, e, n] = turf.bbox({ type: 'Feature', geometry: aoi, properties: {} }) as
      [number, number, number, number]
    // The map spans the full window, but the data panel and timeline sit on top
    // of it. Without asymmetric padding the drawn shape centres itself
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
