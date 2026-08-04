import { useEffect, useMemo, useRef, useState } from 'react'
import { groupFactors, useStore } from '../store'
import type { Factor } from '../types'

/**
 * One line saying exactly what stands behind a factor's number.
 *
 * Three states, and the middle one is the reason this function exists: a
 * factor can be real, fetched from a named endpoint, and still never have been
 * run against that endpoint by anyone. Collapsing that into the same green dot
 * as a checked source would be the most consequential lie in the interface.
 */
export function provenanceLine(f: Factor): string {
  if (!f.real) return 'Generated demo data — not observed'
  const p = f.provenance
  if (!p) return 'Real observations'
  const via = p.endpoint && !p.source.toLowerCase().includes(p.endpoint.split('.')[0])
    ? ` via ${p.endpoint}`
    : ''
  const head = p.status === 'verified'
    ? `Real — ${p.source}${via}, checked against the live service`
    : `Real — ${p.source}${via}, implemented and tested but not yet run live`
  return p.note ? `${head}\n(${p.note})` : head
}

/**
 * An open catalogue of 269 factors is only an asset if it can be searched.
 * A flat list that long is worse than a curated eight, so this leads with a
 * search box and groups everything beneath it.
 *
 * Each factor shows which base dataset it comes from and whether it is derived,
 * because "slope, aspect and ruggedness all come off one elevation raster" is
 * genuinely useful for a user deciding what to add — and it is the same fact
 * that makes the catalogue affordable to run.
 */
