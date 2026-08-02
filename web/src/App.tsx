import { useEffect, type ReactNode } from 'react'
import { useStore } from './store'
import { fetchCatalog } from './api'
import MapCanvas from './components/MapCanvas'
import Timeline from './components/Timeline'
import AttributeTable from './components/AttributeTable'
import ChartStack from './components/ChartStack'
import FactorBrowser from './components/FactorBrowser'
import Provenance from './components/Provenance'
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

  useEffect(() => {
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

  const hint = drawMode
    ? TOOLS.find((t) => t.id === drawMode)!.hint
    : aoi
      ? 'Scrub the timeline, or pick another tool to redraw'
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
          <span className="brand-mark" />
          <span className="brand-name">Site Scanner</span>
          {catalog && <span className="brand-scope">{catalog.coverage.name}</span>}
        </div>
        <div className="topbar-right">
          {isMock && (
            <span className="badge badge-mock" title="Generated data — no Earth Engine connected">
              mock data
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
        </div>

        <div className="panel-body">
          {catalogError && (
            <div className="notice notice-error">
              <strong>Can't reach the API.</strong>
              <p>{catalogError}</p>
              <p className="notice-fix">
                Start it with <code>uvicorn mock_ee_backend:app --port 8000</code>
              </p>
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
            </div>
          )}

          {loading && <div className="loading">Reading the site…</div>}

          {!loading && !error && data && (
            <>
              {tab === 'table' && <AttributeTable />}
              {tab === 'charts' && <ChartStack />}
              {tab === 'sources' && <Provenance />}
            </>
          )}
        </div>
      </aside>

      <Timeline />
    </div>
  )
}
