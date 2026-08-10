import { useState } from 'react'
import { useStore } from '../store'
import {
  changeText, coverageText, findingClass, findingLabel, orderedEntries,
  periodText, unavailableReason,
} from '../lib/historical'
import type { HistoricalEntry } from '../types'

/**
 * Historical evidence.
 *
 * **Evidence first, visual record second.** The obvious version of this screen
 * is a big satellite timeline with the numbers underneath, and it is the wrong
 * way round: a professional does not need to explore fifteen years of imagery,
 * they need to know what changed and whether it was established well enough to
 * act on. The record is worth having and is not the headline.
 *
 * ## This component decides nothing
 *
 * `EVIDENCE_MODEL.md` EM11. It does not compute a trend, a percentage, a
 * significance, a threshold or a state. Every label comes from
 * `lib/historical.ts`, whose functions read `finding.state` and ignore the
 * numbers entirely — proven by a test that feeds them a −45% change with a
 * `clear` state and asserts they render "checked · clear". Noticing that −45%
 * is "obviously" a flag is exactly what a UI must not do: the threshold may
 * have changed, the evidence may have been insufficient, the rule may not
 * apply. Only the server knows.
 *
 * ## The threshold block is not a tooltip
 *
 * "Contour reporting threshold · product-defined; not a regulatory or
 * scientific standard" sits in the open beside the finding. It is part of the
 * evidence, and hiding it would be presenting Contour's own interpretation as
 * an external fact — which is the thing this product exists not to do.
 */
export default function HistoricalEvidence() {
  const data = useStore((s) => s.data)
  const [open, setOpen] = useState<string | null>(null)
  const [methodOpen, setMethodOpen] = useState(false)

  const entries = data?.historical
  if (!entries?.length) return null

  const method = data?.methodology
  const assessed = entries.filter((e) => e.finding?.state !== 'not_assessed')

  return (
    <div className="hist">
      <div className="hist-head">
        <h3 className="radar-head">Historical evidence</h3>
        <span className="hist-count mono">
          {assessed.length} of {entries.length} assessed
        </span>
      </div>

      <ul className="hist-list">
        {orderedEntries(entries).map((entry) => (
          <li key={entry.id} className={`hist-row ${findingClass(entry)}`}>
            <button className="hist-main"
                    aria-expanded={open === entry.id}
                    onClick={() => setOpen(open === entry.id ? null : entry.id)}>
              <span className="hist-name">{entry.name}</span>
              <span className="hist-change mono">{changeText(entry)}</span>
              <span className="hist-state">{findingLabel(entry)}</span>
            </button>

            {open === entry.id && <Detail entry={entry} />}
          </li>
        ))}
      </ul>

      {/* Available, not dominant. A professional may want to check how change
          was defined before quoting a figure; everyone else can ignore it. */}
      {method && (
        <div className="hist-method">
          <button className="log-toggle" aria-expanded={methodOpen}
                  onClick={() => setMethodOpen(!methodOpen)}>
            Methodology
            <span className="mono">{method.version}</span>
          </button>
          {methodOpen && (
            <div className="hist-method-body">
              <p className="hist-seasons mono">
                Vegetation read in months {method.seasons.vegetation?.join(', ')}
              </p>
              <ul className="hist-method-rules">
                {method.rules.map((rule, i) => <li key={i}>{rule}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Detail({ entry }: { entry: HistoricalEntry }) {
  const m = entry.metric
  const meta = entry.rule_meta
  const reason = unavailableReason(entry)

  return (
    <div className="hist-detail">
      {/* Not assessed says why, in the server's own words — the three causes
          have three different fixes and rewriting them here would be the UI
          forming its own opinion about what went wrong. */}
      {reason && <p className="hist-reason">{reason}</p>}

      {m && m.baseline !== null && (
        <div className="hist-periods">
          <div>
            <span className="hist-label">Baseline</span>
            <span className="hist-value mono">{m.baseline.toFixed(2)}</span>
            <span className="hist-when mono">{periodText(m.baseline_years)}</span>
          </div>
          <div>
            <span className="hist-label">Recent</span>
            <span className="hist-value mono">{m.recent?.toFixed(2)}</span>
            <span className="hist-when mono">{periodText(m.recent_years)}</span>
          </div>
          <div>
            <span className="hist-label">Change</span>
            <span className="hist-value mono">{changeText(entry)}</span>
            <span className="hist-when mono">{coverageText(entry)}</span>
          </div>
        </div>
      )}

      {/* In the open, never behind a tooltip. Contour does not present its own
          reporting threshold as an external fact. */}
      <dl className="hist-threshold">
        <dt>Threshold</dt><dd>{meta.threshold_display}</dd>
        <dt>Type</dt><dd>{meta.threshold_type}</dd>
        <dt>Status</dt><dd>{meta.threshold_status}</dd>
        <dt>Purpose</dt><dd>{meta.purpose}</dd>
        <dt>Method</dt><dd className="mono">{meta.method_version}</dd>
      </dl>

      {entry.finding?.state === 'flagged' && entry.finding.flag && (
        <p className="hist-finding">{entry.finding.flag.text}</p>
      )}
    </div>
  )
}