export default function FactorBrowser() {
  const catalog = useStore((s) => s.catalog)
  const selected = useStore((s) => s.selected)
  const toggleFactor = useStore((s) => s.toggleFactor)
  const open = useStore((s) => s.browserOpen)
  const setOpen = useStore((s) => s.setBrowserOpen)
  const [q, setQ] = useState('')
  const [liveOnly, setLiveOnly] = useState(false)
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())

  const realCount = catalog?.summary.real_factor_count ?? 0
  const totalCount = catalog?.summary.factor_count ?? 0
  const verifiedCount = catalog?.summary.verified_factor_count ?? 0
  const realPct = totalCount ? Math.round((realCount / totalCount) * 100) : 0
  const panelRef = useRef<HTMLDivElement>(null)

  // Escape and an outside click both close it. The browser covers a third of
  // the map, and hunting for the button that opened it to get rid of it is a
  // small tax paid every single time.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node
      if (!panelRef.current?.contains(t) && !(t as HTMLElement).closest?.('.browser-toggle')) {
        setOpen(false)
      }
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('mousedown', onDown)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('mousedown', onDown)
    }
  }, [open, setOpen])

  const grouped = useMemo(() => {
    if (!catalog) return {}
    const needle = q.trim().toLowerCase()
    let matched = catalog.factors
    if (needle) {
      matched = matched.filter(
        (f) =>
          f.name.toLowerCase().includes(needle) ||
          f.group.toLowerCase().includes(needle) ||
          f.note.toLowerCase().includes(needle) ||
          f.unit.toLowerCase().includes(needle),
      )
    }
    // Keeping a factor already on the report visible even when it fails the
    // filter: hiding a selected row makes it un-toggleable, which reads as the
    // checkbox being stuck rather than as a filter doing its job.
    if (liveOnly) matched = matched.filter((f) => f.real || selected.includes(f.id))
    return groupFactors(matched)
  }, [catalog, q, liveOnly, selected])

  if (!catalog) return null
  const atLimit = selected.length >= 12

  return (
    <>
      <button
        className={`browser-toggle${open ? ' is-open' : ''}`}
        onClick={() => setOpen(!open)}
        title="Browse factors"
      >
        <span className="count">{selected.length}</span>
        <span>Factors</span>
      </button>

      {open && (
        <div className="factor-browser" ref={panelRef}>
          <div className="browser-head">
            <input
              autoFocus
              className="browser-search"
              placeholder={`Search ${catalog.summary.factor_count} factors…`}
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
            <button className="browser-close" onClick={() => setOpen(false)} aria-label="Close">×</button>
          </div>

          {realCount > 0 && (
            <div className="browser-filters">
              <button
                className={`browser-filter${liveOnly ? ' is-on' : ''}`}
                onClick={() => setLiveOnly(!liveOnly)}
                aria-pressed={liveOnly}
                title="Show only factors backed by real observations — satellite or public open data. Everything else is generated demo data."
              >
                <span className="live-dot" aria-hidden /> Real data only
                <span className="browser-filter-count">{realCount}</span>
              </button>
              {liveOnly && (
                <span className="browser-filter-note">
                  Hiding {totalCount - realCount} generated factors
                </span>
              )}
            </div>
          )}

          {/*
            The ratio, drawn rather than described. Most of this catalogue is
            demo data, and a user is entitled to know that at a glance and
            before choosing — not by counting dots, and not from a paragraph in
            a README they will never open.
          */}
          <div className="real-ratio" title={
            `${realCount} of ${totalCount} factors return real observations.\n` +
            `${verifiedCount} have been run against the live service and checked; ` +
            `${realCount - verifiedCount} are implemented and tested but not yet run for real.\n` +
            `The remaining ${totalCount - realCount} are generated demo data.`
          }>
            <div className="real-ratio-bar" role="img"
                 aria-label={`${realCount} of ${totalCount} factors real, ${realPct} per cent`}>
              <span className="seg is-verified" style={{ width: `${(verifiedCount / (totalCount || 1)) * 100}%` }} />
              <span className="seg is-written" style={{ width: `${((realCount - verifiedCount) / (totalCount || 1)) * 100}%` }} />
            </div>
            {/* Two lines on purpose: the headline is the number people need,
                the breakdown is for anyone who wants to know how solid it is.
                Letting one long line wrap wherever the panel happens to end
                puts the break in a different place at every width. */}
            <div className="real-ratio-key">
              <span className="real-ratio-head">
                <b>{realCount}</b> of {totalCount} factors return real data ({realPct}%)
              </span>
              <span className="real-ratio-detail">
                {verifiedCount} verified
                <span className="sep">·</span>
                {realCount - verifiedCount} written, not yet run
                <span className="sep">·</span>
                {totalCount - realCount} generated
              </span>
            </div>
          </div>

          <div className="browser-meta">
            {catalog.summary.stored_base_count} stored datasets ·{' '}
            {catalog.summary.derived_factor_count} derived
            {atLimit && <span className="limit-warn">12 selected — remove one to add another</span>}
          </div>

          <div className="browser-list">
            {Object.entries(grouped).map(([group, factors]) => {
              const isCollapsed = collapsed.has(group)
              return (
                <div key={group} className="browser-group">
                  <button
                    className="group-head"
                    onClick={() => {
                      const next = new Set(collapsed)
                      next.has(group) ? next.delete(group) : next.add(group)
                      setCollapsed(next)
                    }}
                  >
                    <span className="disclosure">{isCollapsed ? '▸' : '▾'}</span>
                    {group}
                    <span className="group-count">{factors.length}</span>
                  </button>
                  {!isCollapsed &&
                    factors.map((f) => {
                      const on = selected.includes(f.id)
                      const blocked = !on && atLimit
                      return (
                        <button
                          key={f.id}
                          className={`factor-row${on ? ' is-on' : ''}${blocked ? ' is-blocked' : ''}`}
                          onClick={() => toggleFactor(f.id)}
                          disabled={blocked}
                          title={`${f.note}\n\nSource: ${f.base}\nCadence: ${f.cadence}${
                            f.derived ? '\nDerived — computed from the base, not stored separately' : ''
                          }\n\n${provenanceLine(f)}`}
                        >
                          <span className="factor-check">{on ? '✓' : ''}</span>
                          <span className="factor-name">{f.name}</span>
                          {f.real && (
                            <span
                              className={`live-dot${f.provenance?.status === 'written' ? ' is-unverified' : ''}`}
                              title={provenanceLine(f)}
                            />
                          )}
                          {f.derived && <span className="factor-derived" title="Derived on read">ƒ</span>}
                          {f.kind === 'categorical' && <span className="factor-cat" title="Categorical — never averaged">cat</span>}
                          <span className="factor-unit">{f.unit}</span>
                        </button>
                      )
                    })}
                </div>
              )
            })}
            {Object.keys(grouped).length === 0 && (
              <div className="empty-note">
                {q ? <>Nothing matches “{q}”</> : <>Nothing to show</>}
                {liveOnly && <> among the live factors — turn off the filter to see demo data.</>}
                {!liveOnly && <>.</>}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  )
}
