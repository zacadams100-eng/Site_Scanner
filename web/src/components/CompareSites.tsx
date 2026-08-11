import { useEffect, useState } from 'react'
import { useStore } from '../store'
import { compareSites } from '../api'
import type { Comparison, CompareTopicCell } from '../types'

/**
 * Evidence comparison.
 *
 * Reads as a briefing, not a leaderboard. `COMPARISON_CONTRACT.md` is the
 * specification and `EVIDENCE_MODEL.md` EM10 is the invariant; this file is
 * where both are either honoured or quietly lost, because a comparison screen
 * is *made of* the affordances that break them.
 *
 * ## Three things this deliberately does not have
 *
 * **No sortable column headers.** A table with sortable totals is a leaderboard
 * whether or not anyone called it one, and sorting by flag count ranks sites by
 * how little was looked at. Topics are cards, and sites keep the order the user
 * chose them in.
 *
 * **No winner colour.** Nothing is green because it scored well. A `clear`
 * topic is drawn exactly as it is in the single-site radar — the same weight as
 * `flagged`, because "checked and found nothing" is a result, not a prize.
 *
 * **No totals row.** The eye reads a bottom row as a score line, and there is
 * no honest number to put there. The per-site summary carries counts *and*
 * coverage, together, because that pairing is the whole point.
 *
 * ## The one thing it does insist on
 *
 * Coverage sits beside every site's counts, at the top, before any topic. A
 * site with zero flags and 43% coverage is not equivalent to a site with two
 * flags and 95% coverage, and a reader who sees the counts first will have
 * decided that it is before they reach any caveat further down.
 */

/** Same vocabulary as the radar's coverage strip. Two components describing
 *  the same four states must not invent two sets of words for them. */
const STATE_LABEL: Record<CompareTopicCell['state'], string> = {
  flagged: 'Flagged',
  clear: 'Checked · clear',
  partial: 'Partly checked',
  not_assessed: 'Not assessed',
}

export default function CompareSites() {
  const saved = useStore((s) => s.saved)
  const scannerId = useStore((s) => s.scannerId)
  const selected = useStore((s) => s.selected)
  const compareIds = useStore((s) => s.compareIds)
  const setComparing = useStore((s) => s.setComparing)

  const [result, setResult] = useState<Comparison | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const sites = compareIds
    .map((id) => saved.find((s) => s.id === id))
    .filter(Boolean) as typeof saved

  useEffect(() => {
    if (sites.length < 2) { setResult(null); return }
    const control = new AbortController()
    setLoading(true)
    setError(null)
    compareSites(
      sites.map((s) => ({ id: s.id, name: s.name, geometry: s.geometry })),
      selected.slice(0, 16),
      scannerId,
      control.signal,
    )
      .then(setResult)
      .catch((e) => {
        if (e?.name !== 'AbortError') setError(e?.message ?? 'Comparison failed')
      })
      .finally(() => setLoading(false))
    return () => control.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [compareIds.join(','), selected.join(','), scannerId])

  if (compareIds.length === 0) return null

  return (
    <div className="cmp">
      <div className="cmp-head">
        <h2 className="cmp-title">Compare sites</h2>
        <button className="btn btn-secondary btn-sm"
                onClick={() => setComparing(false)}>
          Close
        </button>
      </div>

      {/* Before anything else, and never collapsed. A reader who meets the
          counts first has already ranked the sites in their head. */}
      <p className="cmp-frame">
        Comparison shows differences in available evidence. It does not rank
        sites or determine suitability.
      </p>

      <p className="cmp-names mono">{sites.map((s) => s.name).join(' · ')}</p>

      {loading && <p className="cmp-status">Assessing {sites.length} sites…</p>}
      {error && (
        <div className="notice notice-error"><strong>That didn't work.</strong>
          <p>{error}</p></div>
      )}

      {result && (
        <>
          {/* Layer 1 — counts, each with its coverage attached. */}
          <ul className="cmp-summary">
            {result.sites.map((s) => (
              <li key={s.id} className="cmp-site">
                <p className="cmp-site-name">{s.name}</p>
                <p className="cmp-site-cov mono">
                  {Math.round(s.share * 100)}% assessed
                </p>
                <p className="cmp-site-counts">
                  <span><b>{s.flags}</b> flagged</span>
                  <span><b>{s.informational}</b> informational</span>
                  <span><b>{s.not_assessed}</b> not assessed</span>
                </p>
                <p className="cmp-site-sub mono">
                  {s.observed} of {s.relevant} indicators observed
                </p>
              </li>
            ))}
          </ul>

          {/* Fires unprompted. A warning the reader has to go looking for is a
              warning that arrives after the decision. */}
          {result.coverage_warning && (
            <p className="cmp-warning">{result.coverage_warning}</p>
          )}

          {/* Layer 2 — topic cards, not a sortable table. */}
          <h3 className="radar-head">By topic</h3>
          <ul className="cmp-topics">
            {result.topics.map((topic) => (
              <li key={topic.id} className="cmp-topic">
                <div className="cmp-topic-head">
                  <h4 className="cmp-topic-name">{topic.name}</h4>
                  {/* Three sites all at 0/2 are not unevenly evidenced —
                      saying so asserts a difference that is not there. */}
                  {topic.uneven ? (
                    <span className="cmp-uneven">uneven evidence</span>
                  ) : topic.assessed_for_none ? (
                    <span className="cmp-none">not assessed</span>
                  ) : null}
                </div>
                <ul className="cmp-cells">
                  {topic.sites.map((cell, i) => (
                    <li key={cell.id} className={`cmp-cell is-${cell.state}`}>
                      <span className="cmp-cell-site">
                        {result.sites[i]?.name ?? cell.id}
                      </span>
                      <span className="cmp-cell-state">
                        {STATE_LABEL[cell.state]}
                      </span>
                      <span className="cmp-cell-cov mono">
                        {cell.coverage.assessed}/{cell.coverage.total}
                      </span>
                    </li>
                  ))}
                </ul>
                {topic.note && <p className="cmp-note">{topic.note}</p>}
              </li>
            ))}
          </ul>

          {/* Layer 3 — observations, and there is no fourth layer. */}
          {result.differences.length > 0 && (
            <>
              <h3 className="radar-head">Observations</h3>
              <ul className="cmp-diffs">
                {result.differences.map((d, i) => (
                  <li key={i} className={`cmp-diff is-${d.kind}`}>{d.text}</li>
                ))}
              </ul>
            </>
          )}

          <p className="radar-principle">{result.principle}</p>
          <p className="radar-limits">{result.limits}</p>
        </>
      )}
    </div>
  )
}
