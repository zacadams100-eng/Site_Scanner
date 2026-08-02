import { useMemo } from 'react'
import { useStore } from '../store'
import type { Series } from '../types'

/**
 * Every number traces back to a source, a resolution and a licence.
 *
 * This is not a compliance checkbox — it is the answer to "how do I know I can
 * trust this?", which is the question that decides whether a technical user
 * adopts the tool. GEE makes people work this out for themselves; showing it
 * plainly is a genuine differentiator.
 */
export default function Provenance() {
  const data = useStore((s) => s.data)
  const selected = useStore((s) => s.selected)

  const cols = useMemo(
    () => selected.map((id) => data?.series[id]).filter((s): s is Series => !!s),
    [selected, data],
  )

  if (!cols.length) return null

  // Group by base dataset — several factors usually share one source, and
  // repeating the licence four times is noise.
  const byBase = new Map<string, { base: Series['meta']['base_meta']; factors: Series[] }>()
  for (const c of cols) {
    const key = c.meta.base_meta.id
    if (!byBase.has(key)) byBase.set(key, { base: c.meta.base_meta, factors: [] })
    byBase.get(key)!.factors.push(c)
  }

  return (
    <div className="provenance">
      {[...byBase.values()].map(({ base, factors }) => (
        <div key={base.id} className="prov-card">
          <div className="prov-name">{base.name}</div>
          <div className="prov-grid">
            <span>Source</span><span>{base.source}</span>
            <span>Licence</span><span>{base.licence}</span>
            <span>Resolution</span>
            <span>{base.resolution_m ? `${base.resolution_m} m` : 'Vector / tabular'}</span>
            <span>Native cadence</span><span>{base.native_cadence}</span>
            <span>Stored cadence</span><span>{base.cadence}</span>
            <span>Held by us</span>
            <span>{base.stored ? 'Yes — served from our storage' : 'No — queried live'}</span>
          </div>
          <div className="prov-factors">
            {factors.map((f) => (
              <span key={f.factor_id} className="prov-chip" title={f.meta.note}>
                {f.meta.name}
                {f.meta.derived && <em title="Derived from the base at read time"> ƒ</em>}
              </span>
            ))}
          </div>
          <a className="prov-link" href={base.url} target="_blank" rel="noreferrer">
            {base.url.replace(/^https?:\/\//, '').replace(/\/$/, '')} ↗
          </a>
        </div>
      ))}
    </div>
  )
}
