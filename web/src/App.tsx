import { useCallback, useEffect, type ReactNode } from 'react'
import { useStore } from './store'
import { fetchCatalog } from './api'
import MapCanvas from './components/MapCanvas'
import CertaintyLegend from './components/CertaintyLegend'
import Timeline from './components/Timeline'
import AttributeTable from './components/AttributeTable'
import ChartStack from './components/ChartStack'
import FactorBrowser from './components/FactorBrowser'
import Findings from './components/Findings'
import LoadingSequence from './components/LoadingSequence'
import Provenance from './components/Provenance'
import PlaceSearch from './components/PlaceSearch'
import Sidebar from './components/Sidebar'
import StatusBar from './components/StatusBar'
import Toolbar from './components/Toolbar'
import Compare from './components/Compare'
import BrandMark from './components/BrandMark'
import { formatArea } from './lib/format'
import type { DrawMode } from './types'

/** Drawing tools. Outline geometry on a 24 grid, 2px stroke, rounded joins —
 *  the same drawing rules as every other icon in the interface. */
const TOOLS: { id: Exclude<DrawMode, null>; label: string; hint: string; icon: ReactNode }[] = [
  {
    id: 'rect', label: 'Rectangle', hint: 'Drag across the map to draw a rectangle',
    icon: <rect x="4" y="6" width="16" height="12" rx="1.5" />,
  },
  {
    id: 'circle', label: 'Circle', hint: 'Drag from the centre outward',
    icon: <circle cx="12" cy="12" r="7" />,
  },
  {
    id: 'freehand', label: 'Freehand', hint: 'Drag to trace any shape',
    icon: <path d="M5 15.5c1-6 4.5-8.5 7-6.5s-1.5 6 1 7 4.5-2.5 6-6" />,
  },
  {
    id: 'point', label: 'Marker', hint: 'Click the map to mark a location',
    icon: <><path d="M12 21.5s7-6.1 7-11.5a7 7 0 1 0-14 0c0 5.4 7 11.5 7 11.5Z" /><circle cx="12" cy="10" r="2.5" /></>,
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
  const sidebarOpen = useStore((s) => s.sidebarOpen)
  const panelOpen = useStore((s) => s.panelOpen)
  const setPanelOpen = useStore((s) => s.setPanelOpen)
  const projectName = useStore((s) => s.projectName)

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
        /* The Data section's picker surfaces the detailed message; a silent
           no-op is right for a stray drag of an unrelated file. */
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
    <div className={`app${sidebarOpen ? '' : ' rail-collapsed'}${panelOpen ? '' : ' panel-closed'}`}>
      <header className="topbar">
        <div className="brand">
          <BrandMark className="brand-mark" />
          <span className="brand-name"><b>Site</b> Scanner</span>
        </div>

        <div className="topbar-doc">
          <span className="doc-name">{projectName ?? (aoi ? 'Untitled site' : 'No site open')}</span>
          {data && <span className="doc-meta mono">{formatArea(data.area_ha)}</span>}
        </div>

        <PlaceSearch />

        <div className="topbar-right">
          {isMock && (
            <span className="badge badge-mock" title="Generated data — no Earth Engine connected">
              demo data
            </span>
          )}
          {data && data.real_factors && data.real_factors.length > 0 && (
            <span className="badge badge-live"
                  title={`Live Earth Engine data for: ${data.real_factors.join(', ')}. Everything else is demo data.`}>
              {data.real_factors.length} live
            </span>
          )}
          {catalog && <span className="badge">{catalog.coverage.name}</span>}
          <FactorBrowser />
        </div>
      </header>

      <Sidebar />

      <main className="stage">
        <MapCanvas />
        <CertaintyLegend />

        {/* Map controls — one floating rectangle over the canvas, nothing else */}
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
              <svg viewBox="0 0 24 24" width="19" height="19" fill="none"
                   stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                {t.icon}
              </svg>
            </button>
          ))}
          <span className="tool-sep" aria-hidden />
          <button className="tool" onClick={undo} disabled={!canUndo}
                  title="Undo (Cmd+Z)" aria-label="Undo">
            <svg viewBox="0 0 24 24" width="19" height="19" fill="none"
                 stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M8 6 4 10l4 4" /><path d="M4 10h9a5 5 0 0 1 0 10H9" />
            </svg>
          </button>
          <button className="tool" onClick={redo} disabled={!canRedo}
                  title="Redo (Cmd+Shift+Z)" aria-label="Redo">
            <svg viewBox="0 0 24 24" width="19" height="19" fill="none"
                 stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="m16 6 4 4-4 4" /><path d="M20 10h-9a5 5 0 0 0 0 10h4" />
            </svg>
          </button>
          {aoi && (
            <button className="tool tool-clear" onClick={() => setAoi(null)}
                    title="Remove the drawn shape" aria-label="Remove the drawn shape">
              <svg viewBox="0 0 24 24" width="19" height="19" fill="none"
                   stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M6 6 18 18M18 6 6 18" />
              </svg>
            </button>
          )}
        </div>

        <div className="hint-bar">{hint}</div>

        <Timeline />
      </main>

      {/* Data panel — the Excel half */}
      <aside className="data-panel">
        <div className="panel-head">
          <div className="panel-title">
            {aoi ? 'Site report' : 'No area drawn'}
            {data && <span className="panel-sub mono">{formatArea(data.area_ha)}</span>}
            <button className="icon-btn panel-hide" onClick={() => setPanelOpen(false)}
                    title="Hide the report" aria-label="Hide the report">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor"
                   strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <path d="m10 7 5 5-5 5" />
              </svg>
            </button>
          </div>
          <div className="tabs" role="tablist">
            {(['findings', 'table', 'charts', 'sources'] as const).map((t) => (
              <button key={t} role="tab" aria-selected={tab === t}
                      className={`tab${tab === t ? ' is-active' : ''}`} onClick={() => setTab(t)}>
                {t === 'findings' ? 'Findings'
                  : t === 'table' ? 'Table'
                  : t === 'charts' ? 'Charts' : 'Sources'}
                {t === 'findings' && !!data?.insights?.length && (
                  <span className="tab-count">{data.insights.length}</span>
                )}
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
              <button className="btn btn-secondary btn-sm" onClick={loadCatalog}>Try again</button>
            </div>
          )}

          {!catalogError && !aoi && (
            <div className="placeholder">
              <p>Draw a rectangle, circle or freehand shape on the map.</p>
              <p className="placeholder-sub">
                Or open <strong>Templates</strong> in the sidebar for a worked
                starting point — development appraisal, flood exposure, grid
                connection, farm appraisal and twenty more.
              </p>
              <p className="placeholder-sub">
                The attribute table and charts generate themselves — no extra steps.
              </p>
              {catalog && (
                <p className="placeholder-meta mono">
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
                <button className="btn btn-secondary btn-sm" onClick={() => void refresh()}>
                  Try again
                </button>
              )}
            </div>
          )}

          {loading && <LoadingSequence />}

          {!loading && !error && data && (
            <>
              {tab === 'findings' && <Findings />}
              {tab === 'table' && <AttributeTable />}
              {tab === 'charts' && <><Compare /><ChartStack /></>}
              {tab === 'sources' && <Provenance />}
            </>
          )}
        </div>
      </aside>

      {!panelOpen && (
        <button className="panel-show" onClick={() => setPanelOpen(true)}>
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor"
               strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="m14 7-5 5 5 5" />
          </svg>
          Report
        </button>
      )}

      <StatusBar />
    </div>
  )
}
