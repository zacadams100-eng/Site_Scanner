import { useMemo, useState } from 'react'
import { useStore } from '../store'
import { formatArea } from '../lib/format'
import { relativeTime, thumbnailPath } from '../lib/thumbnail'

/**
 * The home screen: you land on your work, not on an empty canvas.
 *
 * The idea is Procreate's, and the part worth borrowing is not the grid. It is
 * that opening the app puts your own things in front of you instead of a blank
 * document and a file menu. Everything a returning user wants is one click,
 * and nothing has to be found.
 *
 * ## The thumbnail is the site's own outline
 *
 * People do not recognise a site by its name. "Manor Farm" and "Manor Farm 2"
 * are indistinguishable in a list; a long roadside strip and a fat rectangle
 * are not. So each card draws the boundary that was traced, from the geometry
 * already in `localStorage` — no tiles, no network, no screenshot to capture
 * or store, and it works offline. See `lib/thumbnail.ts` for the projection,
 * which has to correct for longitude or every English site draws stretched.
 *
 * ## The empty state is the important one
 *
 * A first-time user has no sites, and for them this screen is pure obstacle.
 * `docs/USER-TESTING.md` names the one measurement that matters — seconds
 * until they draw a shape — so with nothing saved this gets out of the way and
 * says the one thing that needs saying. It does not explain the catalogue, the
 * templates or the timeline; those are discoverable once there is a shape on
 * the map, and none of them are reachable before there is one.
 *
 * ## Two places, one component
 *
 * `screen` renders it as the full-window home screen; without it, it renders
 * inside the report panel. The same list either way — the difference is only
 * how much room it is given and, in `screen`, a way back to a site that is
 * already open. Which one appears is `store.home`, and the reason a returning
 * user gets the window while a newcomer gets the panel is documented on
 * `openOnGallery` in the store.
 */

const THUMB = { width: 148, height: 96 }

export default function Gallery({ screen = false }: { screen?: boolean }) {
  const saved = useStore((s) => s.saved)
  const loadSaved = useStore((s) => s.loadSaved)
  const deleteSaved = useStore((s) => s.deleteSaved)
  const renameSaved = useStore((s) => s.renameSaved)
  const setDrawMode = useStore((s) => s.setDrawMode)
  const catalog = useStore((s) => s.catalog)
  // Only for the way back: with a site already open, the gallery is a detour
  // and leaving it must not require drawing something.
  const aoi = useStore((s) => s.aoi)
  const setHome = useStore((s) => s.setHome)

  const [renaming, setRenaming] = useState<string | null>(null)

  // Most recent first. A gallery ordered by creation puts the thing you were
  // working on five minutes ago at the bottom of the page.
  const sites = useMemo(
    () => [...saved].sort((a, b) => b.savedAt - a.savedAt), [saved])

  const cls = `gallery${screen ? ' gallery-screen' : ''}`

  if (!sites.length) {
    return (
      <div className={`${cls} gallery-empty`}>
        <h1 className="gallery-empty-title">Draw an area on the map</h1>
        <p className="gallery-empty-sub">
          Press and drag anywhere in England. Everything else — the layers, the
          fifteen-year record, the report — follows from the shape.
        </p>
        <button className="btn btn-primary" onClick={() => setDrawMode('rect')}>
          Start with a rectangle
        </button>
        {catalog && (
          <p className="gallery-empty-meta mono">
            {catalog.summary.factor_count} factors ·{' '}
            {catalog.summary.real_factor_count ?? 0} from real data ·{' '}
            {catalog.time.start.slice(0, 4)}–{catalog.time.end.slice(0, 4)}
          </p>
        )}
      </div>
    )
  }

  return (
    <div className={cls}>
      <div className="gallery-head">
        <h1 className="gallery-title">
          Your sites
          <span className="gallery-count mono">{sites.length}</span>
        </h1>
        <div className="gallery-actions">
          {/* Only when there is something to go back to. A "back to map"
              button with an empty map behind it promises a place that isn't
              there. */}
          {screen && aoi && (
            <button className="btn btn-secondary btn-sm" onClick={() => setHome(false)}>
              Back to the map
            </button>
          )}
          <button className={`btn btn-sm ${screen ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setDrawMode('rect')}>
            Draw a new one
          </button>
        </div>
      </div>

      <ul className="gallery-grid">
        {sites.map((site) => {
          const d = thumbnailPath(site.geometry, THUMB)
          return (
            <li key={site.id} className="site-card">
              {/* The thumbnail is the open affordance, as in any gallery —
                  the whole tile, not a small link inside it. */}
              <button className="site-open" onClick={() => loadSaved(site.id)}
                      title={`Open ${site.name}`}>
                <svg className="site-thumb" viewBox={`0 0 ${THUMB.width} ${THUMB.height}`}
                     width="100%" role="img"
                     aria-label={`Outline of ${site.name}`}>
                  {d
                    ? <path d={d} className="site-outline" />
                    /* No usable geometry. Saying so beats drawing a dot that
                       reads as a very small site. */
                    : <text x="50%" y="50%" className="site-thumb-none"
                            textAnchor="middle">no outline</text>}
                </svg>
              </button>

              <div className="site-meta">
                {renaming === site.id ? (
                  <input
                    className="site-rename"
                    defaultValue={site.name}
                    autoFocus
                    aria-label="Site name"
                    onBlur={(e) => { renameSaved(site.id, e.target.value); setRenaming(null) }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        renameSaved(site.id, (e.target as HTMLInputElement).value)
                        setRenaming(null)
                      }
                      if (e.key === 'Escape') setRenaming(null)
                    }}
                  />
                ) : (
                  <button className="site-name" onClick={() => setRenaming(site.id)}
                          title="Rename">
                    {site.name}
                  </button>
                )}

                <p className="site-facts">
                  <span className="mono">{formatArea(site.area_ha)}</span>
                  {!!site.factors?.length && (
                    <><span className="sep">·</span>
                      <span className="mono">{site.factors.length}</span>
                      {site.factors.length === 1 ? ' layer' : ' layers'}</>
                  )}
                  {!!site.markers?.length && (
                    <><span className="sep">·</span>
                      <span className="mono">{site.markers.length}</span> marked</>
                  )}
                </p>
                <p className="site-when">{relativeTime(site.savedAt)}</p>
              </div>

              <button className="site-delete icon-btn"
                      aria-label={`Delete ${site.name}`}
                      title="Delete"
                      onClick={() => {
                        // A saved site is minutes of tracing and there is no
                        // undo for this one.
                        if (confirm(`Delete “${site.name}”? This cannot be undone.`)) {
                          deleteSaved(site.id)
                        }
                      }}>
                <svg viewBox="0 0 24 24" width="15" height="15" fill="none"
                     stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
                  <path d="M6 6 18 18M18 6 6 18" />
                </svg>
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
