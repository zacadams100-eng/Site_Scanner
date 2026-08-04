import type { SavedAoi, SitesFile } from '../store'
import type { Factor, Series } from '../types'
import { coverageHeader, coverageValue, formatValue, isPartialYear } from './format'

/** Explains the months-observed columns wherever a file has room to say it. */
export const PARTIAL_YEAR_NOTE =
  'A year built from fewer than 12 months is not comparable to a full one — ' +
  'the "months observed" columns say how many contributed.'

/**
 * The notices the licences require, deduplicated.
 *
 * Nearly every source here is free to use commercially *on condition* that a
 * specific wording is shown — the Crown copyright line for OGL, "modified
 * Copernicus … data" for Sentinel, Ordnance Survey's own form of words. An
 * exported file is where the obligation is most likely to be forgotten and
 * most likely to matter, because it is the copy that leaves and gets passed
 * on. Several factors usually share one source, hence the dedup.
 */
export function attributionsFor(cols: Series[]): string[] {
  const seen = new Set<string>()
  for (const c of cols) {
    const line = c.meta.base_meta.attribution
    if (line) seen.add(line)
  }
  return [...seen]
}

/**
 * Getting data out.
 *
 * Counter-intuitively, making it easy to leave makes people stay. A tool you
 * cannot extract data from does not get used for real work, and a QGIS user
 * will happily adopt this for the tedious half of their workflow — provided
 * the results come back out in a format they already use.
 */

function download(blob: Blob, filename: string): void {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  a.click()
  // Revoking immediately can cancel the download in Safari.
  setTimeout(() => URL.revokeObjectURL(a.href), 4000)
}

const esc = (v: string) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v)

/** Rows for the annual table, shared by the CSV file and the clipboard so the
 *  two cannot drift — they were separate copies of the same loop, and only one
 *  of them would have been remembered when this changed. */
export function annualRows(cols: Series[]): { header: string[]; rows: string[][] } {
  const header = ['Year']
  for (const c of cols) {
    const name = `${c.meta.name}${c.unit ? ` (${c.unit})` : ''}`
    header.push(name, coverageHeader(c.meta.name))
  }

  const years = cols[0]?.annual.map((r) => r.year) ?? []
  const rows = years.map((y) => {
    const row = [String(y)]
    for (const c of cols) {
      const r = c.annual.find((a) => a.year === y)
      row.push(r?.value === null || r?.value === undefined ? '' : String(r.value))
      row.push(coverageValue(r))
    }
    return row
  })
  return { header, rows }
}

export function exportAnnualCsv(cols: Series[], area_ha: number): void {
  const { header, rows } = annualRows(cols)
  const lines = [
    `# Site Scanner export — ${new Date().toISOString().slice(0, 10)}`,
    `# Area: ${area_ha.toFixed(1)} ha`,
    `# Sources: ${[...new Set(cols.map((c) => c.meta.base_meta.name))].join('; ')}`,
    ...attributionsFor(cols).map((a) => `# ${a}`),
    `# ${PARTIAL_YEAR_NOTE}`,
    header.map(esc).join(','),
    ...rows.map((r) => r.map(esc).join(',')),
  ]
  download(new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' }),
           'site-scanner-annual.csv')
}

export function exportMonthlyCsv(cols: Series[]): void {
  const header = ['Month', ...cols.flatMap((c) => [
    `${c.meta.name}${c.unit ? ` (${c.unit})` : ''}`,
    `${c.meta.name} valid fraction`,
  ])]
  const lines = [header.map(esc).join(',')]
  const steps = cols[0]?.points.map((p) => p.t) ?? []
  steps.forEach((t, i) => {
    const row = [t]
    for (const c of cols) {
      const p = c.points[i]
      row.push(p?.value === null || p?.value === undefined ? '' : String(p.value))
      row.push(String(p?.valid_fraction ?? ''))
    }
    lines.push(row.map(esc).join(','))
  })
  download(new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' }),
           'site-scanner-monthly.csv')
}

