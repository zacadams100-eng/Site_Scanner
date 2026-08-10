import { useEffect, useRef } from 'react'
import { useStore } from '../store'
import {
  allVerified, assessedOn, findEntry, gapLabel, gapSummary, humanKey,
  methodsUsed, priorityClass, priorityLabel, raisedSummary,
} from '../lib/investigation'
import type {
  EvidenceChain, EvidencePack, InvestigationWorkspaceEntry, RaisedBy,
} from '../types'

/**
 * The investigation workspace.
 *
 * Where a finding becomes a professional question. It answers, in the order a
 * professional asks:
 *
 *     Why am I seeing this?   → the findings that raised it, with their rules
 *     What does it establish? → the canonical claim
 *     What does it not?       → the canonical limitation
 *     What should be checked? → the named investigation and its next step
 *     What do I take along?   → sources, endpoints, methods, measurements
 *
 * ## This screen must not know its domain
 *
 * Every word naming a thing in the world arrives as data — the investigation's
 * name and next step from `radar.INVESTIGATIONS`, the rule's name and
 * threshold from `rule_meta`, the claim boundary from `claims.py`. What is
 * written here is only the *structure* of the question, which is the same
 * whether the subject is a parcel, a reserve, a licence block or a stretch of
 * shoreline.
 *
 * `lib/investigation.test.ts` proves it by rendering a coastal investigation
 * assembled from fabricated metadata, and the Python side does the same
 * through `investigation.report`. If either needs a change here to pass, the
 * abstraction has been broken and the diff says which assumption did it.
 *
 * ## It decides nothing
 *
 * Priority is the engine's, findings are in the engine's order, and the claim
 * boundary is taken verbatim (EM11, EM12). The workspace is a view over an
 * interpretation that was reached once.
 */
export default function InvestigationWorkspace() {
  const data = useStore((s) => s.data)
  const id = useStore((s) => s.investigationId)
  const close = useStore((s) => s.closeInvestigation)
  const openEvidence = useStore((s) => s.openEvidence)
  const setTab = useStore((s) => s.setTab)
  // The subject's own name where it has one. Never "site" — the workspace
  // does not know what kind of thing it is looking at.
  const subject = useStore((s) => s.projectName)
  const panel = useRef<HTMLDivElement>(null)

  const entry = findEntry(data?.workspace, id)

  useEffect(() => {
    if (!entry) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close() }
    window.addEventListener('keydown', onKey)
    panel.current?.focus()
    return () => window.removeEventListener('keydown', onKey)
  }, [entry, close])

  if (!entry) return null

  const methods = methodsUsed(entry)

  return (
    <div className="iw-scrim" onClick={close}>
      <aside className="iw" role="dialog" aria-modal="true" tabIndex={-1}
             ref={panel} aria-label={entry.name}
             onClick={(e) => e.stopPropagation()}>
        <div className="iw-top">
          <span className={`iw-pri ${priorityClass(entry)}`}>
            {priorityLabel(entry)}
          </span>
          <button className="icon-btn" onClick={close} aria-label="Close">✕</button>
        </div>

        <header className="iw-head">
          <h2 className="iw-title">{entry.name}</h2>
          {entry.blurb && <p className="iw-blurb">{entry.blurb}</p>}
          <p className="iw-raised mono">
            {raisedSummary(entry)}
            {subject && <> · {subject}</>}
            {assessedOn(entry) && <> · assessed {assessedOn(entry)}</>}
          </p>
        </header>

        {/* ---- Why this appeared --------------------------------------- */}
        <section className="iw-section">
          <h3 className="iw-h">Why this appeared</h3>
          {entry.raised_by.map((r) => <Raised key={r.id} raised={r} />)}
        </section>

        {/* ---- The claim boundary, taken verbatim ---------------------- */}
        <section className="iw-claims">
          <div className="iw-claim is-established">
            <h3 className="iw-h">What this establishes</h3>
            {entry.established.map((c, i) => <p key={i}>{c}</p>)}
          </div>
          <div className="iw-claim is-not-established">
            <h3 className="iw-h">What this does not establish</h3>
            {entry.not_established.map((c, i) => <p key={i}>{c}</p>)}
          </div>
        </section>

        {/* ---- What to check ------------------------------------------- */}
        {entry.next_step && (
          <section className="iw-section">
            <h3 className="iw-h">Suggested professional check</h3>
            <p className="iw-next">{entry.next_step}</p>
          </section>
        )}

        {/* ---- Evidence chain ------------------------------------------ */}
        {entry.chains.length > 0 && (
          <section className="iw-section">
            <h3 className="iw-h">Evidence chain</h3>
            {entry.chains.map((c, i) => <Chain key={i} chain={c} />)}
          </section>
        )}

        {/* ---- Evidence gaps ------------------------------------------- */}
        <section className="iw-section">
          <h3 className="iw-h">Evidence gaps</h3>
          {/* Never omitted. A workspace showing only the evidence *behind* an
              investigation reads as a complete pack, and the reader has no way
              to know what was missing from it. */}
          <p className="iw-gap-summary">{gapSummary(entry)}</p>
          {entry.gaps.map((g) => (
            <div key={g.rule} className={`iw-gap is-${g.reason}`}>
              <p className="iw-gap-asks">{g.asks || g.rule}</p>
              <p className="iw-gap-why mono">{gapLabel(g.reason)}</p>
              {!!g.factors.length && (
                <p className="iw-gap-factors">{g.factors.join(' · ')}</p>
              )}
            </div>
          ))}
        </section>

        {/* ---- What to take along -------------------------------------- */}
        <section className="iw-section">
          <h3 className="iw-h">Evidence to take to the professional</h3>
          {methods.length > 0 && (
            <p className="iw-methods mono">
              Method{methods.length === 1 ? '' : 's'}: {methods.join(', ')}
            </p>
          )}
          {/* A statement about the evidence, never about the subject. */}
          <p className="iw-verified mono">
            {allVerified(entry)
              ? 'Every source behind this was reached live.'
              : 'Not every source behind this was reached live — see below.'}
          </p>
          {entry.evidence.map((p) => (
            <Pack key={p.factor} pack={p} onOpen={() => openEvidence(p.factor)} />
          ))}
        </section>

        {/* Only actions the app can actually keep. Nothing here needs backend
            infrastructure that does not exist. */}
        <footer className="iw-actions">
          <button className="iw-action" onClick={() => { close(); setTab('radar') }}>
            ← Back to Radar
          </button>
          <span className="iw-action-note">
            This investigation and its evidence are included in the site
            investigation brief.
          </span>
        </footer>
      </aside>
    </div>
  )
}

