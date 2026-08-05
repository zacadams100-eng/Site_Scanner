/**
 * The map, as a picture, for the printed report.
 *
 * A site report without a map of the site is a spreadsheet. This grabs the
 * live MapLibre canvas — the same view the user has arranged, at the zoom and
 * position they chose, with their drawn boundary and markers on it — and
 * returns it as a data URL the print window can embed.
 *
 * Two things make it work, and both are easy to get wrong:
 *
 * **`preserveDrawingBuffer: true` on the map.** WebGL clears its drawing
 * buffer after every frame unless told otherwise, so `toDataURL()` on a
 * default MapLibre canvas returns a transparent image. It is set where the map
 * is created, and this function is the only reason it is.
 *
 * **The DOM overlays are not in the canvas.** Place labels, the drawn AOI's
 * handles and user markers are HTML elements positioned over the map, not
 * WebGL geometry — MapLibre needs a glyph server for text, which this project
 * deliberately does not run. So the boundary and the markers are drawn onto
 * the captured image afterwards, from their real coordinates, using the map's
 * own projection. Anything drawn here lands exactly where it sits on screen.
 */

import type { Map as MapLibreMap } from 'maplibre-gl'
import type { Marker } from '../types'

export interface MapShot {
  dataUrl: string
  width: number
  height: number
}

/** Brand colours, repeated rather than imported: this output leaves the app. */
const MOSS = '#4d6048'
const MOSS_FILL = 'rgba(77, 96, 72, 0.18)'
const BLUE = '#2fa8d8'
const PAPER = '#f8f6f2'

/**
 * Capture the map as it stands.
 *
 * Returns null rather than throwing when there is no map or the capture comes
 * back blank — a report without its picture is still a useful report, and a
 * failed screenshot must not cost the user the document.
 */
export function captureMap(
  map: MapLibreMap | undefined | null,
  aoi: GeoJSON.Polygon | null,
  markers: Marker[] = [],
  maxWidth = 1400,
): MapShot | null {
  if (!map) return null

  let source: HTMLCanvasElement
  try {
    source = map.getCanvas()
  } catch {
    return null
  }
  if (!source.width || !source.height) return null

  // Crop to the site rather than printing the whole viewport.
  //
  // A browser window is tall and the drawn area is usually a small square in
  // the middle of it, so an uncropped capture wastes most of a page on empty
  // countryside and leaves the subject the size of a stamp. This takes a
  // landscape band around the boundary, with enough margin to show what it
  // sits next to.
  const crop = cropToAoi(map, aoi, source.width, source.height)

  const scale = Math.min(1, maxWidth / crop.w)
  const width = Math.round(crop.w * scale)
  const height = Math.round(crop.h * scale)

  const out = document.createElement('canvas')
  out.width = width
  out.height = height
  const ctx = out.getContext('2d')
  if (!ctx) return null

  // Paper underneath: the basemap has transparent areas, and transparent
  // becomes black in most PDF renderers.
  ctx.fillStyle = PAPER
  ctx.fillRect(0, 0, width, height)
  try {
    ctx.drawImage(source, crop.x, crop.y, crop.w, crop.h, 0, 0, width, height)
  } catch {
    return null
  }

  // Screen coordinates are relative to the whole canvas; the image is a
  // window onto part of it, so everything drawn on top has to be shifted by
  // the crop's origin as well as scaled.
  const dpr = source.width / map.getCanvas().clientWidth || 1
  const project = (lng: number, lat: number) => {
    const p = map.project([lng, lat])
    return { x: (p.x * dpr - crop.x) * scale, y: (p.y * dpr - crop.y) * scale }
  }

  if (aoi?.coordinates?.[0]?.length) {
    ctx.beginPath()
    aoi.coordinates[0].forEach(([lng, lat], i) => {
      const { x, y } = project(lng, lat)
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    ctx.closePath()
    ctx.fillStyle = MOSS_FILL
    ctx.fill()
    ctx.strokeStyle = MOSS
    ctx.lineWidth = 2 * scale * 1.5
    ctx.stroke()
  }

  for (const marker of markers) {
    const { x, y } = project(marker.lng, marker.lat)
    ctx.beginPath()
    ctx.arc(x, y, 6, 0, Math.PI * 2)
    ctx.fillStyle = BLUE
    ctx.fill()
    ctx.strokeStyle = '#fff'
    ctx.lineWidth = 2
    ctx.stroke()

    if (marker.name) {
      ctx.font = '600 12px "IBM Plex Sans", system-ui, sans-serif'
      const w = ctx.measureText(marker.name).width
      // A pill behind the text, because a label on aerial imagery is otherwise
      // unreadable half the time.
      ctx.fillStyle = 'rgba(255,255,255,0.88)'
      ctx.fillRect(x + 9, y - 9, w + 8, 17)
      ctx.fillStyle = '#232323'
      ctx.fillText(marker.name, x + 13, y + 3.5)
    }
  }

  let dataUrl: string
  try {
    dataUrl = out.toDataURL('image/png')
  } catch {
    return null                       // tainted canvas, e.g. a CORS-less tile
  }
  // A blank capture is the failure `preserveDrawingBuffer` exists to prevent.
  // Better to omit the picture than to print an empty grey box.
  if (dataUrl.length < 1000) return null
  return { dataUrl, width, height }
}


/** Aspect ratio of the printed map. Landscape, so it sits on a page the way a
 *  figure should rather than pushing everything below the fold. */
const CROP_RATIO = 3 / 2
/** How much country to show around the site, as a fraction of its own size. */
const CROP_PADDING = 1.6

/**
 * The rectangle of canvas to print: the boundary plus margin, in 3:2.
 *
 * Falls back to a centred band of the viewport when there is no AOI, and never
 * returns a rectangle outside the canvas — an out-of-bounds source rectangle
 * makes `drawImage` silently produce transparent edges.
 */
export function cropToAoi(map: MapLibreMap, aoi: GeoJSON.Polygon | null,
                   canvasW: number, canvasH: number) {
  const full = { x: 0, y: 0, w: canvasW, h: canvasH }
  const ring = aoi?.coordinates?.[0]
  const dpr = canvasW / map.getCanvas().clientWidth || 1

  let cx = canvasW / 2
  let cy = canvasH / 2
  let want = Math.min(canvasW, canvasH)

  if (ring?.length) {
    const pts = ring.map(([lng, lat]) => map.project([lng, lat]))
    const xs = pts.map((p) => p.x * dpr)
    const ys = pts.map((p) => p.y * dpr)
    const minX = Math.min(...xs), maxX = Math.max(...xs)
    const minY = Math.min(...ys), maxY = Math.max(...ys)
    cx = (minX + maxX) / 2
    cy = (minY + maxY) / 2
    // A very small site still needs a sensible amount of context around it,
    // and a very large one must not demand more canvas than exists.
    want = Math.max(maxX - minX, maxY - minY) * (1 + CROP_PADDING)
    want = Math.max(want, Math.min(canvasW, canvasH) * 0.35)
  }

  let w = Math.min(canvasW, want * CROP_RATIO)
  let h = w / CROP_RATIO
  if (h > canvasH) {
    h = canvasH
    w = Math.min(canvasW, h * CROP_RATIO)
  }
  if (w <= 0 || h <= 0) return full

  return {
    x: Math.round(Math.max(0, Math.min(canvasW - w, cx - w / 2))),
    y: Math.round(Math.max(0, Math.min(canvasH - h, cy - h / 2))),
    w: Math.round(w),
    h: Math.round(h),
  }
}
