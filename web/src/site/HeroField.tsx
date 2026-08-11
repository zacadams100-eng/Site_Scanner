import { useEffect, useRef, useState } from 'react'
import {
  buildField, contourLevels, formatCoord, marchingSquares, pickLabels, project,
  type FieldLabel, type PlaceFeature,
} from '../lib/heroField'

/**
 * The homepage hero: a field sheet being surveyed.
 *
 * ## What this is, and what it is not
 *
 * It is the real coastline of England and Wales, its real rivers, and real
 * places at their real coordinates, drawn as a topographic sheet and read by
 * an instrument over fifteen seconds. The contour lines are cartographic
 * texture rather than terrain — there is no elevation data behind them, so the
 * sheet never prints a height, and the readout says FIELD SHEET rather than
 * quoting a measurement it does not have. A hero that invents numbers would
 * contradict the product standing behind it.
 *
 * It is not a photograph. There is no photographic plate in this repository,
 * and one invented for the purpose would be the "AI nature" the brief rules
 * out. `plate` accepts a real aerial image if one is ever commissioned: it
 * renders beneath the cartography and the sheet composes over it unchanged.
 *
 * ## Why there is no animation loop in JavaScript
 *
 * Everything static is drawn once into a canvas at mount — coastline, rivers,
 * lakes, contours, graticule — and then never touched. All motion is CSS on
 * composited layers, so the running cost of the hero is a transform the
 * compositor was going to do anyway. There is no rAF, no per-frame work, and
 * nothing to throttle when the tab is backgrounded.
 *
 * ## Restraint
 *
 * The sheet is bone, khaki and faded blue. Signal orange appears twice: the
 * scan sweep, and the SCAN COMPLETE mark. The collage interventions arrive for
 * about three seconds in the middle of the loop and leave. Everything here
 * sits behind live text, so it is muted on purpose — a hero that competes with
 * the headline is a hero nobody reads past.
 */

interface Sheet {
  view: { minLon: number; minLat: number; maxLon: number; maxLat: number }
  coast: [number, number][][]
  rivers: [number, number][][]
  lakes: [number, number][][]
  places: PlaceFeature[]
}

/** Drawn once at this size and scaled by CSS. Large enough that the slow drift
 *  never reveals a soft edge, small enough to rasterise in a few milliseconds. */
const W = 1400
const H = 900

const COLORS = {
  sea: '#cfdcdf',
  land: '#ebe6d5',
  landEdge: '#5f6357',
  contour: '#9ba08a',
  contourIndex: '#6f7660',
  water: '#7fa3ab',
  grid: '#b9b3a0',
}

