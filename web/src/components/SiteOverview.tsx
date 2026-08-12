import { useStore } from '../store'
import ScannerIdentity from './ScannerIdentity'
import FieldChecks from './FieldChecks'
import SignalGaps from './SignalGap'
import SiteOutcomes from './SiteOutcomes'
import {
  assessedText, attentionRows, coverageBar, evidenceRows, gapCauses,
  historicalRows, overlapNote, siteFacts,
} from '../lib/overview'

/**
 * Site overview — the briefing.
 *
 * The screen you can put in front of someone in a meeting without explaining
 * the application first. That is a product goal and also the risk: a summary
 * is the most quotable screen in the tool, and the quotable version of this
 * product is the dishonest one.
 *
 * ## Four sections, in this order, for a reason
 *
 * Evidence → what needs attention → historical change → evidence gaps.
 *
 * The gaps go **last but never optional**. A reader who meets "7 flagged"
 * first has already formed a view of the site, so the coverage line sits
 * *inside* the evidence block rather than after it — the count and its
 * denominator are one statement, not a claim and a caveat.
 *
 * ## What this screen refuses to do
 *
 * **No headline number** (EM7). There is no total, no percentage of health,
 * no traffic light for the site. A summary screen is precisely where "Site
 * health: 72/100" gets proposed, and a score hides its own inputs while the
 * whole argument for this tool is that it shows them.
 *
 * The redesign put a large figure on this screen, and exactly one: **evidence
 * coverage**. It is safe at that size because it rates the assessment rather
 * than the site, and it moves the opposite way to a score — it falls as less
 * is known. The four state counts stay at equal weight beneath it, because the
 * eye reads size as importance and a flag count set large is a verdict with
 * extra steps. `lib/overview.test.ts` pins both properties.
 *
 * **No state of its own** (EM11). Every label and every colour comes from
 * `lib/overview.ts`, which reads the engine's `state`. The specific trap here
 * is direction: an overview wants to draw a falling number red, and a −23%
 * NDVI the engine called `clear` must still render as clear. The arrow comes
 * from the sign, the colour from the state, and they are separate functions so
 * the mistake cannot be made in passing.
 *
 * **No county it cannot source.** The header reads "24.6 ha · 51.2400,
 * -0.5700" rather than "24.6 ha · Surrey", because a drawn shape carries no
 * administrative area and inventing one would put a guess in the line a reader
 * trusts most.
 */
