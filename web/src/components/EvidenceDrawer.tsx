import { useEffect, useRef } from 'react'
import { useStore } from '../store'
import {
  evidenceRows, findEntry, humanKey, sections, sourceRows, stateClass,
  stateLabel,
} from '../lib/evidence'
import type { EvidenceEntry, EvidenceFinding } from '../types'

/**
 * The evidence explorer.
 *
 * One question, asked of one factor: **where did this number come from, what
 * exactly did Contour establish, and what did it not establish?**
 *
 * ## Contextual, not a catalogue
 *
 * It opens on a factor, from a flag or a row the reader was already looking
 * at. It is deliberately not a browsable index of 273 factors — that answers
 * "here is our database" when the question is "why is Contour saying this".
 *
 * ## The claim boundary is the feature
 *
 * Every other section here is provenance the radar already had. The pair at
 * the end — what this establishes, what it does not — is what stops a reader
 * completing
 *
 *     measurement → diagnosis
 *
 * when Contour only supports
 *
 *     measurement → investigation
 *
 * Both sentences are composed by the server next to the engine that reached
 * the state (`evidence.py`), not here, so they cannot drift out of step with
 * the rule they describe. This component renders them and never edits them.
 *
 * ## Shape follows state
 *
 * `sections()` decides which blocks appear from the *state*, not from whether
 * a field happens to be populated. An informational reading gets no threshold
 * block at all — an empty one implies a threshold exists and was met, and
 * inventing a threshold is precisely what that state must not do.
 */
export default function EvidenceDrawer() {
  const data = useStore((s) => s.data)
  const factor = useStore((s) => s.evidenceFactor)
  const close = useStore((s) => s.closeEvidence)
  const setTab = useStore((s) => s.setTab)
  const openInvestigation = useStore((s) => s.openInvestigation)
  const panel = useRef<HTMLDivElement>(null)

  const entry = findEntry(data?.evidence, factor)

  // Escape closes, and focus moves in on open. A drawer that traps a keyboard
  // user is worse than no drawer.
  useEffect(() => {
    if (!entry) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close() }
    window.addEventListener('keydown', onKey)
    panel.current?.focus()
    return () => window.removeEventListener('keydown', onKey)
  }, [entry, close])

  if (!entry) return null

  const plan = sections(entry)

  return (
    <div className="ev-scrim" onClick={close}>
      <aside className="ev" role="dialog" aria-modal="true" tabIndex={-1}
             ref={panel} aria-label={`Evidence for ${entry.name}`}
             onClick={(e) => e.stopPropagation()}>
        <div className="ev-top">
          {/* Back to where they came from, named. "Close" would leave a reader
              who arrived from a flag unsure whether they lose their place. */}
          <button className="ev-back" onClick={() => { close(); setTab('radar') }}>
            ← Back to Radar
          </button>
          <button className="icon-btn" onClick={close} aria-label="Close">✕</button>
        </div>

        <header className="ev-head">
          <h2 className="ev-title">{entry.name}</h2>
          <span className={`ev-state ${stateClass(entry)}`}>{stateLabel(entry)}</span>
        </header>

        {/* The findings, each with the rule that reached it. Plural because one
            series can carry two rules — a trend test and a baseline test — and
            showing only the strongest hides half the answer. */}
        {entry.findings.map((f) => (
          <p key={f.id} className="ev-finding">{f.text}</p>
        ))}

        {plan.measurement && entry.findings.map((f) => (
          <Measurement key={f.id} finding={f} showThreshold={plan.threshold} />
        ))}

        {/* ---- Source: four questions, four fields ---------------------- */}
        <section className="ev-section">
          <h3 className="ev-h">Source</h3>
          {entry.source.dataset && (
            <p className="ev-dataset">{entry.source.dataset}</p>
          )}
          <dl className="ev-dl">
            {sourceRows(entry).map(([k, v]) => (
              <div className="ev-row" key={k}>
                <dt>{k}</dt><dd>{v}</dd>
              </div>
            ))}
          </dl>
          {/* A fact about the data, and this project's reading of it, kept
              apart. Merging them would present an opinion as a licence term. */}
          {entry.source.clearance && (
            <p className="ev-clearance">
              Commercial clearance: <strong>{entry.source.clearance}</strong>
              {' — Contour\'s own reading of the licence, not a legal opinion.'}
            </p>
          )}
          {entry.source.attribution && (
            <p className="ev-attribution">{entry.source.attribution}</p>
          )}
          {entry.assessed_at && (
            /* "Assessed 10 Aug 2026" on a factor whose state is *not
               assessed* contradicts the line above it. The timestamp is when
               the report ran either way, so it is the verb that has to
               change — this product spends a great deal of effort keeping
               "assessed" meaning something specific. */
            <p className="ev-when mono">
              {entry.state === 'not_assessed' ? 'Report run ' : 'Assessed '}
              {new Date(entry.assessed_at).toLocaleDateString('en-GB',
                { day: 'numeric', month: 'short', year: 'numeric' })}
            </p>
          )}
        </section>

        {/* ---- Investigation ------------------------------------------- */}
        {plan.investigation && (
          <section className="ev-section">
            <h3 className="ev-h">Investigation</h3>
            {entry.investigations.map((inv) => (
              <div key={inv.id} className="ev-inv">
                <button className="ev-inv-name"
                        onClick={() => openInvestigation(inv.id)}>
                  {inv.name} →
                </button>
                {/* Traceable in both directions: the flag names what it raised,
                    and the investigation names what raised it. */}
                <span className="ev-inv-why mono">
                  Raised by: {inv.why.join(', ') || '—'}
                </span>
              </div>
            ))}
          </section>
        )}

        {/* ---- The claim boundary -------------------------------------- */}
        <section className="ev-claims">
          <div className="ev-claim is-established">
            <h3 className="ev-h">What this establishes</h3>
            {entry.claims.established.map((c, i) => <p key={i}>{c}</p>)}
          </div>
          {/* Never optional, on any path. A boundary that goes missing
              sometimes is worse than none: the reader learns to expect it and
              reads its absence as "nothing to qualify here". */}
          <div className="ev-claim is-not-established">
            <h3 className="ev-h">What this does not establish</h3>
            {entry.claims.not_established.map((c, i) => <p key={i}>{c}</p>)}
          </div>
        </section>
      </aside>
    </div>
  )
}

