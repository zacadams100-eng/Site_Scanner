import { useRef, useState, type ReactNode } from 'react'
import { useStore } from '../store'
import { exportSites, readAoiFile, readSitesFile } from '../lib/exports'
import { formatArea } from '../lib/format'
import { rampColor } from '../lib/format'

/**
 * The working sidebar: what is on the map, and what you can put on it.
 *
 * Everything that used to be scattered — a floating factor browser, four
 * buttons above the table, a modal of templates — is one column on the left,
 * which is where a GIS user's hand already goes. The map keeps the rest of the
 * window, and the whole column collapses to its icons when it is in the way.
 *
 * Sections are deliberately few. A rail with eleven entries reads as a product
 * that does eleven things badly; this one does four things and says so.
 */

type Section = 'layers' | 'sites' | 'data' | 'analysis'

const ICONS: Record<Section, ReactNode> = {
  // Outline, 2px, rounded — drawn on the same 24 grid so they sit level.
  layers: <><path d="M12 4 4 8.5l8 4.5 8-4.5L12 4Z" /><path d="M4 13.5 12 18l8-4.5" /></>,
  sites: <><path d="M12 21s7-5.5 7-11a7 7 0 1 0-14 0c0 5.5 7 11 7 11Z" /><circle cx="12" cy="10" r="2.5" /></>,
  data: <><path d="M12 16V5" /><path d="m8 9 4-4 4 4" /><path d="M4 16v2.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V16" /></>,
  analysis: <><path d="M4 19h16" /><path d="M7 19v-6" /><path d="M12 19V6" /><path d="M17 19v-9" /></>,
}

const LABELS: Record<Section, string> = {
  layers: 'Layers',
  sites: 'Sites',
  data: 'Data',
  analysis: 'Analysis',
}

