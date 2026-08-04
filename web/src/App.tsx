import { useCallback, useEffect, type ReactNode } from 'react'
import { useStore } from './store'
import { fetchCatalog } from './api'
import MapCanvas from './components/MapCanvas'
import Timeline from './components/Timeline'
import AttributeTable from './components/AttributeTable'
import ChartStack from './components/ChartStack'
import FactorBrowser from './components/FactorBrowser'
import Provenance from './components/Provenance'
import PlaceSearch from './components/PlaceSearch'
import Toolbar from './components/Toolbar'
import Templates from './components/Templates'
import Compare from './components/Compare'
import { formatArea } from './lib/format'
import type { DrawMode } from './types'

const TOOLS: { id: Exclude<DrawMode, null>; label: string; hint: string; icon: ReactNode }[] = [
  {
    id: 'rect', label: 'Rectangle', hint: 'Drag across the map to draw a rectangle',
    icon: <rect x="3" y="4.5" width="14" height="11" rx="1.5" />,
  },
  {
    id: 'circle', label: 'Circle', hint: 'Drag from the centre outward',
    icon: <circle cx="10" cy="10" r="6.5" />,
  },
  {
    id: 'freehand', label: 'Freehand', hint: 'Drag to trace any shape',
    icon: <path d="M4 13c1-5 4-7 6-5s-1 5 1 6 4-2 5-5" />,
  },
]

