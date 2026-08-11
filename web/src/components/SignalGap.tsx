import type { RadarTopic } from '../types'

/**
 * What the instrument could not read, presented as a capability note.
 *
 * This is the component the whole product's credibility rests on. A check that
 * could not run is not a check that passed, and the interface has to make that
 * distinction *interesting* rather than merely correct — a greyed-out row
 * reads as a defect in the software, and this reads as a fact about the
 * instrument.
 *
 * Everything shown comes from the radar payload: the check's own `asks`, the
 * backend's own `reason`, the indicators it needed. Nothing here is written by
 * the frontend about a place, because the frontend knows nothing about places.
 */

/** The backend's reason codes, in the instrument's language.
 *
 *  Only codes the API actually emits. An unmapped reason falls through to the
 *  raw string rather than a guess — a wrong explanation of why something could
 *  not be measured is worse than an unpolished one. */
const REASON: Record<string, { why: string; enable: string }> = {
  demo_data: {
    why: 'This deployment is running on generated data, so nothing may be '
       + 'claimed from it.',
    enable: 'A live connection to the source service.',
  },
  no_source: {
    why: 'No live source is connected for the evidence this check needs.',
    enable: 'An implemented and credentialed source for the indicators below.',
  },
  not_selected: {
    why: 'The evidence this check reads was not among the factors requested.',
    enable: 'Add the indicators below to the report.',
  },
  insufficient: {
    why: 'The source answered, but with too little usable record to compare '
       + 'against.',
    enable: 'A longer or less obstructed observation record for this area.',
  },
  outside_coverage: {
    why: 'This area falls outside the coverage this scanner has established.',
    enable: 'Coverage exercised and verified for this region.',
  },
}

function explain(reason: string | null | undefined) {
  if (!reason) {
    return { why: 'The instrument did not record a reason.', enable: '' }
  }
  return REASON[reason] ?? { why: reason, enable: '' }
}

/**
 * One unread check.
 *
 * Rendered as an instrument limitation card: what was being asked, why no
 * reading was possible, and what would make it possible. The last of those is
 * the part that turns a gap into a roadmap.
 */
export function SignalGapCard({ ask, indicators, reason }:
                              { ask: string; indicators: string[]; reason?: string | null }) {
  const { why, enable } = explain(reason)
  return (
    <li className="gap-card">
      <div className="gap-head">
        <span className="gap-glyph" aria-hidden>○</span>
        <p className="gap-status mono">No signal</p>
      </div>
      <p className="gap-ask">{ask}</p>
      <dl className="gap-detail">
        <dt className="mono">Why</dt>
        <dd>{why}</dd>
        {indicators.length > 0 && (
          <>
            <dt className="mono">Needs</dt>
            <dd className="gap-needs">
              {indicators.map((i) => (
                <span className="gap-chip mono" key={i}>{i}</span>
              ))}
            </dd>
          </>
        )}
        {enable && (
          <>
            <dt className="mono">Would enable it</dt>
            <dd>{enable}</dd>
          </>
        )}
      </dl>
    </li>
  )
}

/**
 * Every unread check across a topic.
 *
 * Grouped by topic rather than listed flat, because "terrain could not be
 * read" is a sentence a user can act on and "eleven checks did not run" is a
 * number they cannot.
 */
export default function SignalGaps({ topics }: { topics: RadarTopic[] }) {
  const unread = topics
    .map((t) => ({ topic: t, checks: t.checks.filter((c) => !c.assessed) }))
    .filter((g) => g.checks.length > 0)

  if (unread.length === 0) return null

  const total = unread.reduce((n, g) => n + g.checks.length, 0)

  return (
    <section className="gaps">
      <div className="gaps-head">
        <h2 className="ovw-h">Signal unavailable</h2>
        <span className="gaps-count mono">{total}</span>
      </div>
      <p className="gaps-note">
        These are limits of the instrument on this deployment, not findings
        about the site. Each states what would enable it.
      </p>
      {unread.map(({ topic, checks }) => (
        <div className="gap-group" key={topic.id}>
          <h3 className="gap-topic mono">{topic.name}</h3>
          <ul className="gap-list">
            {checks.map((c) => (
              <SignalGapCard key={c.rule} ask={c.asks}
                             indicators={c.indicators} reason={c.reason} />
            ))}
          </ul>
        </div>
      ))}
    </section>
  )
}