export default function Sidebar() {
  const catalog = useStore((s) => s.catalog)
  const selected = useStore((s) => s.selected)
  const toggleFactor = useStore((s) => s.toggleFactor)
  const setSelected = useStore((s) => s.setSelected)
  const setBrowserOpen = useStore((s) => s.setBrowserOpen)
  const setTemplatesOpen = useStore((s) => s.setTemplatesOpen)
  const data = useStore((s) => s.data)
  const aoi = useStore((s) => s.aoi)
  const setAoi = useStore((s) => s.setAoi)
  const saved = useStore((s) => s.saved)
  const saveAoi = useStore((s) => s.saveAoi)
  const loadSaved = useStore((s) => s.loadSaved)
  const deleteSaved = useStore((s) => s.deleteSaved)
  const renameSaved = useStore((s) => s.renameSaved)
  const updateSaved = useStore((s) => s.updateSaved)
  const importSites = useStore((s) => s.importSites)
  const overlayOpacity = useStore((s) => s.overlayOpacity)
  const setOverlayOpacity = useStore((s) => s.setOverlayOpacity)
  const open = useStore((s) => s.sidebarOpen)
  const setOpen = useStore((s) => s.setSidebarOpen)
  const section = useStore((s) => s.sidebarSection)
  const setSection = useStore((s) => s.setSidebarSection)
  const compareIndex = useStore((s) => s.compareIndex)
  const timeIndex = useStore((s) => s.timeIndex)
  const setCompareIndex = useStore((s) => s.setCompareIndex)
  const setTab = useStore((s) => s.setTab)

  const [naming, setNaming] = useState(false)
  const [draft, setDraft] = useState('')
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const sitesFileRef = useRef<HTMLInputElement>(null)

  const say = (m: string) => { setNote(m); setTimeout(() => setNote(null), 2600) }

  const factorById = (id: string) => catalog?.factors.find((f) => f.id === id)

  const onPick = (s: Section) => {
    if (s === section && open) setOpen(false)
    else { setSection(s); setOpen(true) }
  }

  return (
    <aside className={`sidebar${open ? '' : ' is-collapsed'}`}>
      <nav className="rail" aria-label="Sections">
        {(Object.keys(LABELS) as Section[]).map((s) => (
          <button
            key={s}
            className={`rail-btn${section === s && open ? ' is-active' : ''}`}
            onClick={() => onPick(s)}
            aria-pressed={section === s && open}
            title={LABELS[s]}
          >
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor"
                 strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              {ICONS[s]}
            </svg>
            <span className="rail-label">{LABELS[s]}</span>
          </button>
        ))}
        <button className="rail-btn rail-collapse" onClick={() => setOpen(!open)}
                title={open ? 'Collapse the sidebar' : 'Expand the sidebar'}
                aria-label={open ? 'Collapse the sidebar' : 'Expand the sidebar'}>
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor"
               strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d={open ? 'm14 7-5 5 5 5' : 'm10 7 5 5-5 5'} />
          </svg>
          <span className="rail-label">{open ? 'Hide' : 'Show'}</span>
        </button>
      </nav>

      {open && (
        <div className="side-panel">
          {section === 'layers' && (
            <>
              <div className="side-head">
                <h2 className="side-title">Layers</h2>
                <button className="btn btn-secondary btn-sm" onClick={() => setBrowserOpen(true)}>
                  Add…
                </button>
              </div>
              <p className="side-note">
                The first layer is the one drawn on the map. The rest are read in
                the table and the charts.
              </p>

              <div className="layer-list">
                {selected.map((id, i) => {
                  const f = factorById(id)
                  const series = data?.series[id]
                  const isPrimary = i === 0
                  return (
                    <div key={id} className={`layer${isPrimary ? ' is-primary' : ''}`}>
                      <button
                        className="layer-vis"
                        title={isPrimary ? 'Drawn on the map' : 'Draw this one on the map'}
                        aria-label={isPrimary ? 'Drawn on the map' : 'Draw this one on the map'}
                        onClick={() => setSelected([id, ...selected.filter((s) => s !== id)])}
                      >
                        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor"
                             strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                          {isPrimary
                            ? <><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6Z" /><circle cx="12" cy="12" r="2.5" /></>
                            : <><path d="M4 4 20 20" /><path d="M2 12s3.5-6 10-6a11 11 0 0 1 4 .8M22 12s-3.5 6-10 6a11 11 0 0 1-4-.8" /></>}
                        </svg>
                      </button>

                      {/* Symbology: the ramp this layer is painted with, or a
                          flat chip for a class layer, which has no ramp. */}
                      <span
                        className="layer-ramp"
                        aria-hidden
                        style={f?.kind === 'categorical'
                          ? { background: 'var(--structure-quiet)' }
                          : { background: `linear-gradient(90deg, ${rampColor(0)}, ${rampColor(0.5)}, ${rampColor(1)})` }}
                      />

                      <span className="layer-text">
                        <span className="layer-name" title={f?.note}>{f?.name ?? id}</span>
                        <span className="layer-src">
                          {series?.meta.base_meta.name ?? f?.base}
                          {f?.real && <span className="live-dot" title="Live satellite observations" />}
                        </span>
                      </span>

                      <button className="layer-del" title="Remove this layer"
                              aria-label={`Remove ${f?.name ?? id}`}
                              onClick={() => toggleFactor(id)}>
                        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor"
                             strokeWidth="2" strokeLinecap="round" aria-hidden>
                          <path d="M6 6 18 18M18 6 6 18" />
                        </svg>
                      </button>
                    </div>
                  )
                })}
              </div>

              <label className="side-field">
                <span>Overlay opacity</span>
                <input
                  type="range" min={0} max={100} step={5}
                  value={Math.round(overlayOpacity * 100)}
                  onChange={(e) => setOverlayOpacity(Number(e.target.value) / 100)}
                />
                <span className="mono">{Math.round(overlayOpacity * 100)}%</span>
              </label>
            </>
          )}

          {section === 'sites' && (
            <>
              <div className="side-head">
                <h2 className="side-title">Sites</h2>
                <button className="btn btn-primary btn-sm" disabled={!aoi}
                        onClick={() => { setNaming(true); setDraft('') }}>
                  Save this site
                </button>
              </div>

              {naming && aoi && (
                <div className="side-card">
                  <label className="side-label" htmlFor="site-name">Name</label>
                  <input
                    id="site-name" autoFocus className="field" placeholder="Untitled site"
                    value={draft} onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') { saveAoi(draft); setNaming(false); say('Saved') }
                      if (e.key === 'Escape') setNaming(false)
                    }}
                  />
                  <p className="side-note">
                    Keeps the shape, the {selected.length} chosen layer
                    {selected.length === 1 ? '' : 's'} and the date on the timeline.
                  </p>
                  <div className="side-row">
                    <button className="btn btn-primary btn-sm"
                            onClick={() => { saveAoi(draft); setNaming(false); say('Saved') }}>
                      Save
                    </button>
                    <button className="btn btn-secondary btn-sm" onClick={() => setNaming(false)}>
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {!saved.length && !naming && (
                <p className="side-note">
                  Nothing saved yet. Draw an area, then save it — the layers and
                  the date come back with it.
                </p>
              )}

              <div className="site-list">
                {saved.map((s) => (
                  <div key={s.id} className="site">
                    {renamingId === s.id ? (
                      <input
                        autoFocus className="field" defaultValue={s.name}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            renameSaved(s.id, (e.target as HTMLInputElement).value)
                            setRenamingId(null)
                          }
                          if (e.key === 'Escape') setRenamingId(null)
                        }}
                        onBlur={(e) => { renameSaved(s.id, e.target.value); setRenamingId(null) }}
                      />
                    ) : (
                      <>
                        <button className="site-load" onClick={() => loadSaved(s.id)}
                                title={s.factors?.length
                                  ? `Restores ${s.factors.length} layers and the saved date`
                                  : 'Saved before layers were kept — restores the shape only'}>
                          <span className="site-name">{s.name}</span>
                          <span className="site-meta mono">
                            {formatArea(s.area_ha)}{s.factors?.length ? ` · ${s.factors.length} layers` : ''}
                          </span>
                        </button>
                        <button className="icon-btn" title="Rename" aria-label={`Rename ${s.name}`}
                                onClick={() => setRenamingId(s.id)}>
                          <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor"
                               strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                            <path d="M4 20h4L19 9a2.1 2.1 0 0 0-3-3L5 17v3Z" />
                          </svg>
                        </button>
                        <button className="icon-btn" title="Update with the current view" disabled={!aoi}
                                aria-label={`Update ${s.name}`}
                                onClick={() => { updateSaved(s.id); say(`Updated ${s.name}`) }}>
                          <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor"
                               strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                            <path d="M20 12a8 8 0 1 1-2.5-5.8" /><path d="M20 4v4h-4" />
                          </svg>
                        </button>
                        <button className="icon-btn icon-btn-bad" title="Delete"
                                aria-label={`Delete ${s.name}`}
                                onClick={() => deleteSaved(s.id)}>
                          <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor"
                               strokeWidth="2" strokeLinecap="round" aria-hidden>
                            <path d="M6 6 18 18M18 6 6 18" />
                          </svg>
                        </button>
                      </>
                    )}
                  </div>
                ))}
              </div>

              <div className="side-row side-row-end">
                <button className="btn btn-secondary btn-sm" disabled={!saved.length}
                        onClick={() => { exportSites(saved); say('Sites written to a file') }}>
                  Back up
                </button>
                <button className="btn btn-secondary btn-sm" onClick={() => sitesFileRef.current?.click()}>
                  Restore…
                </button>
              </div>
              <input
                ref={sitesFileRef} type="file" accept=".json,application/json"
                style={{ display: 'none' }}
                onChange={async (e) => {
                  const f = e.target.files?.[0]
                  e.target.value = ''
                  if (!f) return
                  try {
                    const n = importSites(await readSitesFile(f))
                    say(`${n} site${n === 1 ? '' : 's'} added`)
                  } catch (err: any) {
                    say(err?.message ?? 'Could not read that file.')
                  }
                }}
              />
            </>
          )}

          {section === 'data' && (
            <>
              <div className="side-head"><h2 className="side-title">Data</h2></div>
              <p className="side-note">
                Bring a boundary you already have instead of tracing it again.
                Drop a file anywhere on the map, or pick one.
              </p>
              <button className="btn btn-secondary" onClick={() => fileRef.current?.click()}>
                Choose a boundary file…
              </button>
              <input
                ref={fileRef} type="file" accept=".geojson,.json,.kml,application/geo+json"
                style={{ display: 'none' }}
                onChange={async (e) => {
                  const f = e.target.files?.[0]
                  e.target.value = ''
                  if (!f) return
                  try {
                    setAoi(await readAoiFile(f))
                    say(`Loaded ${f.name}`)
                  } catch (err: any) {
                    say(err?.message ?? 'Could not read that file.')
                  }
                }}
              />
              <dl className="side-facts">
                <dt>Accepted</dt>
                <dd className="mono">GeoJSON · KML</dd>
                <dt>Coverage</dt>
                <dd>{catalog?.coverage.name ?? 'England'}</dd>
                <dt>Largest area</dt>
                <dd className="mono">250,000 ha</dd>
              </dl>
              <p className="side-note">
                A shapefile has to be converted first — QGIS exports GeoJSON
                directly, and so does ArcGIS Pro.
              </p>
            </>
          )}

          {section === 'analysis' && (
            <>
              <div className="side-head"><h2 className="side-title">Analysis</h2></div>
              <p className="side-note">
                Start from a worked question, or compare two dates on the
                timeline.
              </p>
              <button className="btn btn-secondary" onClick={() => setTemplatesOpen(true)}>
                Start from a question…
              </button>
              <button
                className="btn btn-secondary"
                disabled={!data || timeIndex < 12}
                onClick={() => { setCompareIndex(timeIndex - 12); setTab('charts') }}
              >
                Compare with a year earlier
              </button>
              {compareIndex !== null && (
                <button className="btn btn-secondary" onClick={() => setCompareIndex(null)}>
                  Clear the comparison
                </button>
              )}
              <p className="side-note">
                Shift-click the timeline to pin any other month.
              </p>
            </>
          )}

          {note && <div className="side-flash" role="status">{note}</div>}
        </div>
      )}
    </aside>
  )
}
