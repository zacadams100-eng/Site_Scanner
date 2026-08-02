import type { Factor, Series } from '../types'
import { formatValue } from './format'

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

export function exportAnnualCsv(cols: Series[], area_ha: number): void {
  const header = ['Year', ...cols.map((c) => `${c.meta.name}${c.unit ? ` (${c.unit})` : ''}`)]
  const lines = [
    `# Site Scanner export — ${new Date().toISOString().slice(0, 10)}`,
    `# Area: ${area_ha.toFixed(1)} ha`,
    `# Sources: ${[...new Set(cols.map((c) => c.meta.base_meta.name))].join('; ')}`,
    header.map(esc).join(','),
  ]
  const years = cols[0]?.annual.map((r) => r.year) ?? []
  for (const y of years) {
    const row = [String(y)]
    for (const c of cols) {
      const r = c.annual.find((a) => a.year === y)
      row.push(r?.value === null || r?.value === undefined ? '' : String(r.value))
    }
    lines.push(row.map(esc).join(','))
  }
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

/** GeoJSON with the annual series folded into the feature's properties, so the
 *  shape and its numbers travel together into QGIS. */
export function exportGeoJson(aoi: GeoJSON.Polygon, cols: Series[], area_ha: number): void {
  const props: Record<string, unknown> = {
    name: 'Site Scanner AOI',
    area_ha: Number(area_ha.toFixed(2)),
    exported: new Date().toISOString(),
  }
  for (const c of cols) {
    props[c.factor_id] = Object.fromEntries(
      c.annual.map((r) => [r.year, r.value]),
    )
    props[`${c.factor_id}__meta`] = {
      name: c.meta.name,
      unit: c.unit,
      source: c.meta.base_meta.name,
      licence: c.meta.base_meta.licence,
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
    cols.map((c) => cell(`${c.meta.name} (${c.unit})`)).join('') + '</Row>')
  for (const r0 of cols[0]?.annual ?? []) {
    const cells = [cell(r0.year, 'Number')]
    for (const c of cols) {
      const r = c.annual.find((a) => a.year === r0.year)
      cells.push(r?.value === null || r?.value === undefined
        ? cell('')
        : cell(r.value, typeof r.value === 'number' ? 'Number' : 'String'))
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
  const rows = (cols[0]?.annual ?? []).map((r0) => {
    const cells = cols.map((c) => {
      const r = c.annual.find((a) => a.year === r0.year)
      return `<td>${formatValue(r?.value ?? null, c.meta as Factor)}</td>`
    }).join('')
    return `<tr><th>${r0.year}</th>${cells}</tr>`
  }).join('')

  w.document.write(`<!doctype html><meta charset="utf-8">
<title>Site Scanner report</title>
<style>
 body{font:12px/1.5 -apple-system,system-ui,sans-serif;margin:32px;color:#111}
 h1{font-size:18px;margin:0 0 4px} .sub{color:#666;margin-bottom:20px}
 table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
 th,td{border-bottom:1px solid #ddd;padding:5px 8px;text-align:right}
 th:first-child,td:first-child{text-align:left}
 thead th{border-bottom:2px solid #333;font-size:11px}
 .src{margin-top:24px;font-size:10px;color:#666}
 @media print{body{margin:12mm}}
</style>
<h1>Site Scanner — site report</h1>
<div class="sub">${area_ha.toFixed(1)} ha · centred ${centroid.lat.toFixed(4)}, ${centroid.lng.toFixed(4)}
 · generated ${new Date().toLocaleDateString('en-GB')}</div>
<table><thead><tr><th>Year</th>${cols.map((c) =>
   `<th>${c.meta.name}<br><span style="font-weight:400;color:#888">${c.unit}</span></th>`).join('')}</tr></thead>
<tbody>${rows}</tbody></table>
<div class="src"><strong>Sources.</strong> ${[...new Set(cols.map((c) =>
  `${c.meta.base_meta.name} (${c.meta.base_meta.licence})`))].join(' · ')}</div>`)
  w.document.close()
  w.focus()
  setTimeout(() => w.print(), 350)
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
