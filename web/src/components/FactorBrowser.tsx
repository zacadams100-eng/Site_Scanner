import { useMemo, useState } from 'react'
import { groupFactors, useStore } from '../store'

/**
 * An open catalogue of 118 factors is only an asset if it can be searched.
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
        <div className="factor-browser">
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
                title="Show only factors backed by real satellite observations. Everything else is demo data."
              >
                <span className="live-dot" aria-hidden /> Live data only
                <span className="browser-filter-count">{realCount}</span>
              </button>
              {liveOnly && (
                <span className="browser-filter-note">
                  Hiding {catalog.summary.factor_count - realCount} demo factors
                </span>
              )}
            </div>
          )}

          <div className="browser-meta">
            {catalog.summary.factor_count} factors · {realCount} live · {catalog.summary.stored_base_count} stored
            datasets · {catalog.summary.derived_factor_count} derived
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
                          }\n${f.real
                            ? 'Live — real satellite observations'
                            : 'Demo data — generated, not observed'}`}
                        >
                          <span className="factor-check">{on ? '✓' : ''}</span>
                          <span className="factor-name">{f.name}</span>
                          {f.real && (
                            <span className="live-dot" title="Live — real satellite observations" />
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
