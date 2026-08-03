import { useMemo, useRef, useState } from 'react'
import { useStore } from '../store'
import {
  exportAnnualCsv, exportGeoJson, exportMonthlyCsv, exportXml,
  printReport, readAoiFile,
} from '../lib/exports'
import { shareUrl } from '../lib/permalink'
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
  const projects = useStore((s) => s.projects)
  const currentProjectId = useStore((s) => s.currentProjectId)
  const saveProject = useStore((s) => s.saveProject)
  const setGalleryOpen = useStore((s) => s.setGalleryOpen)
  const setAoi = useStore((s) => s.setAoi)
  const setTemplatesOpen = useStore((s) => s.setTemplatesOpen)

  const [menu, setMenu] = useState<'none' | 'export'>('none')
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

      {/* Updates the open project when there is one, so repeated saves during
          a session leave one card in the gallery rather than a pile. Only a
          project without a name yet has to ask for one. */}
      <button className="tb" disabled={!aoi}
              onClick={() => {
                if (currentProjectId) { saveProject(); say('Saved'); return }
                const name = prompt('Name this site', 'Untitled site')
                if (name !== null) { saveProject(name); say('Saved to your sites') }
              }}
              title={currentProjectId ? 'Update this site' : 'Keep this site for later'}>
        Save
      </button>

      <button className="tb" onClick={() => setGalleryOpen(true)} title="All your sites">
        Sites {projects.length > 0 && <span className="tb-count">{projects.length}</span>}
      </button>

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
