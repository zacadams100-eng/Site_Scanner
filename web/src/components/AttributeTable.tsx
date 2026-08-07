import { Fragment, useMemo, useState } from 'react'
import { useStore } from '../store'
import { confidenceBand, formatValue, labelStep } from '../lib/format'
import { coverageCaveat, coverageGrade, coverageMark } from '../lib/coverage'
import { annualRows, exportAnnualCsv } from '../lib/exports'
import type { Series } from '../types'
import { isReal } from '../lib/format'

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

  /** TSV, because that is what pastes cleanly into Excel and Google Sheets.
   *  Shares annualRows with the CSV export: these were two hand-maintained
   *  copies of the same loop, which is how the partial-year caveat came to be
   *  missing from both. */
  const copyTsv = () => {
    const { header, rows } = annualRows(cols)
    const lines = [header.join('\t'), ...rows.map((r) => r.join('\t'))]
    void navigator.clipboard.writeText(lines.join('\n'))
  }

  const downloadCsv = () => exportAnnualCsv(cols, data?.area_ha ?? 0)

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
                    title={`${c.meta.note}\n\nSource: ${c.meta.base_meta.name}` +
                      (isReal(c.source)
                        ? `\n\nLive Earth Engine data${c.elapsed_ms ? ` — ${(c.elapsed_ms / 1000).toFixed(1)}s to fetch` : ''}`
                        : c.error
                          ? `\n\n${c.error}`
                          : '\n\nDemo data — not observed')}>
                  <span className="th-name">
                    {isReal(c.source) && <span className="live" title="Live Earth Engine data">●</span>}
                    {c.meta.name}
                  </span>
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
                // The fragment needs the key, not the row inside it — React
                // cannot see through an unkeyed wrapper.
                <Fragment key={y}>
                  <tr
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
                      const grade = coverageGrade(r)
                      const mark = coverageMark(r)
                      // One sentence, computed once, used by the tooltip here
                      // and by every export. Four copies of this text is how
                      // the table and the CSV came to disagree before.
                      const caveat = coverageCaveat(c, r)
                      return (
                        <td
                          key={c.factor_id}
                          className={`num band-${band} cov-${grade}`}
                          title={
                            [caveat,
                             r.min !== null
                               ? `Range ${formatValue(r.min, c.meta)}–${formatValue(r.max, c.meta)}`
                               : null,
                            ].filter(Boolean).join(' ') || undefined
                          }
                        >
                          {formatValue(r.value, c.meta)}
                          {/* A severe gap gets the month count, not a dot. The
                              dot hints that a problem exists; this states it,
                              in the last place anyone looks before quoting the
                              number. Not aria-hidden at that grade — a screen
                              reader user needs it more, not less. */}
                          {mark && (
                            <span className={`partial is-${grade}`}
                                  aria-hidden={grade === 'slight' || undefined}>
                              {mark}
                            </span>
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
                </Fragment>
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
