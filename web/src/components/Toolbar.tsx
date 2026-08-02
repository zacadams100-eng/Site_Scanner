import { useMemo, useRef, useState } from 'react'
import { useStore } from '../store'
import {
  exportAnnualCsv, exportGeoJson, exportMonthlyCsv, exportXml,
  printReport, readAoiFile,
} from '../lib/exports'
import { shareUrl } from '../lib/permalink'
import { formatArea } from '../lib/format'
import type { Series } from '../types'

/**
 * Everything you do *with* a report, as opposed to everything you do to build
 * one: save it, share it, get the data out, bring a boundary in.
 *
 * These are grouped in one place on purpose. Scattering "export" across four
 * menus is how desktop GIS ends up with a hundred entry points and no
 * discoverability.
 */
export default function Toolbar() {
  const aoi = useStore((s) => s.aoi)
  const data = useStore((s) => s.data)
  const selected = useStore((s) => s.selected)
  const saved = useStore((s) => s.saved)
  const saveAoi = useStore((s) => s.saveAoi)
  const loadSavedAoi = useStore((s) => s.loadSaved)
  const deleteSaved = useStore((s) => s.deleteSaved)
  const setAoi = useStore((s) => s.setAoi)
  const setTemplatesOpen = useStore((s) => s.setTemplatesOpen)

  const [menu, setMenu] = useState<'none' | 'export' | 'saved'>('none')
  const [flash, setFlash] = useState<string | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const cols = useMemo(
    () => selected.map((id) => data?.series[id]).filter((s): s is Series => !!s),
    [selected, data],
  )

  const say = (msg: string) => {
    setFlash(msg)
    setTimeout(() => setFlash(null), 2200)
  }

  const onShare = async () => {
    const url = shareUrl({
      aoi, factors: selected,
      t: useStore.getState().timeIndex,
      compare: useStore.getState().compareIndex,
    })
    try {
      await navigator.clipboard.writeText(url)
      say('Link copied — it restores this exact view')
    } catch {
      say(url)
    }
  }

  const onUpload = async (file: File | undefined) => {
    if (!file) return
    setUploadError(null)
    try {
      setAoi(await readAoiFile(file))
      say(`Loaded ${file.name}`)
    } catch (e: any) {
      setUploadError(e?.message ?? 'Could not read that file.')
    }
  }

  return (
    <div className="toolbar">
      <button className="tb" onClick={() => setTemplatesOpen(true)}
              title="Start from a worked example">Templates</button>

      <button className="tb" onClick={() => fileRef.current?.click()}
              title="Load a boundary from GeoJSON or KML">Upload</button>
      <input
        ref={fileRef} type="file" accept=".geojson,.json,.kml,application/geo+json"
        style={{ display: 'none' }}
        onChange={(e) => { void onUpload(e.target.files?.[0]); e.target.value = '' }}
      />

      <button className="tb" disabled={!aoi}
              onClick={() => {
                const name = prompt('Name this site', 'Untitled site')
                if (name !== null) { saveAoi(name); say('Saved') }
              }}
              title="Keep this shape for later">Save</button>

      <div className="tb-wrap">
        <button className={`tb${menu === 'saved' ? ' is-open' : ''}`}
                onClick={() => setMenu(menu === 'saved' ? 'none' : 'saved')}
                title="Your saved sites">
          Sites {saved.length > 0 && <span className="tb-count">{saved.length}</span>}
        </button>
        {menu === 'saved' && (
          <div className="tb-menu">
            {saved.length === 0 && <div className="tb-empty">Nothing saved yet.</div>}
            {saved.map((s) => (
              <div key={s.id} className="tb-saved">
                <button className="tb-saved-load"
                        onClick={() => { loadSavedAoi(s.id); setMenu('none') }}>
                  <span className="tb-saved-name">{s.name}</span>
                  <span className="tb-saved-meta">{formatArea(s.area_ha)}</span>
                </button>
                <button className="tb-saved-del" title="Delete"
                        onClick={() => deleteSaved(s.id)}>×</button>
              </div>
            ))}
          </div>
        )}
      </div>

      <button className="tb" disabled={!aoi} onClick={onShare}
              title="Copy a link that restores this exact view">Share</button>

      <div className="tb-wrap">
        <button className={`tb${menu === 'export' ? ' is-open' : ''}`} disabled={!data}
                onClick={() => setMenu(menu === 'export' ? 'none' : 'export')}>
          Export
        </button>
        {menu === 'export' && data && (
          <div className="tb-menu">
            <button onClick={() => { exportAnnualCsv(cols, data.area_ha); setMenu('none') }}>
              CSV — one row per year
            </button>
            <button onClick={() => { exportMonthlyCsv(cols); setMenu('none') }}>
              CSV — every month, with confidence
            </button>
            <button onClick={() => { exportXml(cols); setMenu('none') }}>
              Excel workbook
            </button>
            <button disabled={!aoi}
                    onClick={() => { if (aoi) exportGeoJson(aoi, cols, data.area_ha); setMenu('none') }}>
              GeoJSON — shape plus data
            </button>
            <button onClick={() => { printReport(cols, data.area_ha, data.centroid); setMenu('none') }}>
              Printable report / PDF
            </button>
          </div>
        )}
      </div>

      {flash && <div className="tb-flash">{flash}</div>}
      {uploadError && (
        <div className="tb-flash tb-flash-error" onClick={() => setUploadError(null)}>
          {uploadError}
        </div>
      )}
    </div>
  )
}