function drawSheet(ctx: CanvasRenderingContext2D, sheet: Sheet, detail: 'full' | 'lite') {
  const p = project(sheet.view, W, H, 24)
  ctx.clearRect(0, 0, W, H)

  ctx.fillStyle = COLORS.sea
  ctx.fillRect(0, 0, W, H)

  const trace = (ring: [number, number][]) => {
    ctx.beginPath()
    ring.forEach(([lon, lat], i) => {
      const [x, y] = p(lon, lat)
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
  }

  // Land, filled then edged. The fill is what stops this reading as a wireframe.
  ctx.fillStyle = COLORS.land
  for (const ring of sheet.coast) { trace(ring); ctx.fill() }

  /*
   * Contours, clipped to land.
   *
   * Clipping matters more than it looks: contours running out across the sea
   * is the single detail that makes a generated map look generated. Real
   * survey sheets stop at the coast.
   */
  ctx.save()
  ctx.beginPath()
  for (const ring of sheet.coast) {
    ring.forEach(([lon, lat], i) => {
      const [x, y] = p(lon, lat)
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
  }
  ctx.clip()

  const field = buildField(detail === 'full' ? 220 : 110, detail === 'full' ? 140 : 70, 7)
  const levels = contourLevels(detail === 'full' ? 11 : 6)
  const sx = W / (field.w - 1)
  const sy = H / (field.h - 1)
  levels.forEach((level, i) => {
    // Every fourth line heavier, the way an index contour is drawn on a real
    // sheet. It is the difference between contours and hatching.
    const index = i % 4 === 0
    ctx.strokeStyle = index ? COLORS.contourIndex : COLORS.contour
    ctx.lineWidth = index ? 1.1 : 0.6
    ctx.globalAlpha = index ? 0.85 : 0.6
    ctx.beginPath()
    for (const [x1, y1, x2, y2] of marchingSquares(field, level)) {
      ctx.moveTo(x1 * sx, y1 * sy)
      ctx.lineTo(x2 * sx, y2 * sy)
    }
    ctx.stroke()
  })
  ctx.restore()
  ctx.globalAlpha = 1

  // Water over contours: rivers are surface, contours are ground.
  ctx.strokeStyle = COLORS.water
  ctx.lineWidth = 1.1
  ctx.lineJoin = 'round'
  for (const line of sheet.rivers) { trace(line); ctx.stroke() }
  ctx.fillStyle = COLORS.water
  for (const ring of sheet.lakes) { trace(ring); ctx.fill() }

  ctx.strokeStyle = COLORS.landEdge
  ctx.lineWidth = 1.2
  ctx.globalAlpha = 0.85
  for (const ring of sheet.coast) { trace(ring); ctx.stroke() }
  ctx.globalAlpha = 1
}

/** The graticule, drawn as a separate canvas so it can fade independently of
 *  the sheet it sits on. */
function drawGrid(ctx: CanvasRenderingContext2D, sheet: Sheet) {
  const p = project(sheet.view, W, H, 24)
  ctx.clearRect(0, 0, W, H)
  ctx.strokeStyle = COLORS.grid
  ctx.lineWidth = 0.8
  ctx.setLineDash([2, 5])
  const { minLon, maxLon, minLat, maxLat } = sheet.view
  for (let lon = Math.ceil(minLon); lon <= maxLon; lon++) {
    const [x] = p(lon, minLat)
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke()
  }
  for (let lat = Math.ceil(minLat); lat <= maxLat; lat++) {
    const [, y] = p(minLon, lat)
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke()
  }
  ctx.setLineDash([])
}

export default function HeroField({ plate }: { plate?: string }) {
  const sheetRef = useRef<HTMLCanvasElement>(null)
  const gridRef = useRef<HTMLCanvasElement>(null)
  const [labels, setLabels] = useState<(FieldLabel & { x: number; y: number })[]>([])
  const [ready, setReady] = useState(false)

  useEffect(() => {
    // Fetched whatever the motion preference is. A visitor who has asked for
    // stillness still gets the sheet — it simply does not move, and that one
    // composed frame is their entire hero, so withholding it would leave them
    // with an empty band where everyone else sees the product's subject.
    const lite = window.matchMedia('(max-width: 760px)').matches
    let cancelled = false

    const load = async () => {
      try {
        const res = await fetch('/hero/field.json')
        if (!res.ok) return
        const sheet: Sheet = await res.json()
        if (cancelled) return

        const sheetCtx = sheetRef.current?.getContext('2d')
        const gridCtx = gridRef.current?.getContext('2d')
        if (!sheetCtx || !gridCtx) return
        // Full detail even when motion is off: the reduced-detail sheet exists to
        // keep a phone's compositor light, and a still frame has no compositor
        // cost at all. For these visitors this one frame is the entire hero, so
        // it gets every contour.
        drawSheet(sheetCtx, sheet, lite ? 'lite' : 'full')
        drawGrid(gridCtx, sheet)

        const p = project(sheet.view, W, H, 24)
        /*
         * Placed, then filtered to the half of the frame the headline does not
         * occupy. The first version labelled Leeds and Liverpool underneath the
         * word COMMISSION — legible as neither. The text column owns the left;
         * the instrument owns the right, and the split is what makes the two
         * read as one composition rather than as a background with writing on
         * it.
         */
        /*
         * Two keep-out regions, because the text is not one rectangle. The
         * lede and the buttons sit in a narrow left column, but the headline
         * runs much wider — so filtering on x alone put "Kingston upon Hull"
         * directly underneath the word COMMISSION. The headline band is
         * excluded across most of the frame; below it, only the column is.
         */
        const clear = (x: number, y: number) => {
          // On a phone the copy runs the full width and height of the hero,
          // so there is no clear region to place a label in. Simplified rather
          // than shrunk: the sheet keeps its coastline and contours and drops
          // the labelling, which at 9px behind body text was noise anyway.
          if (lite) return false
          const inHeadlineBand = y > 0.10 && y < 0.44 && x < 0.76
          const inTextColumn = x < 0.46
          return !inHeadlineBand && !inTextColumn
        }
        /*
         * Thinned in screen space, not in degrees.
         *
         * Degrees are the wrong unit for "do these two labels collide": London
         * and Southend are 0.84° apart and landed on top of each other, while
         * two towns the same distance apart north to south did not. A label is
         * a wide, short box, so the test is an ellipse matching its shape.
         */
        const candidates = pickLabels(sheet.places, 60, 0)
          .map((l) => {
            const [x, y] = p(l.lon, l.lat)
            return { ...l, x: x / W, y: y / H }
          })
          .filter((l) => l.x < 0.97 && l.y > 0.06 && l.y < 0.94 && clear(l.x, l.y))

        const picked: typeof candidates = []
        for (const l of candidates) {
          if (picked.length >= (lite ? 4 : 7)) break
          const collides = picked.some((k) =>
            ((k.x - l.x) / 0.15) ** 2 + ((k.y - l.y) / 0.055) ** 2 < 1)
          if (!collides) picked.push(l)
        }
        setLabels(picked.map((l, i) => ({
          ...l, order: i, x: l.x * 100, y: l.y * 100,
        })))
        setReady(true)
      } catch {
        // A hero that fails to load is a hero that is simply not there. The
        // headline and the call to action never depended on it.
      }
    }

    // After first paint, so the sheet never competes with the text for the
    // bandwidth that makes the page usable.
    const idle = (window as { requestIdleCallback?: (cb: () => void) => number })
      .requestIdleCallback
    const handle = idle ? idle(load) : window.setTimeout(load, 400)
    return () => {
      cancelled = true
      if (!idle) window.clearTimeout(handle)
    }
  }, [])

  return (
    <div className={`hf${ready ? ' is-ready' : ''}`} aria-hidden="true">
      {/* A real aerial plate, if one is ever commissioned. Everything above
          composes over it unchanged. */}
      {plate && <div className="hf-plate" style={{ backgroundImage: `url(${plate})` }} />}

      <div className="hf-drift">
        <canvas className="hf-sheet" ref={sheetRef} width={W} height={H} />
        <canvas className="hf-grid" ref={gridRef} width={W} height={H} />

        {/* Places, arriving in order of size. Each carries the coordinate it
            is actually at — the same mono face the application sets every
            measurement in. */}
        <div className="hf-marks">
          {labels.map((l) => (
            <div key={l.name} className="hf-mark" style={{
              left: `${l.x}%`, top: `${l.y}%`,
              animationDelay: `${2.4 + l.order * 0.45}s`,
            }}>
              <span className="hf-tick" />
              <span className="hf-name">{l.name}</span>
              <span className="hf-coord mono">
                {formatCoord(l.lat, 'lat')} {formatCoord(l.lon, 'lon')}
              </span>
            </div>
          ))}
        </div>

        {/* The collage. Three interventions, present for about three seconds
            in the middle of the loop, drawn as archival line-work rather than
            as stickers. */}
        <svg className="hf-collage" viewBox="0 0 1400 900" preserveAspectRatio="xMidYMid slice">
          <g className="hf-sun">
            <circle cx="1128" cy="286" r="38" />
            {Array.from({ length: 24 }, (_, i) => {
              const a = (i / 24) * Math.PI * 2
              const r1 = i % 2 ? 52 : 58
              const r2 = i % 2 ? 72 : 86
              return (
                <line key={i}
                  x1={1128 + Math.cos(a) * r1} y1={286 + Math.sin(a) * r1}
                  x2={1128 + Math.cos(a) * r2} y2={286 + Math.sin(a) * r2} />
              )
            })}
          </g>

          {/* A botanical sprig, the kind pressed into a field guide. */}
          <g className="hf-sprig">
            <path d="M172 742 C 186 700, 196 660, 200 616" />
            {[0, 1, 2, 3, 4].map((i) => {
              const y = 720 - i * 26
              const x = 176 + i * 5
              return (
                <g key={i}>
                  <path d={`M${x} ${y} C ${x - 26} ${y - 8}, ${x - 32} ${y - 26}, ${x - 14} ${y - 30}`} />
                  <path d={`M${x} ${y} C ${x + 26} ${y - 8}, ${x + 32} ${y - 26}, ${x + 14} ${y - 30}`} />
                </g>
              )
            })}
          </g>

          {/* A surveyor's annotation: a bracket around a stretch of coast and a
              hand-drawn leader line, the way a field note marks a spot. */}
          <g className="hf-annot">
            <path d="M905 596 l0 -13 68 0 0 13" />
            <path d="M939 583 C 946 556, 962 540, 986 534" />
            <circle cx="991" cy="533" r="3.2" />
          </g>
        </svg>

        {/* The scan sweep. One pass per loop, the only moving orange. */}
        <div className="hf-sweep" />
      </div>

      {/* Instrument furniture, fixed to the frame rather than drifting with
          the sheet — an instrument's own labelling does not move with what it
          is looking at. */}
      <div className="hf-hud">
        <span className="hf-hud-tl mono">SITE SCANNER · FIELD INTELLIGENCE / 01</span>
        <span className="hf-hud-tr mono">ENGLAND &amp; WALES · FIELD SHEET</span>
        <span className="hf-hud-bl mono">LAND · HABITAT · COASTAL</span>
        <span className="hf-hud-br mono hf-complete">SCAN COMPLETE</span>
      </div>

      <div className="hf-grain" />
      <div className="hf-vignette" />
    </div>
  )
}
