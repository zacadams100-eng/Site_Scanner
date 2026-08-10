import { useMemo, useState } from 'react'
import { useStore } from '../store'
import type { Flag, RadarTopic, Unassessed } from '../types'

/**
 * The investigation radar.
 *
 * `Findings` says what the numbers did. This says what that would prompt a
 * professional to check — the question people actually arrive with, which is
 * why it is the first tab.
 *
 * ## The design problem is the empty space, not the flags
 *
 * A list of warnings is easy to render and easy to believe. The hard part is
 * that a reader takes a short list as "we looked at everything and this is
 * what is wrong" — so silence reads as safety when it usually means *we could
 * not look*. Every slope factor in the catalogue is generated today, so a
 * naive version of this screen would show a site with no terrain warnings and
 * no indication that terrain was never assessed.
 *
 * Hence the coverage strip at the top, before any flag: seven topics, each one
 * flagged, clear, or not assessed. It is the first thing on screen because it
 * is what makes the rest of the screen readable. A clear topic is drawn as
 * positively as a flagged one — "checked, nothing found" is a real result and
 * the only thing that distinguishes a screened site from an unscreened one.
 *
 * ## Nothing here is an opinion about the site
 *
 * Flags carry the observed value and the threshold they crossed. Investigations
 * carry the flags that raised them. Neither says whether the site is any good;
 * that judgement belongs to the person whose name goes on the report, and
 * `limits` says so in the panel rather than in a tooltip.
 */

const SEVERITY_LABEL: Record<string, string> = {
  high: 'High', medium: 'Medium', low: 'Low',
}

/** Squares, not traffic lights. BRAND.md rations colour, and a wall of red
 *  discs turns a survey aid into an alarm panel — which is also the wrong
 *  emotional register for "worth a look". */
function Dot({ state }: { state: RadarTopic['state'] }) {
  return <span className={`radar-dot is-${state}`} aria-hidden />
}