function Chain({ chain }: { chain: EvidenceChain }) {
  return (
    <div className="iw-chain">
      <p className="iw-chain-rule">{chain.rule}</p>
      <ol className="iw-chain-steps">
        {chain.steps.map((s, i) => (
          <li key={i} className={`iw-step is-${s.step}`}>
            <span className="iw-step-label">{s.label}</span>
            <span className="iw-step-value">{s.value}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}

function Raised({ raised }: { raised: RaisedBy }) {
  return (
    <div className={`iw-raised-row is-${raised.severity ?? 'none'}`}>
      <p className="iw-raised-text">{raised.text}</p>
      <dl className="iw-dl">
        <div className="iw-row"><dt>Rule</dt><dd>{raised.rule}</dd></div>
        {raised.threshold && (
          <div className="iw-row"><dt>Threshold</dt><dd>{raised.threshold}</dd></div>
        )}
        {raised.threshold_type && (
          <div className="iw-row"><dt>Type</dt><dd>{raised.threshold_type}</dd></div>
        )}
        {raised.method && (
          <div className="iw-row">
            <dt>Method</dt><dd className="mono">{raised.method}</dd>
          </div>
        )}
      </dl>
      {/* In the open, never behind a tooltip. */}
      {raised.threshold_status && (
        <p className="iw-status">This threshold is {raised.threshold_status}.</p>
      )}
    </div>
  )
}

function Pack({ pack, onOpen }: { pack: EvidencePack; onOpen: () => void }) {
  return (
    <div className="iw-pack">
      <button className="iw-pack-name" onClick={onOpen}>{pack.name} →</button>
      <dl className="iw-dl">
        <div className="iw-row"><dt>Publisher</dt><dd>{pack.publisher || '—'}</dd></div>
        <div className="iw-row"><dt>Endpoint</dt><dd>{pack.endpoint || '—'}</dd></div>
        <div className="iw-row"><dt>Licence</dt><dd>{pack.licence || '—'}</dd></div>
        <div className="iw-row">
          <dt>Assessed</dt>
          <dd className="mono">
            {pack.assessed_at
              ? new Date(pack.assessed_at).toLocaleDateString('en-GB',
                  { day: 'numeric', month: 'short', year: 'numeric' })
              : '—'}
          </dd>
        </div>
      </dl>
      {pack.measurements.map((m, i) => (
        <table className="iw-measure" key={i}>
          {/* Labelled by rule. Three rules' measurements ran together as one
              list with two unlabelled "Threshold" rows, which reads as a
              contradiction rather than as two tests of one series. */}
          <caption className="iw-measure-rule">
            {m.rule_name || humanKey(m.rule)}
          </caption>
          <tbody>
            {Object.entries(m.evidence).map(([k, v]) => (
              <tr key={k}>
                <th>{humanKey(k)}</th><td className="mono">{String(v)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ))}
      {pack.attribution && <p className="iw-attribution">{pack.attribution}</p>}
    </div>
  )
}
