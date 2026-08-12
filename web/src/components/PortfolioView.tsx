import { useEffect, useState } from 'react'
import { useStore } from '../store'
import BrandMark from './BrandMark'
import type { PortfolioDocument } from '../types'
import {
  ATTENTION_LABEL, ATTENTION_NOTE, fetchDemoPortfolio, groupRows, lastAssessed,
  radarTiles,
} from '../lib/portfolio'

/**
 * The portfolio — many sites, one view.
 *
 * The product's second question. The first is "tell me about this site", which
 * the workspace answers. This one is "tell me about all of these sites", and it
 * is a different question rather than the same one repeated: what an owner
 * needs is not a thousand reports but the handful of places in them that need a
 * person.
 *
 * ## The ordering decision, which is the whole screen
 *
 * The radar tiles run: sites, **never scanned**, sites with findings,
 * investigations, evidence gaps, awaiting review. The second position is
 * deliberate and it is the same editorial rule the Brief follows — a reader who
 * meets "12 with findings" before "6 never scanned" has already formed a view
 * of the portfolio, and at this scale that view gets applied to every site at
 * once.
 *
 * Rows are grouped into three buckets rather than ranked. A rank is an ordering
 * along one dimension, which is a score with the number hidden. These are three
 * different *kinds* of work, and the row shows the counts that put it in its
 * bucket so a reader can see why it is where it is.
 *
 * ## Demonstration data
 *
 * The only portfolio available today is generated, because there is no store
 * and no real one to show. That makes the labelling the entire safety
 * mechanism, so it appears three times: a banner above the radar, a column on
 * every row, and the `is_demo` field on the row data itself for anything that
 * leaves the screen. `tests/test_portfolio_route.py` holds the backend half.
 *
 * ## What this screen does not do
 *
 * No total, average, percentage, index or score. The one derived value on the
 * page is which bucket a row is in, and that is a partition of values the
 * backend already sent.
 */
export default function PortfolioView() {
  const setPortfolio = useStore((s) => s.setPortfolio)
  const [doc, setDoc] = useState<PortfolioDocument | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const ac = new AbortController()
    fetchDemoPortfolio(ac.signal)
      .then(setDoc)
      .catch((e) => { if (e.name !== 'AbortError') setError(String(e.message || e)) })
    return () => ac.abort()
  }, [])

  const tiles = radarTiles(doc?.radar)
  const groups = groupRows(doc?.sites ?? [])

  return (
    <div className="pf">
      <div className="pf-inner">
        <header className="pf-head">
          <div className="pf-brand">
            <BrandMark className="lib-brand-mark" />
            <span className="lib-kicker">Site Scanner</span>
            <button className="pf-back" type="button" onClick={() => setPortfolio(false)}>
              Back to scanners
            </button>
          </div>
          <h1 className="lib-title">Portfolio</h1>
          <p className="lib-sub">
            Every site on the books, what has been established about each, and
            what has not. A site that has never been scanned is not a clear
            site — it appears here as work outstanding, not as an absence of
            findings.
          </p>
        </header>

        {error && (
          <p className="pf-error">
            The portfolio could not be loaded: {error}. Nothing is shown rather
            than a partial list, because a portfolio missing some of its sites
            would understate every count on this page.
          </p>
        )}

        {/* Above the radar, not below it. A reader who takes in the numbers
            before the label has already read generated figures as measurements,
            and the label arriving afterwards does not undo that. */}
        {doc?.contains_demo_data && (
          <div className="pf-demo" role="note">
            <span className="pf-demo-tag mono">Demonstration data</span>
            <p>{doc.demo_notice}</p>
          </div>
        )}

        {tiles.length > 0 && (
          <section className="pf-radar" aria-label="Portfolio radar">
            {tiles.map((t) => (
              <div className={`pf-tile pf-tile-${t.kind}`} key={t.key}>
                <span className="pf-tile-value mono">{t.value.toLocaleString('en-GB')}</span>
                <span className="pf-tile-label">{t.label}</span>
                {/* On the tile, not in a tooltip. A large figure is the most
                    quotable thing on this screen and it will be quoted without
                    its heading. */}
                <span className="pf-tile-note">{t.note}</span>
              </div>
            ))}
          </section>
        )}

        {doc && doc.radar.sites === 0 && (
          <p className="pf-empty">
            No sites yet. A portfolio starts empty, and an empty portfolio is
            an accurate one — there is nothing here to report and nothing is
            implied about anywhere.
          </p>
        )}

        {groups.map((group) => (
          <section className="pf-group" key={group.attention}
                   aria-labelledby={`pf-${group.attention}`}>
            <div className="pf-group-head">
              <h2 className="lib-family-name" id={`pf-${group.attention}`}>
                {ATTENTION_LABEL[group.attention]}
                <span className="lib-count mono">{group.rows.length}</span>
              </h2>
              <p className="lib-family-subject">{ATTENTION_NOTE[group.attention]}</p>
            </div>

            <div className="pf-table-wrap">
              <table className="pf-table">
                <thead>
                  <tr>
                    <th scope="col">Site</th>
                    <th scope="col">Scanners</th>
                    <th scope="col" className="pf-num">Findings</th>
                    <th scope="col" className="pf-num">Investigations</th>
                    <th scope="col" className="pf-num">Evidence gaps</th>
                    <th scope="col">Review</th>
                    <th scope="col">Last assessed</th>
                  </tr>
                </thead>
                <tbody>
                  {group.rows.map((row) => (
                    <tr key={row.site_id}>
                      <th scope="row" className="pf-site">
                        <span className="pf-site-name">{row.name}</span>
                        <span className="pf-site-meta mono">
                          {row.area_ha != null ? `${row.area_ha.toLocaleString('en-GB')} ha` : 'Area not recorded'}
                          {/* The row carries its own label. A legend at the
                              top of a screen does not survive a row being
                              copied into a document. */}
                          {row.is_demo && <span className="pf-demo-chip">Demo</span>}
                        </span>
                      </th>
                      <td>
                        {row.scanners.length > 0
                          ? row.scanners.join(', ')
                          : <span className="pf-none">None run</span>}
                      </td>
                      <td className="pf-num mono">{row.findings}</td>
                      <td className="pf-num mono">{row.investigations}</td>
                      <td className="pf-num mono">{row.evidence_gaps}</td>
                      <td>
                        {row.awaiting_review
                          ? <span className="pf-await">Not reviewed</span>
                          : <span className="pf-none">—</span>}
                      </td>
                      <td className="mono pf-date">{lastAssessed(row)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ))}

        <footer className="lib-foot">
          <p>
            A clear result means we checked. An empty result means we could not.
          </p>
        </footer>
      </div>
    </div>
  )
}