function Measurement({ finding, showThreshold }:
                     { finding: EvidenceFinding; showThreshold: boolean }) {
  const rows = evidenceRows(finding)
  const meta = finding.rule_meta ?? {}

  return (
    <section className="ev-section">
      {/* Named after the rule that produced it. Two findings on one factor
          rendered two identical "Measurement" headings, which read as a
          repeat rather than as two different tests of the same series. */}
      <h3 className="ev-h">
        {meta.rule ? `Measurement — ${meta.rule}` : 'Measurement'}
      </h3>
      <dl className="ev-dl">
        {rows.map(([k, v]) => (
          <div className="ev-row" key={k}><dt>{k}</dt><dd className="mono">{v}</dd></div>
        ))}
      </dl>

      {showThreshold && (finding.threshold || Object.keys(meta).length > 0) && (
        <>
          <h3 className="ev-h ev-h-sub">Rule</h3>
          <dl className="ev-dl">
            {meta.rule && <div className="ev-row"><dt>Rule</dt><dd>{meta.rule}</dd></div>}
            <div className="ev-row">
              <dt>Threshold</dt>
              <dd>{String(meta.threshold_display || finding.threshold)}</dd>
            </div>
            {meta.threshold_type && (
              <div className="ev-row"><dt>Type</dt><dd>{String(meta.threshold_type)}</dd></div>
            )}
            {meta.method_version && (
              <div className="ev-row">
                <dt>Method</dt><dd className="mono">{String(meta.method_version)}</dd>
              </div>
            )}
          </dl>
          {/* In the open, never behind a tooltip: Contour does not present its
              own reporting threshold as an external fact. */}
          {meta.threshold_status && (
            <p className="ev-threshold-note">
              This threshold is {String(meta.threshold_status)}.
            </p>
          )}
        </>
      )}
    </section>
  )
}

export { humanKey }