export default function App() {
  const catalog = useStore((s) => s.catalog)
  const catalogError = useStore((s) => s.catalogError)
  const setCatalog = useStore((s) => s.setCatalog)
  const setCatalogError = useStore((s) => s.setCatalogError)
  const setMock = useStore((s) => s.setMock)
  const isMock = useStore((s) => s.isMock)

  const drawMode = useStore((s) => s.drawMode)
  const setDrawMode = useStore((s) => s.setDrawMode)
  const aoi = useStore((s) => s.aoi)
  const setAoi = useStore((s) => s.setAoi)
  const data = useStore((s) => s.data)
  const loading = useStore((s) => s.loading)
  const error = useStore((s) => s.error)
  const tab = useStore((s) => s.activeTab)
  const setTab = useStore((s) => s.setTab)
  const refresh = useStore((s) => s.refresh)
  const undo = useStore((s) => s.undo)
  const redo = useStore((s) => s.redo)
  const canUndo = useStore((s) => s.past.length > 0)
  const canRedo = useStore((s) => s.future.length > 0)
  const setAoiFromDrop = useStore((s) => s.setAoi)

  // Named rather than inline, so the error notice can offer the same attempt
  // again instead of making the user reload the page.
  const loadCatalog = useCallback(() => {
    setCatalogError(null)
    fetch('/api/catalog')
      .then(async (r) => {
        if (!r.ok) throw new Error(`Catalogue unavailable (${r.status})`)
        // The backend stamps every response; surfacing it means nobody ever
        // mistakes generated numbers for real ones.
        setMock(r.headers.get('X-Contour-Mock') === 'true')
        setCatalog(await r.json())
      })
      .catch(() => {
        // Retry once through the typed client for a cleaner message.
        fetchCatalog()
          .then(setCatalog)
          .catch((e) => setCatalogError(e?.message ?? 'Could not reach the API'))
      })
  }, [setCatalog, setCatalogError, setMock])

  useEffect(() => { loadCatalog() }, [loadCatalog])

  // Undo/redo, and drag-and-drop of a boundary file anywhere on the map.
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
    const onDrop = async (e: DragEvent) => {
      e.preventDefault()
      const file = e.dataTransfer?.files?.[0]
      if (!file) return
      const { readAoiFile } = await import('./lib/exports')
      try {
        setAoiFromDrop(await readAoiFile(file))
      } catch {
        /* Toolbar's picker surfaces the detailed message; a silent no-op is
           right for a stray drag of an unrelated file. */
      }
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('dragover', stop)
    window.addEventListener('drop', onDrop)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('dragover', stop)
      window.removeEventListener('drop', onDrop)
    }
  }, [undo, redo, setAoiFromDrop])

  const hint = drawMode
    ? TOOLS.find((t) => t.id === drawMode)!.hint
    : aoi
      ? 'Drag the shape to move it, or a corner to resize'
      : 'Pick a tool, then drag on the map'

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
        {aoi && (
          <button className="tool tool-clear" onClick={() => setAoi(null)} title="Remove the drawn shape">
            <svg viewBox="0 0 20 20" width="19" height="19" fill="none"
                 stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
              <path d="M5 5l10 10M15 5L5 15" />
            </svg>
          </button>
        )}
      </div>

      <div className="hint-bar">{hint}</div>

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
            <b>Site</b> Scanner
          </span>
          {catalog && <span className="brand-scope">{catalog.coverage.name}</span>}
        </div>
        <PlaceSearch />
        <div className="topbar-right">
          {isMock && (
            <span className="badge badge-mock" title="Generated data — no Earth Engine connected">
              mock data
            </span>
          )}
          {data && data.real_factors && data.real_factors.length > 0 && (
            <span className="badge badge-live"
                  title={`Live Earth Engine data for: ${data.real_factors.join(', ')}. Everything else is demo data.`}>
              {data.real_factors.length} live
            </span>
          )}
          {data && (
            <span className={`badge badge-${data.precision}`}
                  title={data.precision === 'approx'
                    ? 'Approximate — from pre-aggregated cells. The exact pass refines this.'
                    : 'Exact — computed from source pixels'}>
              {data.precision}
            </span>
          )}
          <FactorBrowser />
        </div>
      </header>

      {/* Data panel — the Excel half */}
      <aside className="data-panel">
        <div className="panel-head">
          <div className="panel-title">
            {aoi ? 'Site report' : 'No area drawn'}
            {data && <span className="panel-sub">{formatArea(data.area_ha)}</span>}
          </div>
          <div className="tabs">
            {(['table', 'charts', 'sources'] as const).map((t) => (
              <button key={t} className={`tab${tab === t ? ' is-active' : ''}`} onClick={() => setTab(t)}>
                {t === 'table' ? 'Table' : t === 'charts' ? 'Charts' : 'Sources'}
              </button>
            ))}
          </div>
          <Toolbar />
        </div>

        <div className="panel-body">
          {catalogError && (
            <div className="notice notice-error">
              <strong>Can't reach the API.</strong>
              <p>{catalogError}</p>
              <p className="notice-fix">
                Start it with <code>uvicorn mock_ee_backend:app --port 8000</code>
              </p>
              {/* A backend that was not running yet is the usual cause, and it
                  is usually running a few seconds later. Reloading the whole
                  page to find out is a needless reset. */}
              <button className="tb notice-retry" onClick={loadCatalog}>Try again</button>
            </div>
          )}

          {!catalogError && !aoi && (
            <div className="placeholder">
              <p>Draw a rectangle, circle or freehand shape on the map.</p>
              <p className="placeholder-sub">
                The attribute table and charts generate themselves — no extra steps.
              </p>
              {catalog && (
                <p className="placeholder-meta">
                  {catalog.summary.factor_count} factors · {catalog.time.steps.length} monthly
                  steps · {catalog.time.start.slice(0, 4)}–{catalog.time.end.slice(0, 4)}
                </p>
              )}
            </div>
          )}

          {error && (
            <div className="notice notice-error">
              <strong>That didn't work.</strong>
              <p>{error}</p>
              {/* The drawn shape survives a failed query, so the fix for a
                  timeout or a dropped connection is to ask again — not to
                  redraw the area, which was the only route out before. */}
              {aoi && (
                <button className="tb notice-retry" onClick={() => void refresh()}>
                  Try again
                </button>
              )}
            </div>
          )}

          {loading && <div className="loading">Reading the site…</div>}

          {!loading && !error && data && (
            <>
              {tab === 'table' && <AttributeTable />}
              {tab === 'charts' && <><Compare /><ChartStack /></>}
              {tab === 'sources' && <Provenance />}
            </>
          )}
        </div>
      </aside>

      <Timeline />
      <Templates />
    </div>
  )
}