/**
 * The two-date change table, as rows.
 *
 * Shared by the CSV file and its tests so the file cannot drift from what the
 * Compare panel shows. Categorical factors report changed/no change rather
 * than a difference, and a gap at either end reports no delta at all — the
 * same rules the panel applies, because a spreadsheet is exactly where an
 * invented zero would be mistaken for a measurement of no change.
 */
export function compareRows(cols: Series[], a: number, b: number): { header: string[]; rows: string[][] } {
  const [lo, hi] = a <= b ? [a, b] : [b, a]
  const stepA = cols[0]?.points[lo]?.t ?? ''
  const stepB = cols[0]?.points[hi]?.t ?? ''
  const header = ['Factor', 'Unit', stepA, stepB, 'Change', 'Change %']

  const rows = cols.map((c) => {
    const va = c.points[lo]?.value ?? null
    const vb = c.points[hi]?.value ?? null
    const base = [c.meta.name, c.unit]
    if (va === null || vb === null) {
      return [...base, va === null ? '' : String(va), vb === null ? '' : String(vb), '', '']
    }
    if (typeof va === 'string' || typeof vb === 'string') {
      return [...base, String(va), String(vb), va === vb ? 'no change' : 'changed', '']
    }
    const d = vb - va
    const pct = va !== 0 ? ((d / Math.abs(va)) * 100).toFixed(1) : ''
    return [...base, String(va), String(vb), String(Number(d.toFixed(6))), pct]
  })
  return { header, rows }
}

export function exportCompareCsv(cols: Series[], a: number, b: number): void {
  const { header, rows } = compareRows(cols, a, b)
  const lines = [header.map(esc).join(','), ...rows.map((r) => r.map(esc).join(','))]
  lines.push('')
  lines.push(esc('Comparing two single months carries their weather with it. '
                 + 'For a trend, read the full monthly series rather than the endpoints.'))
  for (const line of attributionsFor(cols)) lines.push(esc(line))
  download(new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' }),
           `site-scanner-change-${header[2]}-to-${header[3]}.csv`)
}

/** GeoJSON with the annual series folded into the feature's properties, so the
 *  shape and its numbers travel together into QGIS. */
export function exportGeoJson(aoi: GeoJSON.Polygon, cols: Series[], area_ha: number): void {
  const props: Record<string, unknown> = {
    name: 'Site Scanner AOI',
    area_ha: Number(area_ha.toFixed(2)),
    exported: new Date().toISOString(),
    attribution: attributionsFor(cols),
  }
  for (const c of cols) {
    props[c.factor_id] = Object.fromEntries(
      c.annual.map((r) => [r.year, r.value]),
    )
    // Kept as a sibling key rather than folded into the value, so anything
    // already reading `properties[factor_id][year]` keeps working.
    props[`${c.factor_id}__months_observed`] = Object.fromEntries(
      c.annual.map((r) => [r.year, r.value === null ? null : r.months_observed]),
    )
    props[`${c.factor_id}__meta`] = {
      name: c.meta.name,
      unit: c.unit,
      source: c.meta.base_meta.name,
      licence: c.meta.base_meta.licence,
      months_in_full_year: c.annual[0]?.months_total ?? 12,
      note: PARTIAL_YEAR_NOTE,
    }
  }
  const fc: GeoJSON.FeatureCollection = {
    type: 'FeatureCollection',
    features: [{ type: 'Feature', geometry: aoi, properties: props }],
  }
  download(new Blob([JSON.stringify(fc, null, 2)], { type: 'application/geo+json' }),
           'site-scanner-aoi.geojson')
}

/** SpreadsheetML — opens natively in Excel and Google Sheets with real column
 *  types, and needs no dependency to write. */
