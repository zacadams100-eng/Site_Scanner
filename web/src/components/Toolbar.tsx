import { useEffect, useMemo, useRef, useState } from 'react'
import { useStore } from '../store'
import {
  exportAnnualCsv, exportCompareCsv, exportGeoJson, exportMonthlyCsv,
  exportSites, exportXml, printReport, readAoiFile, readSitesFile,
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
  const timeIndex = useStore((s) => s.timeIndex)
  const compareIndex = useStore((s) => s.compareIndex)
  const saveAoi = useStore((s) => s.saveAoi)
  const loadSavedAoi = useStore((s) => s.loadSaved)
  const deleteSaved = useStore((s) => s.deleteSaved)
  const renameSaved = useStore((s) => s.renameSaved)
  const updateSaved = useStore((s) => s.updateSaved)
  const importSites = useStore((s) => s.importSites)
  const setAoi = useStore((s) => s.setAoi)
  const setTemplatesOpen = useStore((s) => s.setTemplatesOpen)

  const [menu, setMenu] = useState<'none' | 'export' | 'saved'>('none')
  const [flash, setFlash] = useState<string | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  // Naming a site happens inline rather than through window.prompt: a prompt
  // is blocked outright in some embedded contexts, and it cannot show the user
  // what is about to be saved with the name.
  const [naming, setNaming] = useState(false)
  const [draftName, setDraftName] = useState('')
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const sitesFileRef = useRef<HTMLInputElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)

  const cols = useMemo(
    () => selected.map((id) => data?.series[id]).filter((s): s is Series => !!s),
    [selected, data],
  )

  // A menu that only closes by clicking its own button again is a menu that
  // stays open over the table. Outside click and Escape both dismiss, which is
  // what every other menu on the machine does.
  useEffect(() => {
    if (menu === 'none' && !naming) return
    const onDown = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) { setMenu('none'); setNaming(false) }
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setMenu('none'); setNaming(false); setRenamingId(null) }
    }
    window.addEventListener('mousedown', onDown)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('mousedown', onDown)
      window.removeEventListener('keydown', onKey)
    }
  }, [menu, naming])

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

  const onImportSites = async (file: File | undefined) => {
    if (!file) return
    setUploadError(null)
    try {
      const n = importSites(await readSitesFile(file))
      say(`${n} site${n === 1 ? '' : 's'} added`)
      setMenu('saved')
    } catch (e: any) {
      setUploadError(e?.message ?? 'Could not read that file.')
    }
  }

  const commitName = () => {
    saveAoi(draftName)
    setNaming(false)
    setDraftName('')
    say('Saved — factors and date included')
  }

  return (
    <div className="toolbar" ref={wrapRef}>
      <button className="tb" onClick={() => setTemplatesOpen(true)}
              title="Start from a worked example">Templates</button>

      <button className="tb" onClick={() => fileRef.current?.click()}
              title="Load a boundary from GeoJSON or KML">Upload</button>
      <input
        ref={fileRef} type="file" accept=".geojson,.json,.kml,application/geo+json"
        style={{ display: 'none' }}
        onChange={(e) => { void onUpload(e.target.files?.[0]); e.target.value = '' }}
      />

      <div className="tb-wrap">
        <button className={`tb${naming ? ' is-open' : ''}`} disabled={!aoi}
                onClick={() => { setNaming(!naming); setDraftName('') }}
                title="Keep this shape, its factors and its date for later">Save</button>
        {naming && aoi && (
          <div className="tb-menu tb-naming">
            <label className="tb-naming-label" htmlFor="site-name">Name this site</label>
            <input
              id="site-name" autoFocus className="tb-naming-input"
              value={draftName} placeholder="Untitled site"
              onChange={(e) => setDraftName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') commitName()
                if (e.key === 'Escape') setNaming(false)
              }}
            />
            <div className="tb-naming-note">
              Saves the shape, the {selected.length} chosen factor
              {selected.length === 1 ? '' : 's'} and where the timeline is.
            </div>
            <div className="tb-naming-row">
              <button className="tb tb-small" onClick={commitName}>Save site</button>
              <button className="tb tb-small" onClick={() => setNaming(false)}>Cancel</button>
            </div>
          </div>
        )}
      </div>

      <div className="tb-wrap">
        <button className={`tb${menu === 'saved' ? ' is-open' : ''}`}
                onClick={() => setMenu(menu === 'saved' ? 'none' : 'saved')}
                title="Your saved sites">
          Sites {saved.length > 0 && <span className="tb-count">{saved.length}</span>}
        </button>
        {menu === 'saved' && (
          <div className="tb-menu">
            {saved.length === 0 && (
              <div className="tb-empty">
                Nothing saved yet. Draw an area and press Save — the factors and
                the date come back with it.
              </div>
            )}
            {saved.map((s) => (
              <div key={s.id} className="tb-saved">
                {renamingId === s.id ? (
                  <input
                    autoFocus className="tb-naming-input tb-rename"
                    defaultValue={s.name}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        renameSaved(s.id, (e.target as HTMLInputElement).value)
                        setRenamingId(null)
                      }
                      if (e.key === 'Escape') setRenamingId(null)
                    }}
                    onBlur={(e) => { renameSaved(s.id, e.target.value); setRenamingId(null) }}
                  />
                ) : (
                  <>
                    <button className="tb-saved-load"
                            onClick={() => { loadSavedAoi(s.id); setMenu('none') }}
                            title={s.factors?.length
                              ? `Restores ${s.factors.length} factors and the saved date`
                              : 'Saved before factors were kept — restores the shape only'}>
                      <span className="tb-saved-name">{s.name}</span>
                      <span className="tb-saved-meta">
                        {formatArea(s.area_ha)}
                        {s.factors?.length ? ` · ${s.factors.length} factors` : ''}
                      </span>
                    </button>
                    <button className="tb-saved-act" title="Rename"
                            onClick={() => setRenamingId(s.id)}>✎</button>
                    <button className="tb-saved-act" title="Overwrite with the current view"
                            disabled={!aoi}
                            onClick={() => { updateSaved(s.id); say(`Updated ${s.name}`) }}>⟳</button>
                    <button className="tb-saved-del" title="Delete"
                            onClick={() => deleteSaved(s.id)}>×</button>
                  </>
                )}
              </div>
            ))}
            <div className="tb-menu-sep" />
            <button disabled={!saved.length}
                    onClick={() => { exportSites(saved); say('Sites saved to a file') }}>
              Back up all sites to a file
            </button>
            <button onClick={() => sitesFileRef.current?.click()}>
              Restore sites from a file…
            </button>
          </div>
        )}
        <input
          ref={sitesFileRef} type="file" accept=".json,application/json"
          style={{ display: 'none' }}
          onChange={(e) => { void onImportSites(e.target.files?.[0]); e.target.value = '' }}
        />
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
            {compareIndex !== null && (
              <button onClick={() => { exportCompareCsv(cols, timeIndex, compareIndex); setMenu('none') }}>
                CSV — change between the two pinned dates
              </button>
            )}
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
