import { useMemo } from 'react'
import { useStore } from '../store'
import { formatRadius } from '../lib/format'

// Shared, so the selector returns the same array every render (a fresh [] loops).
const NO_GROUPS: string[] = []
import type { Finding, Layer } from '../types'

/** A swatch in the layer's own colours, so a row can be matched to the map. */
function Swatch({ layer }: { layer?: Layer }) {
  if (!layer || !layer.on_map) return <span className="swatch swatch-none" />
  const { fill, edge, hatched } = layer.style
  const bg = fill === 'none' || hatched ? 'transparent' : fill
  return (
    <span
      className={`swatch swatch-${layer.geom}${hatched ? ' swatch-hatched' : ''}`}
      style={{ background: bg, borderColor: edge, color: edge }}
    />
  )
}

/**
 * The findings schedule, in the same words as the PDF.
 *
 * "Not assessed" is red and says why, every time. It is never folded into
 * "none found": a query that failed is not a clear result.
 */
export default function Findings() {
  const sheet = useStore((s) => s.sheet)!
  const layers = useStore((s) => s.layers)
  const groups = useStore((s) => s.info?.groups ?? NO_GROUPS)
  const hidden = useStore((s) => s.hidden)
  const toggleHidden = useStore((s) => s.toggleHidden)

  const byId = useMemo(() => new Map(layers.map((l) => [l.id, l])), [layers])
  const byGroup = useMemo(() => {
    const out: Record<string, Finding[]> = {}
    for (const f of sheet.findings) (out[f.group] ??= []).push(f)
    return out
  }, [sheet])

  const c = sheet.counts
  return (
    <div className="findings">
      <div className="sheet-summary">
        <div className="counts">
          <span><b>{c.present}</b> present</span>
          <span><b>{c.none_found}</b> none found</span>
          <span className={c.not_assessed ? 'is-bad' : ''}><b>{c.not_assessed}</b> not assessed</span>
        </div>
        <div className="downloads">
          <a className="tb tb-primary" href={sheet.urls.pdf} target="_blank" rel="noreferrer">PDF sheet</a>
          <a className="tb" href={sheet.urls.gpkg} download>GeoPackage</a>
          <a className="tb" href={sheet.urls.json} download>Record (JSON)</a>
        </div>
        {c.not_assessed > 0 && (
          <p className="sheet-warn">
            Check the layers marked not assessed before this goes to a client.
            Their reasons are below and in the JSON record.
          </p>
        )}
        <p className="sheet-meta">
          1:{sheet.scale.toLocaleString('en-GB')} at A4 · {sheet.basemap ? 'OS basemap' : 'no basemap (set OS_API_KEY)'}
          {sheet.client_ref && <> · {sheet.client_ref}</>}
        </p>
      </div>

      {groups.filter((g) => byGroup[g]).map((g) => (
        <section key={g} className="finding-group">
          <h3 className="group-title">{g}</h3>
          {byGroup[g].map((f) => {
            const layer = byId.get(f.layer)
            const onMap = f.status === 'present' && !!sheet.map[f.layer]
            const off = hidden.includes(f.layer)
            return (
              <div key={f.layer} className={`finding is-${f.status}${f.on_site ? ' is-onsite' : ''}`}>
                <button
                  className={`finding-eye${off ? ' is-off' : ''}`}
                  disabled={!onMap}
                  onClick={() => toggleHidden(f.layer)}
                  title={onMap ? (off ? 'Show on map' : 'Hide on map') : 'Nothing to show on the map'}
                  aria-label={`${off ? 'Show' : 'Hide'} ${f.name}`}
                >
                  <Swatch layer={layer} />
                </button>
                <div className="finding-body">
                  <div className="finding-head">
                    <span className="finding-name">{f.name}</span>
                    <span className="finding-radius">{formatRadius(f.search_m)}</span>
                  </div>
                  <div className="finding-text">{f.summary}</div>
                  {f.error && <div className="finding-error">Reason: {f.error}</div>}
                </div>
              </div>
            )
          })}
        </section>
      ))}

      <p className="fine-print">
        Screening only. Statutory and published datasets, read live from each publisher
        when the sheet was made. Not a records-centre search: protected species records
        and local wildlife sites are not included. Search radii are product defaults,
        not regulatory thresholds. Contains public sector information licensed under the
        Open Government Licence v3.0.
      </p>
    </div>
  )
}
