import { useEffect, useMemo, useRef, useState } from 'react'
import { useStore } from '../store'
import {
  exportAnnualCsv, exportCompareCsv, exportGeoJson, exportMonthlyCsv,
  exportXml, printReport,
} from '../lib/exports'
import { shareUrl } from '../lib/permalink'
import type { Series } from '../types'

/**
 * What you do *with* a report, as opposed to what you do to build one.
 *
 * Only two things live here now — share the exact view, and get the numbers
 * out. Everything that shapes the report (layers, saved sites, importing a
 * boundary, templates) moved to the sidebar, because those are inputs and
 * these are outputs, and mixing the two is how a toolbar becomes a junk
 * drawer.
 */
export default function Toolbar() {
  const aoi = useStore((s) => s.aoi)
  const data = useStore((s) => s.data)
  const selected = useStore((s) => s.selected)
  const timeIndex = useStore((s) => s.timeIndex)
  const compareIndex = useStore((s) => s.compareIndex)

  const [menuOpen, setMenuOpen] = useState(false)
  const [flash, setFlash] = useState<string | null>(null)
  const wrapRef = useRef<HTMLDivElement>(null)

  const cols = useMemo(
    () => selected.map((id) => data?.series[id]).filter((s): s is Series => !!s),
    [selected, data],
  )

  // A menu that only closes by clicking its own button again is a menu that
  // stays open over the table.
  useEffect(() => {
    if (!menuOpen) return
    const onDown = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setMenuOpen(false)
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setMenuOpen(false) }
    window.addEventListener('mousedown', onDown)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('mousedown', onDown)
      window.removeEventListener('keydown', onKey)
    }
  }, [menuOpen])

  const say = (msg: string) => {
    setFlash(msg)
    setTimeout(() => setFlash(null), 2400)
  }

  const onShare = async () => {
    const url = shareUrl({ aoi, factors: selected, t: timeIndex, compare: compareIndex })
    try {
      await navigator.clipboard.writeText(url)
      say('Link copied — it restores this exact view')
    } catch {
      say(url)
    }
  }

  return (
    <div className="toolbar" ref={wrapRef}>
      <button className="btn btn-secondary btn-sm" disabled={!aoi} onClick={onShare}
              title="Copy a link that restores this exact view">
        Share
      </button>

      <div className="tb-wrap">
        <button className={`btn btn-secondary btn-sm${menuOpen ? ' is-open' : ''}`}
                disabled={!data} onClick={() => setMenuOpen(!menuOpen)}
                aria-expanded={menuOpen}>
          Export
        </button>
        {menuOpen && data && (
          <div className="tb-menu">
            <button onClick={() => { exportAnnualCsv(cols, data.area_ha); setMenuOpen(false) }}>
              CSV — one row per year
            </button>
            <button onClick={() => { exportMonthlyCsv(cols); setMenuOpen(false) }}>
              CSV — every month, with confidence
            </button>
            {compareIndex !== null && (
              <button onClick={() => { exportCompareCsv(cols, timeIndex, compareIndex); setMenuOpen(false) }}>
                CSV — change between the two pinned dates
              </button>
            )}
            <button onClick={() => { exportXml(cols); setMenuOpen(false) }}>
              Excel workbook
            </button>
            <button disabled={!aoi}
                    onClick={() => { if (aoi) exportGeoJson(aoi, cols, data.area_ha); setMenuOpen(false) }}>
              GeoJSON — shape plus data
            </button>
            <button onClick={() => { printReport(cols, data.area_ha, data.centroid); setMenuOpen(false) }}>
              Printable report / PDF
            </button>
          </div>
        )}
      </div>

      {flash && <div className="tb-flash" role="status">{flash}</div>}
    </div>
  )
}
