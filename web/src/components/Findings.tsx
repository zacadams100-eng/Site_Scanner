import Ask from './Ask'
import { useStore } from '../store'
import { isReal } from '../lib/format'
import type { Insight, Series } from '../types'

/**
 * What the numbers say, in sentences.
 *
 * A report is twelve factors over 180 months. The charts are good but they
 * leave the work of noticing to the user, and the first question anyone has is
 * "is there anything here I should care about?". The server answers it
 * (`insights.py`) and this shows the answer.
 *
 * The design rule that matters: a finding drawn from demo data must be
 * visually distinguishable at a glance, not only readable in the sentence. The
 * sentence already says so — the server puts the caveat in the text itself so
 * no layout can drop it — and this adds a hollow marker and a muted treatment
 * so the eye sorts them before the reader does.
 */

const KIND_LABEL: Record<string, string> = {
  trend: 'Trend',
  anomaly: 'Anomaly',
  step: 'Step change',
  static: 'Designation',
  coverage: 'Coverage',
}

/** The numbers behind a sentence, so it can be checked rather than trusted. */
function evidence(f: Insight): string | null {
  switch (f.kind) {
    case 'trend':
      return [
        f.r2 != null ? `r² ${f.r2.toFixed(2)}` : null,
        f.t != null ? `t ${f.t.toFixed(1)}` : null,
        f.n != null ? `${f.n} observations` : null,
      ].filter(Boolean).join(' · ')
    case 'anomaly':
      return f.z != null ? `z ${f.z.toFixed(1)} against its seasonal norm` : null
    case 'step':
      return f.effect_size != null
        ? `${f.effect_size.toFixed(1)} pooled standard deviations`
        : null
    case 'coverage':
      return f.missing != null && f.total != null
        ? `${f.total - f.missing} of ${f.total} months observed`
        : null
    default:
      return null
  }
}

export default function Findings() {
  const data = useStore((s) => s.data)
  const setTab = useStore((s) => s.setTab)
  const findings = data?.insights ?? []
  const counts = data?.counts

  if (!data) return null

  if (!findings.length) {
    return (
      <div className="findings">
        <Ask />
        <p className="empty-note">
          Nothing stood out in these factors over this window — no significant
          trend, no seasonal anomaly, no step change.
        </p>
        <p className="findings-foot">
          That is a result, not a failure: it means the series are steady. Add
          more factors, or widen the date range, to give it more to look at.
        </p>
      </div>
    )
  }

  return (
    <div className="findings">
      <Ask />
      <VsEngland />
      <ol className="finding-list">
        {findings.map((f, i) => {
          const real = isReal(f.source)
          const note = evidence(f)
          return (
            <li key={`${f.factor}-${f.kind}-${i}`}
                className={`finding${real ? '' : ' is-demo'}`}>
              <span className={`finding-dot${real ? '' : ' is-demo'}`} aria-hidden />
              <div className="finding-body">
                <p className="finding-text">{f.text}</p>
                <p className="finding-meta">
                  <span className="finding-kind">{KIND_LABEL[f.kind] ?? f.kind}</span>
                  {note && <><span className="sep">·</span><span className="mono">{note}</span></>}
                </p>
              </div>
            </li>
          )
        })}
      </ol>

      {counts && (
        <p className="findings-foot">
          {counts.total > counts.shown && (
            <>Showing the {counts.shown} most notable of {counts.total}. </>
          )}
          {counts.from_generated_data > 0 && (
            <>
              {counts.from_generated_data} of these come from demo data and are
              marked as such — they describe generated numbers, not this site.{' '}
            </>
          )}
          Every statement is arithmetic over the series in{' '}
          <button className="linklike" onClick={() => setTab('charts')}>Charts</button>;
          none of it is a prediction.
        </p>
      )}
    </div>
  )
}


/**
 * How this site sits against the rest of England.
 *
 * The single most useful thing that can be done to a number in this product.
 * "Crime density 230" means nothing to a land agent; "busier than four fifths
 * of England" means something in one second, and it is the same figure.
 *
 * Only real columns appear here, and only where a sampled baseline exists —
 * both conditions enforced on the server. A generated value ranked against a
 * real national distribution would produce a percentile whose denominator is
 * sourced and whose numerator is invented, which is the most convincing wrong
 * number this app could show.
 *
 * So the usual state of this block is absent, and that is correct. It appears
 * as the catalogue becomes real, which makes it a quiet running total of how
 * much of this product is grounded.
 */
function VsEngland() {
  const data = useStore((s) => s.data)
  const selected = useStore((s) => s.selected)
  if (!data) return null

  const rows = selected
    .map((id) => data.series[id])
    .filter((s): s is Series => !!s?.baseline)

  if (!rows.length) return null

  // Every row shares the same sample, so the provenance is stated once rather
  // than repeated eight times — but it is stated, because a percentile from 60
  // points and one from 6,000 are different claims.
  const first = rows[0].baseline!

  return (
    <section className="vs-england">
      <h3 className="vs-title">Compared with England</h3>
      <ul className="vs-list">
        {rows.map((s) => (
          <li key={s.factor_id} className="vs-row">
            <span className="vs-name">{s.meta.name}</span>
            <span className="vs-phrase">{s.baseline!.phrase}</span>
            <span className="vs-pct mono" title="percentile among the sampled areas">
              {s.baseline!.percentile}
            </span>
          </li>
        ))}
      </ul>
      <p className="vs-foot">
        Against {first.n} areas sampled across England
        {first.built ? ` in ${first.built.slice(0, 7)}` : ''}. Only factors with
        real data appear here.
      </p>
    </section>
  )
}