export function exportXml(cols: Series[]): void {
  const cell = (v: unknown, type = 'String') =>
    `<Cell><Data ss:Type="${type}">${String(v ?? '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')}</Data></Cell>`

  const rows: string[] = []
  rows.push('<Row>' + cell('Year') +
    cols.map((c) => cell(`${c.meta.name} (${c.unit})`) +
                    cell(coverageHeader(c.meta.name))).join('') + '</Row>')
  for (const r0 of cols[0]?.annual ?? []) {
    const cells = [cell(r0.year, 'Number')]
    for (const c of cols) {
      const r = c.annual.find((a) => a.year === r0.year)
      cells.push(r?.value === null || r?.value === undefined
        ? cell('')
        : cell(r.value, typeof r.value === 'number' ? 'Number' : 'String'))
      // Excel is the likeliest place for someone to chart this and see a
      // spike that is really a short year, so the caveat travels as a real
      // numeric column rather than a note nobody reads.
      cells.push(r && r.value !== null
        ? cell(r.months_observed, 'Number') : cell(''))
    }
    rows.push('<Row>' + cells.join('') + '</Row>')
  }

  const xml = `<?xml version="1.0"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
          xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Worksheet ss:Name="Annual"><Table>${rows.join('')}</Table></Worksheet>
 <Worksheet ss:Name="Sources"><Table>
  <Row>${cell('Factor')}${cell('Source')}${cell('Licence')}${cell('Resolution')}</Row>
  ${cols.map((c) => `<Row>${cell(c.meta.name)}${cell(c.meta.base_meta.source)}` +
      `${cell(c.meta.base_meta.licence)}` +
      `${cell(c.meta.base_meta.resolution_m ? c.meta.base_meta.resolution_m + ' m' : 'vector')}</Row>`).join('')}
  <Row></Row>
  <Row>${cell('Required attribution')}</Row>
  ${attributionsFor(cols).map((a) => `<Row>${cell(a)}</Row>`).join('')}
 </Table></Worksheet>
</Workbook>`
  download(new Blob([xml], { type: 'application/vnd.ms-excel' }),
           'site-scanner.xls')
}

/** A one-page printable report. Opens the browser's own print dialog, which
 *  gives PDF export on every platform without shipping a PDF library. */
