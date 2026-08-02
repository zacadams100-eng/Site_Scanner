import { useMemo } from 'react'
import { useStore } from '../store'
import { formatValue, labelStep } from '../lib/format'
import type { Series } from '../types'

/**
 * Change between two dates.
 *
 * "What changed between X and Y" is the most common real question in temporal
 * GIS, and in ArcGIS it is a multi-step raster-calculator chore. Here the
 * timeline already holds both positions, so the answer is nearly free — pick a
 * second point and every selected factor reports its delta.
 */
export default function Compare() {
  const data = useStore((s) => s.data)
  const selected = useStore((s) => s.selected)
  const catalog = useStore((s) => s.catalog)
  const a = useStore((s) => s.timeIndex)
  const b = useStore((s) => s.compareIndex)
  const setCompare = useStore((s) => s.setCompareIndex)

  const cols = useMemo(
    () => selected.map((id) => data?.series[id]).filter((s): s is Series => !!s),
    [selected, data],
  )

  if (!data || b === null || !cols.length || !catalog) return null

  const steps = catalog.time.steps
  const [lo, hi] = a <= b ? [a, b] : [b, a]

  return (
    <div className="compare-card">
      <div className="compare-head">
        <div>
          <div className="chart-title">
            Change · {labelStep(steps[lo])} → {labelStep(steps[hi])}
          </div>
          <div className="chart-reason">
            {monthsBetween(steps[lo], steps[hi])} months apart
          </div>
        </div>
        <button className="tb tb-small" onClick={() => setCompare(null)}>Clear</button>
      </div>

      <table className="compare-table">
        <thead>
          <tr>
            <th>Factor</th>
            <th className="num">{labelStep(steps[lo]).replace(' ', ' ')}</th>
            <th className="num">{labelStep(steps[hi]).replace(' ', ' ')}</th>
            <th className="num">Change</th>
          </tr>
        </thead>
        <tbody>
          {cols.map((c) => {
            const pa = c.points[lo]
            const pb = c.points[hi]
            const va = pa?.value
            const vb = pb?.value

            // A gap on either end means there is no honest delta to report.
            if (va === null || vb === null || va === undefined || vb === undefined) {
              return (
                <tr key={c.factor_id}>
                  <td>{c.meta.name}</td>
                  <td className="num">{formatValue(va ?? null, c.meta)}</td>
                  <td className="num">{formatValue(vb ?? null, c.meta)}</td>
                  <td className="num gap" title="No usable observation at one end">—</td>
                </tr>
              )
            }

            if (typeof va === 'string' || typeof vb === 'string') {
              const changed = va !== vb
              return (
                <tr key={c.factor_id}>
                  <td>{c.meta.name}</td>
                  <td className="num">{va}</td>
                  <td className="num">{vb}</td>
                  <td className={`num ${changed ? 'delta-changed' : 'delta-same'}`}>
                    {changed ? 'changed' : 'no change'}
                  </td>
                </tr>
              )
            }

            const d = vb - va
            const pct = va !== 0 ? (d / Math.abs(va)) * 100 : null
            const dir = d > 0 ? 'up' : d < 0 ? 'down' : 'flat'
            return (
              <tr key={c.factor_id}>
                <td>{c.meta.name}</td>
                <td className="num">{formatValue(va, c.meta)}</td>
                <td className="num">{formatValue(vb, c.meta)}</td>
                <td className={`num delta-${dir}`}>
                  {d > 0 ? '+' : ''}{formatValue(d, c.meta)}
                  {pct !== null && Math.abs(pct) < 1000 && (
                    <span className="delta-pct">
                      {' '}{d > 0 ? '+' : ''}{pct.toFixed(0)}%
                    </span>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>

      <div className="compare-note">
        Comparing two single months carries their weather with it. For a trend,
        read the chart rather than the endpoints.
      </div>
    </div>
  )
}

function monthsBetween(a: string, b: string): number {
  const [ay, am] = a.split('-').map(Number)
  const [by, bm] = b.split('-').map(Number)
  return (by - ay) * 12 + (bm - am)
}
