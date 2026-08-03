import { useEffect, useMemo, useRef } from 'react'
import * as Plot from '@observablehq/plot'
import { useStore } from '../store'
import { inferCharts, type ChartSpec } from '../lib/charts'
import { seriesColor, stepToDate } from '../lib/format'
import type { Series } from '../types'

/**
 * Charts are generated from the table's data, never from a separate fetch.
 * Filter or change the selection and these follow — which removes an entire
 * class of "which data is this chart showing?" confusion.
 *
 * Observable Plot is used rather than Chart.js precisely because the chart type
 * is chosen by code here: Plot takes a description of the encoding (x is time,
 * y is value, colour is series) and picks sensible scales itself, which is the
 * right API when no human is naming the chart.
 */
export default function ChartStack() {
  const data = useStore((s) => s.data)
  const selected = useStore((s) => s.selected)

  const all = useMemo(
    () => selected.map((id) => data?.series[id]).filter((s): s is Series => !!s),
    [selected, data],
  )
  const specs = useMemo(() => (all.length ? inferCharts(all) : []), [all])

  if (!data || !all.length) return null

  return (
    <div className="chart-stack">
      {specs.map((spec, i) => (
        <ChartCard key={i} spec={spec} all={all} />
      ))}
      {specs.length === 0 && (
        <div className="empty-note">No chart fits the current selection.</div>
      )}
    </div>
  )
}

function ChartCard({ spec, all }: { spec: ChartSpec; all: Series[] }) {
  const ref = useRef<HTMLDivElement>(null)
  const timeIndex = useStore((s) => s.timeIndex)
  const setTimeIndex = useStore((s) => s.setTimeIndex)
  const catalog = useStore((s) => s.catalog)
  const steps = catalog?.time.steps ?? []

  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.innerHTML = ''

    const width = el.clientWidth || 380
    const currentDate = steps[timeIndex] ? stepToDate(steps[timeIndex]) : null

    // A vertical rule marking the timeline's position, on every time-based
    // chart. It is what ties the charts to the map and the scrubber.
    const timeMarker = currentDate
      ? [Plot.ruleX([currentDate], { stroke: '#ff7a5c', strokeWidth: 1.5, strokeOpacity: 0.8 })]
      : []

    const base = {
      width,
      height: 210,
      marginLeft: 52,
      marginRight: 14,
      marginTop: 12,
      marginBottom: 28,
      style: { background: 'transparent', color: '#94a3b8', fontSize: '10px' },
      grid: true,
    }

    let chart: (SVGSVGElement | HTMLElement) | null = null

    if (spec.type === 'line') {
      const rows = spec.factorIds.flatMap((fid) => {
        const s = all.find((a) => a.factor_id === fid)!
        return s.points
          .filter((p) => typeof p.value === 'number')
          .map((p) => ({ date: stepToDate(p.t), value: p.value as number, name: s.meta.name }))
      })
      chart = Plot.plot({
        ...base,
        color: { domain: spec.factorIds.map((f) => all.find((a) => a.factor_id === f)!.meta.name),
                 range: spec.factorIds.map((_, i) => seriesColor(i)), legend: spec.factorIds.length > 1 },
        y: { label: spec.unit, labelAnchor: 'top' },
        x: { label: null },
        marks: [
          // Gaps genuinely break the line. Plot does this natively when the
          // point is absent, which is why nulls are filtered rather than zeroed.
          Plot.lineY(rows, { x: 'date', y: 'value', stroke: 'name', strokeWidth: 1.6, curve: 'linear' }),
          ...timeMarker,
          Plot.ruleY([0], { stroke: '#2b3a52', strokeOpacity: 0.4 }),
        ],
      })
    } else if (spec.type === 'stacked') {
      const rows = spec.factorIds.flatMap((fid) => {
        const s = all.find((a) => a.factor_id === fid)!
        return s.annual
          .filter((r) => typeof r.value === 'number')
          .map((r) => ({ year: new Date(r.year, 6, 1), value: r.value as number, name: s.meta.name }))
      })
      chart = Plot.plot({
        ...base,
        color: { legend: true, range: spec.factorIds.map((_, i) => seriesColor(i)) },
        y: { label: '%' },
        x: { label: null },
        marks: [Plot.areaY(rows, { x: 'year', y: 'value', fill: 'name', fillOpacity: 0.85 })],
      })
    } else if (spec.type === 'bar') {
      const s = all.find((a) => a.factor_id === spec.factorId)!
      const counts = new Map<string, number>()
      for (const r of s.annual) {
        if (typeof r.value === 'string') counts.set(r.value, (counts.get(r.value) ?? 0) + 1)
      }
      const rows = [...counts].map(([name, n]) => ({ name, n }))
      chart = Plot.plot({
        ...base,
        marginLeft: 96,
        y: { label: null },
        x: { label: 'years' },
        marks: [Plot.barX(rows, { x: 'n', y: 'name', fill: seriesColor(1), sort: { y: '-x' } })],
      })
    } else if (spec.type === 'scatter') {
      const a = all.find((s) => s.factor_id === spec.x)!
      const b = all.find((s) => s.factor_id === spec.y)!
      const bByYear = new Map(b.annual.map((r) => [r.year, r.value]))
      const rows = a.annual
        .filter((r) => typeof r.value === 'number' && typeof bByYear.get(r.year) === 'number')
        .map((r) => ({ x: r.value as number, y: bByYear.get(r.year) as number, year: r.year }))
      chart = Plot.plot({
        ...base,
        x: { label: `${a.meta.name} (${a.unit})` },
        y: { label: `${b.meta.name} (${b.unit})` },
        marks: [
          Plot.dot(rows, { x: 'x', y: 'y', fill: seriesColor(0), r: 3.5, fillOpacity: 0.85 }),
          Plot.linearRegressionY(rows, { x: 'x', y: 'y', stroke: '#6fc3d4', strokeOpacity: 0.6 }),
        ],
      })
    }

    if (chart) {
      el.append(chart)
      // Clicking a time chart moves the scrubber — the charts drive the map,
      // not just the other way round.
      if (spec.type === 'line' && steps.length) {
        chart.addEventListener('click', (ev) => {
          const rect = (chart as SVGSVGElement).getBoundingClientRect()
          const frac = ((ev as MouseEvent).clientX - rect.left - base.marginLeft) /
            (rect.width - base.marginLeft - base.marginRight)
          setTimeIndex(Math.max(0, Math.min(steps.length - 1, Math.round(frac * (steps.length - 1)))))
        })
        ;(chart as SVGSVGElement).style.cursor = 'crosshair'
      }
    }
    return () => { el.innerHTML = '' }
  }, [spec, all, timeIndex, steps, setTimeIndex])

  return (
    <div className="chart-card">
      <div className="chart-head">
        <div className="chart-title">{spec.title}</div>
        <div className="chart-reason">{spec.reason}</div>
      </div>
      <div ref={ref} className="chart-body" />
    </div>
  )
}