export default function SiteOverview() {
  const data = useStore((s) => s.data)
  const projectName = useStore((s) => s.projectName)
  const setTab = useStore((s) => s.setTab)
  const openEvidence = useStore((s) => s.openEvidence)
  const openInvestigation = useStore((s) => s.openInvestigation)

  if (!data) return null

  const coverage = data.radar?.coverage
  const rows = evidenceRows(coverage)
  const gaps = gapCauses(coverage)
  const overlap = overlapNote(coverage)
  const history = historicalRows(data.historical)
  const attention = attentionRows(data.radar?.investigations)
  const facts = siteFacts(data.area_ha, data.centroid)
  const bar = coverageBar(coverage)

  return (
    <div className="ovw">
      <ScannerIdentity />

      {/* The header of a field assessment: what this is, and the measurements
          that identify it. Labelled rather than run together in a caption. */}
      <header className="ovw-head">
        <span className="field-label">Site</span>
        <h1 className="ovw-title">{projectName || 'Untitled site'}</h1>
        {facts.length > 0 && (
          <dl className="ovw-facts">
            {facts.map((f) => (
              <div className="ovw-fact" key={f.label}>
                <dt className="ovw-fact-label">{f.label}</dt>
                <dd className="ovw-fact-value mono">{f.value}</dd>
              </div>
            ))}
          </dl>
        )}
      </header>

      {/* ---- Evidence coverage ---------------------------------------- */}
      {/* The only large figure on this screen. See the module note: it rates
          the assessment, not the site, and it falls as less is known. */}
      {bar && (
        <section className="ovw-section ovw-cover">
          <h2 className="ovw-h">Evidence coverage</h2>
          <div className="ovw-cover-row">
            <span className="readout readout-lg">{bar.pct}<span className="ovw-pct">%</span></span>
            <div className="ovw-cover-bar" role="img"
                 aria-label={`${bar.assessed} of ${bar.relevant} factors assessed`}>
              <span className="ovw-cover-fill" style={{ width: `${bar.pct}%` }} />
            </div>
          </div>
          <p className="ovw-coverage mono">{assessedText(coverage)}</p>
        </section>
      )}

      {/* The scanner's own checklist, in its own vocabulary. Placed above the
          evidence counts because "which checks ran" is the question that makes
          those counts mean anything. */}
      {data.radar?.topics && (
        <section className="ovw-section">
          <FieldChecks topics={data.radar.topics} />
        </section>
      )}

      {/* ---- Evidence ------------------------------------------------- */}
      <section className="ovw-section">
        <h2 className="ovw-h">Evidence</h2>
        <ul className="ovw-states">
          {rows.map((r) => (
            <li key={r.key} className={`ovw-state is-${r.key}`}>
              <span className="ovw-num mono">{r.count}</span>
              <span className="ovw-state-label">{r.label}</span>
            </li>
          ))}
        </ul>
        {/* Never omitted and never separated from the counts above it: a flag
            count without its denominator misleads in favour of the site that
            was looked at least. Shown here only when the bar above is absent,
            so the statement appears exactly once. */}
        {!bar && <p className="ovw-coverage mono">{assessedText(coverage)}</p>}
        {/* The four counts above are not a partition — `flagged` and
            `informational` are independent factor sets and one factor can be
            in both. This is the screen where a reader will try to add them, so
            when they exceed the total the reason is stated rather than left as
            an apparent arithmetic error. */}
        {overlap && <p className="ovw-overlap">{overlap}</p>}
        {coverage?.note && <p className="ovw-note">{coverage.note}</p>}
      </section>

      {/* ---- What needs attention ------------------------------------- */}
      <section className="ovw-section">
        <h2 className="ovw-h">What needs attention</h2>
        {attention.length === 0 ? (
          // Not "nothing to worry about". With most of the catalogue still
          // generated, an empty list far more often means nothing could be
          // checked than that nothing is wrong.
          <p className="ovw-empty">
            No investigation was prompted by the evidence that could be read.
            That is not the same as nothing being found — see the gaps below.
          </p>
        ) : (
          <>
            <p className="ovw-count">
              {attention.length} investigation{attention.length === 1 ? '' : 's'} prompted
            </p>
            <ul className="ovw-attention">
              {attention.map((inv) => (
                <li key={inv.id} className={`ovw-inv is-${inv.priority}`}>
                  <span className={`ovw-pri is-${inv.priority}`}>{inv.priority}</span>
                  <div className="ovw-inv-body">
                    <button className="ovw-inv-name"
                            onClick={() => openInvestigation(inv.id)}>
                      {inv.name}
                    </button>
                    {/* Traceable, per EM8/EM9: a recommendation that does not
                        name what raised it is advice, and this product does
                        not give advice. */}
                    <span className="ovw-inv-why mono">
                      from {inv.why.length} finding{inv.why.length === 1 ? '' : 's'}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
            <button className="ovw-link" onClick={() => setTab('radar')}>
              See the full radar →
            </button>
          </>
        )}
      </section>

      {/* ---- Historical change ---------------------------------------- */}
      {history.length > 0 && (
        <section className="ovw-section">
          <h2 className="ovw-h">Historical change</h2>
          <ul className="ovw-hist">
            {history.map((h) => {
              // The factor behind the row, so the explorer opens on the thing
              // the reader was already looking at rather than on a list.
              const factor = data.historical?.find((e) => e.id === h.id)?.factor
              return (
                <li key={h.id} className={`ovw-hist-row ${h.stateClass}`}>
                  <button className="ovw-hist-main"
                          disabled={!factor}
                          onClick={() => factor && openEvidence(factor)}>
                    <span className="ovw-hist-name">{h.name}</span>
                    <span className="ovw-hist-change mono">
                      {h.arrow && <span className="ovw-arrow">{h.arrow}</span>}
                      {h.change}
                    </span>
                    <span className="ovw-hist-state">{h.stateLabel}</span>
                  </button>
                </li>
              )
            })}
          </ul>
          <button className="ovw-link" onClick={() => setTab('radar')}>
            Explore the historical record →
          </button>
        </section>
      )}

      <SiteOutcomes />

      {/* Every check that could not run, as a capability note rather than a
          greyed-out row. See SignalGap.tsx — this is the component the
          product's credibility rests on. */}
      {data.radar?.topics && (
        <section className="ovw-section">
          <SignalGaps topics={data.radar.topics} />
        </section>
      )}

      {/* ---- Evidence gaps -------------------------------------------- */}
      <section className="ovw-section ovw-gaps">
        <h2 className="ovw-h">Evidence gaps</h2>
        <p className="ovw-count">
          {coverage?.not_assessed ?? 0} factors could not be assessed
        </p>
        {/* The split is the section. One is a click; the other is a wall, and
            showing them as one number makes a fixable gap and a permanent one
            look like the same problem. */}
        <ul className="ovw-gap-causes">
          {gaps.map((g) => (
            <li key={g.key} className={`ovw-gap is-${g.key}`}>
              <span className="mono">{g.count}</span> {g.text}
            </li>
          ))}
        </ul>
        <button className="ovw-link" onClick={() => setTab('sources')}>
          View the assessment log →
        </button>
      </section>

      {/* The sentence the whole product rests on, at the foot of the screen
          most likely to be quoted out of context. */}
      {data.radar?.principle && (
        <p className="ovw-principle">{data.radar.principle}</p>
      )}
    </div>
  )
}
