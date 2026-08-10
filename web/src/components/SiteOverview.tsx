import { useStore } from '../store'
import {
  assessedText, attentionRows, evidenceRows, gapCauses, historicalRows,
  locationLine, overlapNote,
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

  return (
    <div className="ovw">
      <header className="ovw-head">
        <h2 className="ovw-title">{projectName || 'Site overview'}</h2>
        <p className="ovw-sub mono">
          {locationLine(data.area_ha, data.centroid)}
        </p>
      </header>

      {/* ---- Evidence ------------------------------------------------- */}
      <section className="ovw-section">
        <h3 className="ovw-h">Evidence</h3>
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
            was looked at least. */}
        <p className="ovw-coverage mono">{assessedText(coverage)}</p>
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
        <h3 className="ovw-h">What needs attention</h3>
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
          <h3 className="ovw-h">Historical change</h3>
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

      {/* ---- Evidence gaps -------------------------------------------- */}
      <section className="ovw-section ovw-gaps">
        <h3 className="ovw-h">Evidence gaps</h3>
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
