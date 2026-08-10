import { useMemo, useState } from 'react'
import { useStore } from '../store'
import type { Coverage, Flag, InfoFinding, RadarTopic, Unassessed } from '../types'

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
  const [openInv, setOpenInv] = useState<string | null>(null)
  const [logOpen, setLogOpen] = useState(false)
  const [openTopic, setOpenTopic] = useState<string | null>(null)
  const [logFilter, setLogFilter] = useState<'all' | 'assessed' | 'not_selected' | 'generated'>('all')

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

  const { flags, topics, investigations, not_assessed, counts,
          informational, coverage, log } = radar
  const blocked = not_assessed.filter((u) => u.reason === 'demo_data')

  return (
    <div className="radar">
      {/* Coverage first. What was looked at decides how to read what follows,
          and the note under it is not optional — a percentage on a screen
          becomes a score in a reader's head within about two seconds. */}
      <section className="radar-cover-head" aria-label="Assessment coverage">
        <div className="cover-top">
          <h3 className="cover-title">Assessment coverage</h3>
          <span className="cover-pct mono">{Math.round(coverage.share * 100)}%</span>
        </div>
        <p className="cover-sub mono">
          {coverage.assessed} / {coverage.relevant} relevant factors assessed
        </p>
        <CoverageBar coverage={coverage} />
        <ul className="cover-legend">
          <li><span className="radar-dot is-flagged" aria-hidden />
            {coverage.flagged} flagged</li>
          <li><span className="radar-dot is-clear" aria-hidden />
            {coverage.clear} clear</li>
          <li><span className="radar-dot is-info" aria-hidden />
            {coverage.informational} informational</li>
          <li><span className="radar-dot is-not_assessed" aria-hidden />
            {coverage.not_assessed} not assessed</li>
        </ul>
        <p className="cover-note">{coverage.note}</p>
      </section>

      <section className="radar-coverage" aria-label="What was assessed">
        <ul className="radar-topics">
          {topics.map((t) => (
            <li key={t.id} className={`radar-topic is-${t.state}`}>
              <button className="radar-topic-row"
                      aria-expanded={openTopic === t.id}
                      onClick={() => setOpenTopic(openTopic === t.id ? null : t.id)}>
                <Dot state={t.state} />
                <span className="radar-topic-name">{t.name}</span>
                {/* The fraction is what stops `clear` being a mood. */}
                {t.coverage.total > 0 && (
                  <span className="radar-topic-cov mono">
                    {t.coverage.assessed}/{t.coverage.total}
                  </span>
                )}
                <span className="radar-topic-state">
                  {t.state === 'flagged'
                    ? `${t.flags} flag${t.flags === 1 ? '' : 's'}`
                    : t.state === 'clear' ? 'checked · clear'
                    /* Some checks ran, others could not. Calling that clear
                       would be the same overstatement as a generated zero. */
                    : t.state === 'partial' ? 'partly checked'
                    : 'not assessed'}
                </span>
              </button>
              {openTopic === t.id && t.detail && (
                <p className="radar-topic-detail">{t.detail}</p>
              )}
            </li>
          ))}
        </ul>
        <p className="radar-coverage-sum mono">
          {counts.topics_flagged} flagged · {counts.topics_clear} clear ·{' '}
          {counts.topics_partial} partial · {counts.topics_not_assessed} not assessed
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

      {/* Measured, and neither good nor bad. Deliberately after the flags and
          set quieter: the radar should still prioritise what needs action. */}
      {informational.length > 0 && (
        <section aria-label="Site facts">
          <h3 className="radar-head">Site facts</h3>
          <ul className="info-list">
            {informational.map((i: InfoFinding) => (
              <li key={i.id} className="info-row">
                <span className="info-text">{i.text}</span>
                <span className="info-topic">{i.topic_name}</span>
              </li>
            ))}
          </ul>
        </section>
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
                      <button className="inv-head"
                              aria-expanded={openInv === inv.id}
                              onClick={() => setOpenInv(openInv === inv.id ? null : inv.id)}>
                        <span className="inv-name">{inv.name}</span>
                        <span className="inv-count mono">
                          {inv.why.length} finding{inv.why.length === 1 ? '' : 's'}
                        </span>
                      </button>
                      <p className="inv-blurb">{inv.blurb}</p>
                      {/* Every recommendation walks back to a number. Without
                          this the list is advice; with it, it is a
                          consequence. */}
                      <ul className="inv-why">
                        {inv.why_text.map((why, i) => (
                          <li key={i}>{why}</li>
                        ))}
                      </ul>
                      {openInv === inv.id && (
                        <div className="inv-more">
                          {inv.next_step && (
                            <p className="inv-step">
                              <span className="inv-step-label">Next step</span>
                              {inv.next_step}
                            </p>
                          )}
                          {!!inv.evidence_factors?.length && (
                            <p className="inv-evidence">
                              <span className="inv-step-label">Evidence</span>
                              {inv.evidence_factors.join(' · ')}
                            </p>
                          )}
                        </div>
                      )}
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

      {/* The audit trail. A professional coming back in three months needs to
          know why the report said what it said, not to trust that it did. */}
      {log.length > 0 && (
        <section className="radar-log" aria-label="Assessment log">
          <button className="log-toggle" aria-expanded={logOpen}
                  onClick={() => setLogOpen(!logOpen)}>
            Assessment log
            <span className="mono">{log.length}</span>
          </button>
          {logOpen && (
            <>
              <p className="log-when mono">
                Assessed {new Date(radar.assessed_at).toLocaleString('en-GB')}
              </p>
              {/* Filters, because at 24 rows this is a list and at 200 it is a
                  haystack. The counts are on the buttons so the shape of the
                  evidence is readable without clicking anything. */}
              <div className="log-filters" role="group" aria-label="Filter the log">
                {([['all', 'All'], ['assessed', 'Assessed'],
                   ['not_selected', 'Not loaded'],
                   ['generated', 'No live source']] as const).map(([id, label]) => {
                  const n = id === 'all' ? log.length
                    : log.filter((r) => r.state === id).length
                  return (
                    <button key={id}
                            className={`log-filter${logFilter === id ? ' is-active' : ''}`}
                            aria-pressed={logFilter === id}
                            disabled={n === 0}
                            onClick={() => setLogFilter(id)}>
                      {label} <span className="mono">{n}</span>
                    </button>
                  )
                })}
              </div>
              <table className="log-table">
                <tbody>
                  {log
                    .filter((r) => logFilter === 'all' || r.state === logFilter)
                    .map((row) => (
                    <tr key={row.factor} className={`log-${row.state}`}>
                      <td>{row.name}</td>
                      <td className="log-state">
                        {row.state === 'assessed' ? 'assessed'
                          : row.state === 'generated' ? 'no live source'
                          : 'not loaded'}
                      </td>
                      <td className="log-who">
                        {row.state === 'assessed'
                          ? <>{row.publisher ?? 'unknown publisher'}
                              {row.status === 'verified' && ' · live'}</>
                          : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </section>
      )}

      {/* The philosophy, in the product rather than in a design document. */}
      <p className="radar-principle">{radar.principle}</p>
      <p className="radar-limits">{radar.limits}</p>
    </div>
  )
}

/**
 * Proportions of what was looked at — deliberately a stacked bar and never a
 * gauge or a dial. A gauge has a good end and a bad end, and this measurement
 * has neither: it says how much we could see, not how the site scored.
 */
function CoverageBar({ coverage }: { coverage: Coverage }) {
  const total = Math.max(1, coverage.relevant)
  const seg = (n: number) => ({ width: `${(n / total) * 100}%` })
  return (
    <div className="cover-bar" role="img"
         aria-label={`${coverage.assessed} of ${coverage.relevant} relevant factors assessed`}>
      <span className="cover-seg is-flagged" style={seg(coverage.flagged)} />
      <span className="cover-seg is-clear" style={seg(coverage.clear)} />
      <span className="cover-seg is-info" style={seg(coverage.informational)} />
      <span className="cover-seg is-gap" style={seg(coverage.not_assessed)} />
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
