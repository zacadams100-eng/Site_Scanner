import { useEffect, useMemo, useRef } from 'react'
import { useStore } from '../store'
import { compact, labelStep, seriesColor } from '../lib/format'

/**
 * The timeline is not just a control — it is a data display.
 *
 * Once an AOI exists it draws that area's whole 15-year series *inside* the
 * track, with an availability strip beneath it. The user sees the entire story
 * before touching anything, and the scrubber head becomes a read-head on a
 * chart they can already read. That single detail does more for "fast and
 * intuitive temporal analysis" than any other piece of this UI.
 *
 * Scrubbing costs nothing: every point is already in memory, so this repaints
 * from local state and never issues a request.
 */
export default function Timeline() {
  const catalog = useStore((s) => s.catalog)
  const data = useStore((s) => s.data)
  const selected = useStore((s) => s.selected)
  const timeIndex = useStore((s) => s.timeIndex)
  const setTimeIndex = useStore((s) => s.setTimeIndex)
  const playing = useStore((s) => s.playing)
  const setPlaying = useStore((s) => s.setPlaying)
  const compareIndex = useStore((s) => s.compareIndex)
  const setCompareIndex = useStore((s) => s.setCompareIndex)
  const setTab = useStore((s) => s.setTab)

  const steps = catalog?.time.steps ?? []
  const canvasRef = useRef<HTMLCanvasElement>(null)

  // Playback. requestAnimationFrame with an accumulator rather than
  // setInterval — a fixed timer makes 180 steps feel like a slideshow, and
  // drifts under load.
  useEffect(() => {
    if (!playing || steps.length === 0) return
    let raf = 0
    let last = performance.now()
    let acc = 0
    const MS_PER_STEP = 70

    const tick = (now: number) => {
      acc += now - last
      last = now
      if (acc >= MS_PER_STEP) {
        const advance = Math.floor(acc / MS_PER_STEP)
        acc -= advance * MS_PER_STEP
        const next = useStore.getState().timeIndex + advance
        setTimeIndex(next >= steps.length ? 0 : next)
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [playing, steps.length, setTimeIndex])

  // Keyboard: the whole timeline is operable without a mouse. ArcGIS Pro
  // cannot say this, and it costs almost nothing.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      if (e.key === 'ArrowLeft') { setTimeIndex(Math.max(0, timeIndex - 1)); e.preventDefault() }
      else if (e.key === 'ArrowRight') { setTimeIndex(Math.min(steps.length - 1, timeIndex + 1)); e.preventDefault() }
      else if (e.key === 'PageDown') { setTimeIndex(Math.max(0, timeIndex - 12)); e.preventDefault() }
      else if (e.key === 'PageUp') { setTimeIndex(Math.min(steps.length - 1, timeIndex + 12)); e.preventDefault() }
      else if (e.key === 'Home') { setTimeIndex(0); e.preventDefault() }
      else if (e.key === 'End') { setTimeIndex(steps.length - 1); e.preventDefault() }
      else if (e.key === ' ') { setPlaying(!playing); e.preventDefault() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [timeIndex, steps.length, playing, setTimeIndex, setPlaying])

  const primary = selected[0]
  const primarySeries = data?.series[primary]

  // Sparkline + availability strip.
  useEffect(() => {
    const cv = canvasRef.current
    if (!cv) return
    const ctx = cv.getContext('2d')
    if (!ctx) return

    const dpr = window.devicePixelRatio || 1
    const w = cv.clientWidth, h = cv.clientHeight
    cv.width = w * dpr; cv.height = h * dpr
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, w, h)
    if (!steps.length) return

    const stripH = 5
    const chartH = h - stripH - 3

    // Year gridlines, so 180 monthly steps stay legible.
    ctx.strokeStyle = 'rgba(255,255,255,0.05)'
    ctx.lineWidth = 1
    steps.forEach((s, i) => {
      if (!s.endsWith('-01')) return
      const x = (i / (steps.length - 1)) * w
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, chartH); ctx.stroke()
    })

    if (!primarySeries || primarySeries.kind === 'categorical') return

    const values = primarySeries.points.map((p) =>
      typeof p.value === 'number' ? p.value : null)
    const present = values.filter((v): v is number => v !== null)
    if (present.length < 2) return
    const lo = Math.min(...present), hi = Math.max(...present)
    const span = hi - lo || 1

    const x = (i: number) => (i / (steps.length - 1)) * w
    const y = (v: number) => chartH - ((v - lo) / span) * (chartH - 6) - 3

    // Fill under the line, broken at gaps.
    ctx.fillStyle = 'rgba(255,122,92,0.14)'
    let runStart = -1
    for (let i = 0; i <= values.length; i++) {
      const v = values[i]
      if (v !== null && v !== undefined) { if (runStart < 0) runStart = i; continue }
      if (runStart >= 0 && i - runStart > 1) {
        ctx.beginPath()
        ctx.moveTo(x(runStart), chartH)
        for (let k = runStart; k < i; k++) ctx.lineTo(x(k), y(values[k] as number))
        ctx.lineTo(x(i - 1), chartH)
        ctx.closePath(); ctx.fill()
      }
      runStart = -1
    }

    // The line itself. Gaps stay gaps — a cloudy month is a hole, not a
    // straight line between two distant observations.
    ctx.strokeStyle = seriesColor(0)
    ctx.lineWidth = 1.5
    ctx.lineJoin = 'round'
    let drawing = false
    ctx.beginPath()
    values.forEach((v, i) => {
      if (v === null) { drawing = false; return }
      if (!drawing) { ctx.moveTo(x(i), y(v)); drawing = true }
      else ctx.lineTo(x(i), y(v))
    })
    ctx.stroke()

    // The comparison marker, when a second position is pinned.
    if (compareIndex !== null && compareIndex >= 0 && compareIndex < steps.length) {
      const cx = x(compareIndex)
      ctx.strokeStyle = 'rgba(111,195,212,0.9)'
      ctx.lineWidth = 1.5
      ctx.setLineDash([3, 2])
      ctx.beginPath(); ctx.moveTo(cx, 0); ctx.lineTo(cx, chartH); ctx.stroke()
      ctx.setLineDash([])
    }

    // Availability strip: how much of the area produced a usable observation.
    primarySeries.points.forEach((p, i) => {
      const px = x(i)
      const bw = Math.max(1, w / steps.length)
      const f = p.valid_fraction
      ctx.fillStyle = p.value === null
        ? 'rgba(63,77,99,0.85)'
        : `rgba(111,195,212,${0.18 + 0.62 * f})`
      ctx.fillRect(px - bw / 2, chartH + 3, bw, stripH)
    })
  }, [primarySeries, steps, compareIndex])

  const step = steps[timeIndex] ?? steps[0]
  const point = primarySeries?.points[timeIndex]
  const factorName = primarySeries?.meta.name ?? ''

  // Every hook must run on every render, so this sits above the early return
  // rather than below it.
  const readout = useMemo(() => {
    if (!point) return null
    if (point.value === null) return { text: 'No usable observation', gap: true }
    return {
      text: `${compact(point.value)} ${primarySeries?.unit ?? ''}`.trim(),
      gap: false,
      confidence: point.valid_fraction,
    }
  }, [point, primarySeries])

  if (!catalog) return null

  return (
    <div className="timeline">
      <button
        className="play-btn"
        onClick={() => setPlaying(!playing)}
        aria-label={playing ? 'Pause playback' : 'Play through time'}
        title={playing ? 'Pause (space)' : 'Play (space)'}
      >
        {playing
          ? <svg viewBox="0 0 16 16" width="15" height="15" fill="currentColor"><rect x="3.5" y="2.5" width="3.2" height="11" rx="0.8" /><rect x="9.3" y="2.5" width="3.2" height="11" rx="0.8" /></svg>
          : <svg viewBox="0 0 16 16" width="15" height="15" fill="currentColor"><path d="M4.5 2.5l9 5.5-9 5.5z" /></svg>}
      </button>

      <div className="time-readout">
        <div className="time-step">{labelStep(step ?? '')}</div>
        {readout && (
          <div className={`time-value${readout.gap ? ' is-gap' : ''}`}>
            {readout.gap ? 'No data' : readout.text}
            {!readout.gap && readout.confidence !== undefined && readout.confidence < 0.4 && (
              <span className="low-conf" title="Few usable pixels this month">low confidence</span>
            )}
          </div>
        )}
        {compareIndex !== null && primarySeries ? (
          <button className="time-compare" onClick={() => setCompareIndex(null)}
                  title="Clear the comparison point">
            vs {labelStep(steps[compareIndex] ?? '')} ×
          </button>
        ) : (
          factorName && <div className="time-factor">{factorName}</div>
        )}
      </div>

      <div className="track-wrap">
        <canvas ref={canvasRef} className="track-canvas" />
        <input
          type="range"
          className="track-input"
          onPointerDown={(e) => {
            // Shift-click pins a second position rather than moving the head,
            // which keeps comparison one gesture away instead of a mode.
            if (!e.shiftKey) return
            e.preventDefault()
            const r = (e.currentTarget as HTMLElement).getBoundingClientRect()
            const frac = (e.clientX - r.left) / r.width
            setCompareIndex(Math.max(0, Math.min(steps.length - 1,
              Math.round(frac * (steps.length - 1)))))
            setTab('charts')
          }}
          min={0}
          max={Math.max(0, steps.length - 1)}
          step={1}
          value={timeIndex}
          onChange={(e) => setTimeIndex(Number(e.target.value))}
          aria-label="Time position"
          aria-valuetext={`${labelStep(step ?? '')}${
            readout ? `, ${readout.gap ? 'no data' : readout.text}` : ''}`}
        />
        <div className="track-years">
          {steps.map((s, i) =>
            s.endsWith('-01') && Number(s.slice(0, 4)) % 3 === 0 ? (
              <span key={s} className="track-year" style={{ left: `${(i / (steps.length - 1)) * 100}%` }}>
                {s.slice(0, 4)}
              </span>
            ) : null,
          )}
        </div>
      </div>
    </div>
  )
}