export function printReport(cols: Series[], area_ha: number,
                            centroid: { lng: number; lat: number }): void {
  const w = window.open('', '_blank')
  if (!w) return
  let anyPartial = false
  const rows = (cols[0]?.annual ?? []).map((r0) => {
    const cells = cols.map((c) => {
      const r = c.annual.find((a) => a.year === r0.year)
      const partial = r ? isPartialYear(r) : false
      if (partial) anyPartial = true
      return `<td>${formatValue(r?.value ?? null, c.meta as Factor)}` +
             `${partial ? `<span class="p" title="${r!.months_observed} of ` +
                          `${r!.months_total} months">*</span>` : ''}</td>`
    }).join('')
    return `<tr><th>${r0.year}</th>${cells}</tr>`
  }).join('')

  // The printed report is the copy that leaves and gets forwarded, so it
  // carries the brand rather than browser defaults: the mark, moss rules,
  // figures in mono. The font stack degrades to whatever the printing machine
  // has — a new window cannot see the app's loaded webfonts.
  w.document.write(`<!doctype html><meta charset="utf-8">
<title>Site Scanner report</title>
<style>
 :root{--moss:#4d6048;--ink:#232323;--slate:#69706a;--rule:#ddd8cf}
 body{font:12px/1.55 'IBM Plex Sans',system-ui,-apple-system,sans-serif;
      margin:30px;color:var(--ink)}
 header{display:flex;align-items:center;gap:12px;padding-bottom:14px;
        border-bottom:2px solid var(--moss);margin-bottom:18px}
 h1{font-size:17px;margin:0;font-weight:600;letter-spacing:.01em}
 .sub{color:var(--slate);font-size:11.5px;margin-top:3px;
      font-family:'IBM Plex Mono',ui-monospace,monospace}
 table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
 th,td{border-bottom:1px solid var(--rule);padding:6px 9px;text-align:right}
 td{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:11.5px}
 th:first-child,td:first-child{text-align:left}
 tbody th{font-weight:600;font-family:'IBM Plex Mono',ui-monospace,monospace}
 thead th{border-bottom:1.5px solid var(--moss);font-size:11px;color:var(--ink)}
 tbody tr:nth-child(odd) td,tbody tr:nth-child(odd) th{background:#faf9f6}
 .src{margin-top:20px;font-size:10px;color:var(--slate);line-height:1.6}
 .p{color:#8a6520;font-weight:600;margin-left:2px}
 @media print{body{margin:12mm}}
</style>
<header>
 <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden>
  <g stroke="#4d6048" stroke-width="2.4" stroke-linecap="round" fill="none">
   <path d="M10 21.5 6 26"/><path d="M22 21.5 26 26"/>
   <path d="M12.5 24.5 11.5 29"/><path d="M19.5 24.5 20.5 29"/></g>
  <g stroke="#4d6048" stroke-width="1.6" stroke-linecap="round" fill="none" opacity=".85">
   <path d="M4 26.6h3.4M9.9 29.4h3.2M18.9 29.4h3.2M24.6 26.6H28"/></g>
  <path d="M16 8c4.6 0 8.2 3.6 8.6 8.6.4 4.6-2.4 8.6-8.6 8.6s-9-4-8.6-8.6C7.8 11.6 11.4 8 16 8Z" fill="#4d6048"/>
  <g stroke="#f8f6f2" stroke-width="1.1" fill="none" opacity=".5">
   <ellipse cx="16" cy="18.2" rx="6" ry="4.2"/><ellipse cx="16" cy="18.2" rx="3.2" ry="2.2"/></g>
  <circle cx="11.4" cy="9.6" r="4.1" fill="#4d6048"/><circle cx="20.6" cy="9.6" r="4.1" fill="#4d6048"/>
  <circle cx="11.4" cy="9.6" r="2.2" fill="#fff"/><circle cx="20.6" cy="9.6" r="2.2" fill="#fff"/>
  <circle cx="11.4" cy="9.6" r="1.1" fill="#4d6048"/><circle cx="20.6" cy="9.6" r="1.1" fill="#4d6048"/>
 </svg>
 <div>
  <h1>Site report</h1>
  <div class="sub">${area_ha.toFixed(1)} ha · ${centroid.lat.toFixed(4)}, ${centroid.lng.toFixed(4)} · EPSG:4326 · ${new Date().toLocaleDateString('en-GB')}</div>
 </div>
</header>
<table><thead><tr><th>Year</th>${cols.map((c) =>
   `<th>${c.meta.name}<br><span style="font-weight:400;color:#69706a;font-family:'IBM Plex Mono',monospace">${c.unit}</span></th>`).join('')}</tr></thead>
<tbody>${rows}</tbody></table>
${anyPartial ? `<div class="src"><strong>* Partial year.</strong> ${PARTIAL_YEAR_NOTE}
 Hover a marked figure on screen for the exact count.</div>` : ''}
<div class="src"><strong>Sources.</strong> ${[...new Set(cols.map((c) =>
  `${c.meta.base_meta.name} (${c.meta.base_meta.licence})`))].join(' · ')}</div>
${attributionsFor(cols).map((a) => `<div class="src">${a}</div>`).join('')}`)
  w.document.close()
  w.focus()
  setTimeout(() => w.print(), 350)
}

/**
 * Saved sites, out to a file and back.
 *
 * Saved sites live in localStorage, which the user can clear by accident, and
 * which does not follow them to another machine or browser. A list of sites
 * someone has curated over a term is worth more than any single report, so it
 * has to be possible to get it out and put it back.
 */
export function sitesFile(sites: SavedAoi[]): SitesFile {
  return {
    format: 'site-scanner.sites',
    version: 1,
    exportedAt: new Date().toISOString(),
    sites,
  }
}

export function exportSites(sites: SavedAoi[]): void {
  const stamp = new Date().toISOString().slice(0, 10)
  download(
    new Blob([JSON.stringify(sitesFile(sites), null, 2)], { type: 'application/json' }),
    `site-scanner-sites-${stamp}.json`,
  )
}

/** Parses an exported sites file, keeping only entries that are actually
 *  usable. A half-readable file should restore what it can and say how much,
 *  rather than being refused whole. */
export function parseSitesFile(text: string): SavedAoi[] {
  let json: any
  try {
    json = JSON.parse(text)
  } catch {
    throw new Error('That file is not a saved-sites file — it is not valid JSON.')
  }
  const list = Array.isArray(json) ? json : json?.sites
  if (!Array.isArray(list)) {
    throw new Error('That file does not contain a list of saved sites.')
  }
  const out: SavedAoi[] = []
  for (const raw of list) {
    const geom = raw?.geometry
    const ring = geom?.coordinates?.[0]
    if (geom?.type !== 'Polygon' || !Array.isArray(ring) || ring.length < 4) continue
    out.push({
      id: String(raw.id ?? `${Date.now()}-${out.length}`),
      name: String(raw.name ?? 'Untitled site').slice(0, 120),
      geometry: { type: 'Polygon', coordinates: [closeRing(ring)] },
      area_ha: Number.isFinite(raw.area_ha) ? Number(raw.area_ha) : 0,
      savedAt: Number.isFinite(raw.savedAt) ? Number(raw.savedAt) : Date.now(),
      ...(Array.isArray(raw.factors) && raw.factors.length
        ? { factors: raw.factors.filter((f: unknown) => typeof f === 'string') }
        : {}),
      ...(Number.isFinite(raw.timeIndex) ? { timeIndex: Number(raw.timeIndex) } : {}),
      ...(raw.compareIndex === null || Number.isFinite(raw.compareIndex)
        ? { compareIndex: raw.compareIndex === null ? null : Number(raw.compareIndex) }
        : {}),
    })
  }
  if (!out.length) throw new Error('No usable sites in that file.')
  return out
}

export async function readSitesFile(file: File): Promise<SavedAoi[]> {
  return parseSitesFile(await file.text())
}

/** Reads a dropped or picked file and returns the first polygon in it.
 *  Most serious users already have their boundary in a file; making them
 *  re-trace it is exactly the friction this product exists to remove. */
export async function readAoiFile(file: File): Promise<GeoJSON.Polygon> {
  const text = await file.text()
  const name = file.name.toLowerCase()

  if (name.endsWith('.kml') || text.trimStart().startsWith('<')) {
    const doc = new DOMParser().parseFromString(text, 'text/xml')
    const coords = doc.querySelector('Polygon coordinates')?.textContent
    if (!coords) throw new Error('No polygon found in that KML file.')
    const ring = coords.trim().split(/\s+/).map((tuple) => {
      const [lng, lat] = tuple.split(',').map(Number)
      return [lng, lat]
    })
    if (ring.length < 3) throw new Error('That KML polygon has too few points.')
    return { type: 'Polygon', coordinates: [closeRing(ring)] }
  }

  let json: any
  try {
    json = JSON.parse(text)
  } catch {
    throw new Error('That file is not GeoJSON or KML. Shapefiles must be ' +
                    'converted first — QGIS exports GeoJSON directly.')
  }

  const geom = findPolygon(json)
  if (!geom) throw new Error('No polygon found in that file.')
  return geom
}

function findPolygon(node: any): GeoJSON.Polygon | null {
  if (!node || typeof node !== 'object') return null
  if (node.type === 'Polygon' && Array.isArray(node.coordinates)) {
    return { type: 'Polygon', coordinates: [closeRing(node.coordinates[0])] }
  }
  if (node.type === 'MultiPolygon' && node.coordinates?.[0]) {
    // Take the largest ring rather than the first — a MultiPolygon of an
    // estate usually leads with an outbuilding.
    const biggest = node.coordinates.reduce((a: any, b: any) =>
      (b[0]?.length ?? 0) > (a[0]?.length ?? 0) ? b : a)
    return { type: 'Polygon', coordinates: [closeRing(biggest[0])] }
  }
  if (node.type === 'Feature') return findPolygon(node.geometry)
  if (node.type === 'FeatureCollection') {
    for (const f of node.features ?? []) {
      const g = findPolygon(f)
      if (g) return g
    }
  }
  if (node.geometry) return findPolygon(node.geometry)
  return null
}

function closeRing(ring: number[][]): number[][] {
  if (!ring?.length) return ring
  const [a, b] = [ring[0], ring[ring.length - 1]]
  return a[0] === b[0] && a[1] === b[1] ? ring : [...ring, ring[0]]
}
