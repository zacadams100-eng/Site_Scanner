import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useStore } from './store'
import MapCanvas from './components/MapCanvas'
import Findings from './components/Findings'
import LayerList from './components/LayerList'
import { BASEMAPS } from './lib/basemaps'
import { formatArea } from './lib/format'
import { readRedLineFile } from './lib/readRedLine'
import type { DrawMode } from './types'
import * as turf from '@turf/turf'

const TOOLS: { id: Exclude<DrawMode, null>; label: string; hint: string; icon: ReactNode }[] = [
  {
    id: 'rect', label: 'Rectangle', hint: 'Drag across the map to draw a rectangular red line',
    icon: <rect x="3" y="4.5" width="14" height="11" rx="1.5" />,
  },
  {
    id: 'circle', label: 'Circle', hint: 'Drag from the centre outward',
    icon: <circle cx="10" cy="10" r="6.5" />,
  },
  {
    id: 'freehand', label: 'Freehand', hint: 'Drag to trace the red line',
    icon: <path d="M4 13c1-5 4-7 6-5s-1 5 1 6 4-2 5-5" />,
  },
]

export default function App() {
  const info = useStore((s) => s.info)
  const layers = useStore((s) => s.layers)
  const apiError = useStore((s) => s.apiError)
  const load = useStore((s) => s.load)

  const drawMode = useStore((s) => s.drawMode)
  const setDrawMode = useStore((s) => s.setDrawMode)
  const redLine = useStore((s) => s.redLine)
  const setRedLine = useStore((s) => s.setRedLine)
  const undo = useStore((s) => s.undo)
  const redo = useStore((s) => s.redo)
  const canUndo = useStore((s) => s.past.length > 0)
  const canRedo = useStore((s) => s.future.length > 0)

  const title = useStore((s) => s.title)
  const setTitle = useStore((s) => s.setTitle)
  const clientRef = useStore((s) => s.clientRef)
  const setClientRef = useStore((s) => s.setClientRef)
  const sheet = useStore((s) => s.sheet)
  const making = useStore((s) => s.making)
  const error = useStore((s) => s.error)
  const make = useStore((s) => s.make)
  const basemap = useStore((s) => s.basemap)
  const setBasemap = useStore((s) => s.setBasemap)

  const fileRef = useRef<HTMLInputElement>(null)
  const [fileError, setFileError] = useState<string | null>(null)

  useEffect(() => { void load() }, [load])

  const onFile = async (file: File | undefined) => {
    if (!file) return
    setFileError(null)
    try {
      setRedLine(await readRedLineFile(file))
    } catch (e: any) {
      setFileError(e?.message ?? 'Could not read that file.')
    }
  }

  // Undo/redo, and drag-and-drop of a red line file anywhere on the map.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') {
        e.preventDefault()
        e.shiftKey ? redo() : undo()
      }
    }
    const stop = (e: DragEvent) => { e.preventDefault() }
    const onDrop = (e: DragEvent) => {
      e.preventDefault()
      void onFile(e.dataTransfer?.files?.[0])
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('dragover', stop)
    window.addEventListener('drop', onDrop)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('dragover', stop)
      window.removeEventListener('drop', onDrop)
    }
  })

  const areaHa = redLine ? turf.area({ type: 'Feature', geometry: redLine, properties: {} }) / 10_000 : 0
  const tooBig = !!info && areaHa > info.max_ha

  const hint = drawMode
    ? TOOLS.find((t) => t.id === drawMode)!.hint
    : redLine
      ? 'Click a feature for its name, or pick a tool to redraw'
      : 'Pick a tool and draw the red line, or drop a GeoJSON or KML file'

  return (
    <div className="app">
      <MapCanvas />

      {/* Tool rail — floats over the canvas rather than sitting in a frame */}
      <div className="tool-rail">
        {TOOLS.map((t) => (
          <button
            key={t.id}
            className={`tool${drawMode === t.id ? ' is-active' : ''}`}
            onClick={() => setDrawMode(drawMode === t.id ? null : t.id)}
            title={t.hint}
            aria-pressed={drawMode === t.id}
            aria-label={t.label}
          >
            <svg viewBox="0 0 20 20" width="19" height="19" fill="none"
                 stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
              {t.icon}
            </svg>
          </button>
        ))}
        <button className="tool tool-sep" onClick={undo} disabled={!canUndo}
                title="Undo (Cmd+Z)" aria-label="Undo">
          <svg viewBox="0 0 20 20" width="19" height="19" fill="none"
               stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
            <path d="M7 5L3.5 8.5 7 12" /><path d="M3.5 8.5H12a4.5 4.5 0 010 9H8" />
          </svg>
        </button>
        <button className="tool" onClick={redo} disabled={!canRedo}
                title="Redo (Cmd+Shift+Z)" aria-label="Redo">
          <svg viewBox="0 0 20 20" width="19" height="19" fill="none"
               stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
            <path d="M13 5l3.5 3.5L13 12" /><path d="M16.5 8.5H8a4.5 4.5 0 000 9h4" />
          </svg>
        </button>
        {redLine && (
          <button className="tool tool-clear" onClick={() => setRedLine(null)} title="Remove the red line" aria-label="Remove the red line">
            <svg viewBox="0 0 20 20" width="19" height="19" fill="none"
                 stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
              <path d="M5 5l10 10M15 5L5 15" />
            </svg>
          </button>
        )}
      </div>

      <div className="hint-bar">{hint}</div>

      <div className="basemap-switch" role="radiogroup" aria-label="Basemap">
        {BASEMAPS.map((b) => (
          <button key={b.id} role="radio" aria-checked={basemap === b.id}
                  className={`bm${basemap === b.id ? ' is-active' : ''}`}
                  onClick={() => setBasemap(b.id)}>
            {b.name}
          </button>
        ))}
      </div>

      <header className="topbar">
        <div className="brand">
          {/* The logo's bracket, reduced to something that survives at 18px.
              The frog does not — at this size it becomes a smudge — so the
              mark keeps the frame and the copper and drops the illustration. */}
          <svg className="brand-mark" viewBox="0 0 24 24" aria-hidden focusable="false">
            <path
              d="M8 3H3v18h5M16 3h5v18h-5"
              fill="none" stroke="currentColor" strokeWidth="2.1"
              strokeLinecap="square"
            />
            <circle cx="12" cy="12" r="3.4" fill="currentColor" />
          </svg>
          <span className="brand-name">
            <b>Contour</b> Desk study map
          </span>
          <span className="brand-scope">Internal · England</span>
        </div>
        <div className="topbar-right">
          {(info?.test_data || sheet?.test_data) && (
            <span className="badge badge-test" title="Layers are read from fixture files. Nothing here is real.">
              Test data — not real
            </span>
          )}
        </div>
      </header>

      <aside className="data-panel">
        <div className="panel-head">
          <div className="panel-title">
            {sheet ? sheet.title : redLine ? 'Red line drawn' : 'No red line yet'}
            {redLine && <span className="panel-sub">{formatArea(areaHa)}</span>}
          </div>
          <div className="toolbar">
            <button className="tb" onClick={() => fileRef.current?.click()}
                    title="Load a red line from GeoJSON or KML">Upload red line</button>
            <input
              ref={fileRef} type="file" accept=".geojson,.json,.kml,application/geo+json"
              style={{ display: 'none' }}
              onChange={(e) => { void onFile(e.target.files?.[0]); e.target.value = '' }}
            />
            {fileError && <span className="tb-error">{fileError}</span>}
          </div>
        </div>

        <div className="panel-body">
          {apiError && (
            <div className="notice notice-error">
              <strong>Can't reach the sheet API.</strong>
              <p>{apiError}</p>
              <p className="notice-fix">
                Start it from the repo root with <code>uvicorn sheet.api:app --port 8000</code>
              </p>
            </div>
          )}

          {redLine && (
            <form className="sheet-form" onSubmit={(e) => { e.preventDefault(); void make() }}>
              <label>
                <span>Site title</span>
                <input value={title} onChange={(e) => setTitle(e.target.value)}
                       placeholder="Land at Home Farm, Dorking" />
              </label>
              <label className="sheet-form-ref">
                <span>Order ref</span>
                <input value={clientRef} onChange={(e) => setClientRef(e.target.value)} placeholder="ORD-001" />
              </label>
              <button className="make" type="submit" disabled={making || tooBig || !!apiError}>
                {making ? 'Making…' : sheet ? 'Make it again' : 'Make the sheet'}
              </button>
              {tooBig && (
                <p className="sheet-warn">Red line over {info!.max_ha.toLocaleString('en-GB')} ha — split it up.</p>
              )}
            </form>
          )}

          <div className="panel-scroll">
            {error && (
              <div className="notice notice-error">
                <strong>That didn't work.</strong>
                <p>{error}</p>
              </div>
            )}

            {making && (
              <div className="loading">
                Reading {layers.length} layers from Natural England, the Environment Agency,
                Historic England and planning.data…
              </div>
            )}

            {!making && sheet && <Findings />}

            {!making && !sheet && !apiError && (
              <>
                <div className="placeholder">
                  <p>{redLine ? 'Name the site, then make the sheet.' : 'Draw the red line on the map.'}</p>
                  <p className="placeholder-sub">
                    Each sheet checks these {layers.length} official layers, out to the distance shown.
                  </p>
                </div>
                <LayerList />
              </>
            )}
          </div>
        </div>
      </aside>
    </div>
  )
}
