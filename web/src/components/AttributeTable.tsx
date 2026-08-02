import { useMemo, useState } from 'react'
import { useStore } from '../store'
import { confidenceBand, formatValue, labelStep } from '../lib/format'
import type { Series } from '../types'

/**
 * One row per year (decision 5), each expandable into its twelve months.
 *
 * Fifteen rows is readable at a glance, which is the point — the annual view
 * answers "how did this site change?" without scrolling, and the monthly
 * detail is one click away when a particular year looks interesting.
 *
 * Excel conventions are load-bearing here and are followed deliberately:
 * tabular numerals, right-aligned figures, sticky headers, sortable columns,
 * and Cmd+C copying TSV that pastes straight into a spreadsheet.
 */
export default function AttributeTable() {
  const data = useStore((s) => s.data)
  const selected = useStore((s) => s.selected)
  const timeIndex = useStore((s) => s.timeIndex)
  const setTimeIndex = useStore((s) => s.setTimeIndex)
  const catalog = useStore((s) => s.catalog)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [sortCol, setSortCol] = useState<string>('year')
  const [sortAsc, setSortAsc] = useState(true)

  const cols = useMemo(
    () => selected.map((id) => data?.series[id]).filter((s): s is Series => !!s),
    [selected, data],
  )

  const years = useMemo(() => {
    if (!cols.length) return []
    const ys = cols[0].annual.map((r) => r.year)
    const sorted = [...ys]
    if (sortCol === 'year') sorted.sort((a, b) => (sortAsc ? a - b : b - a))
    else {
      const s = cols.find((c) => c.factor_id === sortCol)
      if (s) {
        const by = new Map(s.annual.map((r) => [r.year, r.value]))
        sorted.sort((a, b) => {
          const va = by.get(a), vb = by.get(b)
          if (va === null || va === undefined) return 1
          if (vb === null || vb === undefined) return -1
          if (typeof va === 'string' || typeof vb === 'string')
            return sortAsc ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va))
          return sortAsc ? va - vb : vb - va
        })
      }
    }
    return sorted
  }, [cols, sortCol, sortAsc])

  const currentYear = data && catalog
    ? Number(catalog.time.steps[timeIndex]?.slice(0, 4))
    : null

  if (!data || !cols.length) return null

  const toggle = (y: number) => {
    const next = new Set(expanded)
    next.has(y) ? next.delete(y) : next.add(y)
    setExpanded(next)
  }

  const sortBy = (id: string) => {
    if (sortCol === id) setSortAsc(!sortAsc)
    else { setSortCol(id); setSortAsc(id === 'year') }
  }

  /** TSV, because that is what pastes cleanly into Excel and Google Sheets. */
  const copyTsv = () => {
    const header = ['Year', ...cols.map((c) => `${c.meta.name}${c.unit ? ` (${c.unit})` : ''}`)]
    const lines = [header.join('\t')]
    for (const y of years) {
      const row = [String(y)]
      for (const c of cols) {
        const r = c.annual.find((a) => a.year === y)
        row.push(r?.value === null || r?.value === undefined ? '' : String(r.value))
      }
      lines.push(row.join('\t'))
    }
    void navigator.clipboard.writeText(lines.join('\n'))
  }

  const downloadCsv = () => {
    const header = ['Year', ...cols.map((c) => `${c.meta.name}${c.unit ? ` (${c.unit})` : ''}`)]
    const esc = (v: string) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v)
    const lines = [header.map(esc).join(',')]
    for (const y of years) {
      const row = [String(y)]
      for (const c of cols) {
        const r = c.annual.find((a) => a.year === y)
        row.push(r?.value === null || r?.value === undefined ? '' : String(r.value))
      }
      lines.push(row.map(esc).join(','))
    }
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'site-scanner-annual.csv'
    a.click()
    URL.revokeObjectURL(a.href)
  }

  return (
    <div className="table-wrap">
      <div className="table-toolbar">
        <span className="table-caption">
          One row per year · {years.length} years · {cols.length} factor{cols.length > 1 ? 's' : ''}
        </span>
        <div className="table-actions">
          <button onClick={copyTsv} title="Copy as TSV — pastes into Excel">Copy</button>
          <button onClick={downloadCsv} title="Download as CSV">CSV</button>
        </div>
      </div>

      <div className="table-scroll">
        <table className="attr-table">
          <thead>
            <tr>
              <th className="col-year sortable" onClick={() => sortBy('year')}>
                Year {sortCol === 'year' && (sortAsc ? '▲' : '▼')}
              </th>
              {cols.map((c) => (
                <th key={c.factor_id} className="sortable" onClick={() => sortBy(c.factor_id)}
                    title={`${c.meta.note}\n\nSource: ${c.meta.base_meta.name}`}>
                  <span className="th-name">{c.meta.name}</span>
                  <span className="th-unit">{c.unit}</span>
                  {sortCol === c.factor_id && <span className="th-sort">{sortAsc ? '▲' : '▼'}</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {years.map((y) => {
              const isCurrent = y === currentYear
              const open = expanded.has(y)
              return (
                <>
                  <tr
                    key={y}
                    className={`year-row${isCurrent ? ' is-current' : ''}${open ? ' is-open' : ''}`}
                    onClick={() => toggle(y)}
                  >
                    <td className="col-year">
                      <span className="disclosure">{open ? '▾' : '▸'}</span>{y}
                    </td>
                    {cols.map((c) => {
                      const r = c.annual.find((a) => a.year === y)
                      if (!r) return <td key={c.factor_id}>—</td>
                      const band = confidenceBand(r.confidence)
                      return (
                        <td
                          key={c.factor_id}
                          className={`num band-${band}`}
                          title={
                            r.value === null
                              ? 'No usable observation this year'
                              : `${r.months_observed} of ${r.months_total} months observed` +
                                (r.min !== null ? ` · range ${formatValue(r.min, c.meta)}–${formatValue(r.max, c.meta)}` : '')
                          }
                        >
                          {formatValue(r.value, c.meta)}
                          {r.months_observed < r.months_total && r.value !== null && (
                            <span className="partial" aria-hidden>·</span>
                          )}
                        </td>
                      )
                    })}
                  </tr>

                  {open &&
                    monthsOf(y, cols).map(({ step, idx, cells }) => (
                      <tr
                        key={`${y}-${step}`}
                        className={`month-row${idx === timeIndex ? ' is-current' : ''}`}
                        onClick={() => setTimeIndex(idx)}
                        title="Jump the timeline to this month"
                      >
                        <td className="col-year month-label">{labelStep(step).slice(0, 3)}</td>
                        {cells.map((cell, i) => (
                          <td key={i} className={`num band-${confidenceBand(cell.valid)}`}>
                            {cell.value === null
                              ? <span className="gap" title="No usable observation">—</span>
                              : formatValue(cell.value, cols[i].meta)}
                          </td>
                        ))}
                      </tr>
                    ))}
                </>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function monthsOf(year: number, cols: Series[]) {
  const out: { step: string; idx: number; cells: { value: number | string | null; valid: number }[] }[] = []
  const ref = cols[0]
  ref.points.forEach((p, idx) => {
    if (Number(p.t.slice(0, 4)) !== year) return
    out.push({
      step: p.t,
      idx,
      cells: cols.map((c) => ({
        value: c.points[idx]?.value ?? null,
        valid: c.points[idx]?.valid_fraction ?? 0,
      })),
    })
  })
  return out
}