export default function Radar() {
  const data = useStore((s) => s.data)
  const toggleFactor = useStore((s) => s.toggleFactor)
  const selected = useStore((s) => s.selected)
  const [openFlag, setOpenFlag] = useState<string | null>(null)

  const radar = data?.radar

  // Only the checks a click can fix, one row each rather than one button per
  // factor: thirteen bare "Add flood_zone2_pct" buttons is a column-name dump,
  // and the useful unit is the *check that would run*, not the layer.
  // The server has already excluded anything that would come back generated —
  // see radar._state_of.
  const addable = useMemo(
    () => (radar?.not_assessed ?? []).filter(
      (u) => u.reason === 'not_selected'
        && u.factors.some((f) => !selected.includes(f))),
    [radar, selected])

  if (!radar) return null

  const { flags, topics, investigations, not_assessed, counts } = radar
  const blocked = not_assessed.filter((u) => u.reason === 'demo_data')

  return (
    <div className="radar">
      {/* Coverage first. What was looked at decides how to read what follows. */}
      <section className="radar-coverage" aria-label="What was assessed">
        <ul className="radar-topics">
          {topics.map((t) => (
            <li key={t.id} className={`radar-topic is-${t.state}`}>
              <Dot state={t.state} />
              <span className="radar-topic-name">{t.name}</span>
              <span className="radar-topic-state">
                {t.state === 'flagged'
                  ? `${t.flags} flag${t.flags === 1 ? '' : 's'}`
                  : t.state === 'clear' ? 'checked · clear' : 'not assessed'}
              </span>
            </li>
          ))}
        </ul>
        <p className="radar-coverage-sum mono">
          {counts.topics_flagged} flagged · {counts.topics_clear} clear ·{' '}
          {counts.topics_not_assessed} not assessed
        </p>
      </section>

      {/* Flags */}
      {flags.length > 0 ? (
        <section aria-label="Investigation flags">
          <h3 className="radar-head">Investigation flags</h3>
          <ul className="flag-list">
            {flags.map((f) => (
              <FlagRow key={f.id} flag={f}
                       open={openFlag === f.id}
                       onToggle={() => setOpenFlag(openFlag === f.id ? null : f.id)} />
            ))}
          </ul>
        </section>
      ) : (
        <p className="radar-none">
          Nothing crossed a threshold in the layers loaded.{' '}
          {counts.topics_not_assessed > 0 && (
            <>That is not the same as a clear site —{' '}
              {counts.topics_not_assessed} of {topics.length} topics were not
              assessed at all.</>
          )}
        </p>
      )}

      {/* Investigations */}
      {investigations.length > 0 && (
        <section aria-label="Recommended next investigations">
          <h3 className="radar-head">Recommended next investigations</h3>
          {(['high', 'medium', 'low'] as const).map((priority) => {
            const group = investigations.filter((i) => i.priority === priority)
            if (!group.length) return null
            return (
              <div key={priority} className="inv-group">
                <h4 className={`inv-priority is-${priority}`}>
                  {SEVERITY_LABEL[priority]} priority
                </h4>
                <ul className="inv-list">
                  {group.map((inv) => (
                    <li key={inv.id} className="inv">
                      <p className="inv-name">{inv.name}</p>
                      <p className="inv-blurb">{inv.blurb}</p>
                      {/* Every recommendation walks back to a number. Without
                          this the list is advice; with it, it is a
                          consequence. */}
                      <ul className="inv-why">
                        {inv.why_text.map((why, i) => (
                          <li key={i}>{why}</li>
                        ))}
                      </ul>
                    </li>
                  ))}
                </ul>
              </div>
            )
          })}
        </section>
      )}

      {/* What could not be checked, and which of those the user can fix. */}
      {(addable.length > 0 || blocked.length > 0) && (
        <section className="radar-gaps" aria-label="Not assessed">
          <h3 className="radar-head">Not assessed</h3>

          {addable.length > 0 && (
            <div className="gap-block">
              <p className="gap-lead">
                These checks need layers this report does not have. Adding one
                runs its check.
              </p>
              <ul className="gap-add">
                {addable.map((u) => (
                  <li key={u.rule}>
                    <span className="gap-add-text">
                      <span className="gap-topic">{u.topic_name}</span>
                      {' '}— {u.asks}.
                    </span>
                    <button className="btn btn-secondary btn-sm"
                            onClick={() => u.factors.forEach(toggleFactor)}
                            title={(u.factor_names ?? u.factors).join(', ')}>
                      Add {u.factors.length > 1
                        ? `${u.factors.length} layers`
                        : (u.factor_names?.[0] ?? u.factors[0])}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {blocked.length > 0 && (
            <div className="gap-block">
              {/* The important half. These cannot be fixed by the user, and
                  saying "unavailable" would let a reader assume it was
                  checked. Naming the check that did not run is the whole
                  point of the section. */}
              <p className="gap-lead">
                These could not be checked at all, because the data behind them
                is generated demo data. No flag can honestly be raised from it.
              </p>
              <ul className="gap-list">
                {blocked.map((u: Unassessed) => (
                  <li key={u.rule}>
                    <span className="gap-topic">{u.topic_name}</span> — {u.asks}.
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      <p className="radar-limits">{radar.limits}</p>
    </div>
  )
}

function FlagRow({ flag, open, onToggle }:
                 { flag: Flag; open: boolean; onToggle: () => void }) {
  const evidence = Object.entries(flag.evidence)
  return (
    <li className={`flag is-${flag.severity}`}>
      <button className="flag-main" onClick={onToggle} aria-expanded={open}>
        <span className={`flag-sev is-${flag.severity}`}>
          {SEVERITY_LABEL[flag.severity]}
        </span>
        <span className="flag-body">
          <span className="flag-topic">{flag.topic_name}</span>
          <span className="flag-text">{flag.text}</span>
        </span>
      </button>

      {open && (
        <div className="flag-detail">
          <table className="flag-evidence">
            <tbody>
              {evidence.map(([k, v]) => (
                <tr key={k}>
                  <th>{k.replace(/_/g, ' ')}</th>
                  <td className="mono">{String(v)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <ul className="flag-prov">
            {flag.provenance.map((p) => (
              <li key={p.factor}>
                {p.name}
                {p.publisher && <> · {p.publisher}</>}
                {/* verified and written are different claims and must not
                    look alike. See radar._provenance_for. */}
                <span className={`prov-status is-${p.status}`}>
                  {p.status === 'verified'
                    ? 'checked against the live service'
                    : p.status === 'written'
                      ? 'built to the documented API, never run live'
                      : 'provenance unknown'}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </li>
  )
}
