import { useState } from 'react'
import { useStore } from '../store'

/**
 * What actually happened here, recorded afterwards.
 *
 * **Capture only.** Nothing aggregates these, nothing scores them, and nothing
 * anywhere in the product is derived from them. The reason to build the
 * storage now is that the information is perishable: a planning decision or a
 * survey result is known once, by one person, and if there is nowhere to put
 * it that day it is gone.
 *
 * Whether it ever becomes a visible feature — "sites like this one usually
 * turn out to…" — is a later decision, and a large one. This does not pre-empt
 * it and deliberately does not display anything that would look like an
 * answer.
 *
 * Free text rather than a dropdown. A fixed list of outcomes would be the
 * product deciding in advance what counts as a result, which is the same
 * mistake as scoring a site.
 *
 * Only shown for a **saved** site: an outcome has to attach to something that
 * still exists tomorrow, and an unsaved drawing does not.
 */
export default function SiteOutcomes() {
  const saved = useStore((s) => s.saved)
  const projectName = useStore((s) => s.projectName)
  const record = useStore((s) => s.recordOutcome)
  const remove = useStore((s) => s.removeOutcome)

  const site = saved.find((s) => s.name === projectName)
  const [note, setNote] = useState('')
  const [when, setWhen] = useState('')
  const [open, setOpen] = useState(false)

  if (!site) {
    return (
      <section className="ovw-section">
        <h2 className="ovw-h">Outcome</h2>
        <p className="out-hint">
          Save this site to record what happens on it later.
        </p>
      </section>
    )
  }

  const outcomes = site.outcomes ?? []

  return (
    <section className="ovw-section">
      <h2 className="ovw-h">Outcome</h2>
      <p className="out-hint">
        If you find out what actually happened here — a planning decision, a
        survey result, what the ground turned out to be — record it against this
        assessment. It is kept with the site and used for nothing else.
      </p>

      {outcomes.length > 0 && (
        <ul className="out-list">
          {outcomes.map((o) => (
            <li className="out-item" key={o.id}>
              <div className="out-item-head">
                <span className="out-date mono">{o.occurredOn || 'undated'}</span>
                <span className="out-scanner mono">{o.scanner}</span>
                <button className="linklike out-remove" type="button"
                        onClick={() => remove(site.id, o.id)}>Remove</button>
              </div>
              <p className="out-note">{o.note}</p>
              {/* What the assessment said at the time, so the outcome can be
                  read against it rather than against a re-run. */}
              <p className="out-context mono">
                Recorded against {o.findingIds.length}{' '}
                {o.findingIds.length === 1 ? 'finding' : 'findings'}
                {o.coverage && ` · ${o.coverage.assessed} of ${o.coverage.relevant} factors assessed`}
              </p>
            </li>
          ))}
        </ul>
      )}

      {open ? (
        <form className="out-form" onSubmit={(e) => {
          e.preventDefault()
          record(site.id, note, when)
          setNote(''); setWhen(''); setOpen(false)
        }}>
          <label className="out-field">
            <span className="out-label">What happened</span>
            <textarea rows={3} value={note} maxLength={2000}
                      onChange={(e) => setNote(e.target.value)}
                      placeholder="Outline permission refused on flood grounds." />
          </label>
          <label className="out-field">
            {/* When it happened, not when it was typed. A decision from March
                recorded in August is a March fact. */}
            <span className="out-label">When it happened</span>
            <input type="date" value={when}
                   onChange={(e) => setWhen(e.target.value)} />
          </label>
          <div className="out-actions">
            <button className="btn btn-sm" type="submit" disabled={!note.trim()}>
              Record
            </button>
            <button className="btn btn-secondary btn-sm" type="button"
                    onClick={() => setOpen(false)}>Cancel</button>
          </div>
        </form>
      ) : (
        <button className="btn btn-secondary btn-sm" type="button"
                onClick={() => setOpen(true)}>
          Record an outcome
        </button>
      )}
    </section>
  )
}
