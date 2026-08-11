import { useRef, useState } from 'react'

import { ApiError, ask } from '../api'
import { useStore } from '../store'
import { formatValue, isReal } from '../lib/format'
import type { AskResponse } from '../types'

/**
 * Ask the report a question.
 *
 * The point of this box is not that it understands English — it understands a
 * fairly narrow slice of it. The point is what happens after it does: the
 * answer is arithmetic on the same series the table and charts are drawn from,
 * so anything it claims can be checked against the row above it.
 *
 * That is why the numbers are shown next to the sentence rather than only
 * inside it. A plain-English answer with no figures is exactly what a model
 * hallucinating would produce, and the difference has to be visible, not
 * promised.
 */

const PLACEHOLDER = 'Has tree cover dropped since 2019?'

export default function Ask() {
  const aoi = useStore((s) => s.aoi)
  const catalog = useStore((s) => s.catalog)
  // The question is answered from the active scanner's factors, so it has to
  // travel with it — see `ask` in api.ts.
  const scannerId = useStore((s) => s.scannerId)
  const [question, setQuestion] = useState('')
  const [result, setResult] = useState<AskResponse | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // One question at a time: a second submission abandons the first rather than
  // racing it, or a slow early answer lands on top of a fast later one.
  const inflight = useRef<AbortController | null>(null)

  const submit = async (text: string) => {
    const q = text.trim()
    if (!q || !aoi) return

    inflight.current?.abort()
    const controller = new AbortController()
    inflight.current = controller

    setPending(true)
    setError(null)
    try {
      setResult(await ask(aoi, q, scannerId, controller.signal))
    } catch (e) {
      if ((e as Error).name === 'AbortError') return
      setError(e instanceof ApiError ? e.message : 'Could not reach the API.')
      setResult(null)
    } finally {
      if (inflight.current === controller) setPending(false)
    }
  }

  if (!aoi) return null

  return (
    <section className="ask">
      <form
        className="ask-form"
        onSubmit={(e) => {
          e.preventDefault()
          void submit(question)
        }}
      >
        <input
          className="ask-input"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={PLACEHOLDER}
          aria-label="Ask a question about this area"
          maxLength={400}
        />
        <button className="btn" type="submit" disabled={pending || !question.trim()}>
          {pending ? 'Reading…' : 'Ask'}
        </button>
      </form>

      {error && <p className="ask-error">{error}</p>}

      {result && !pending && (
        <div className="ask-answer">
          <p className="ask-text">{result.answer}</p>

          {result.findings.length > 0 && (
            <>
              {/* The figures behind the sentence. Present so the answer can be
                  checked against the table rather than taken on trust. */}
              <ul className="ask-evidence">
                {result.findings.map((f) => {
                  // The attribute table's own formatter, so a figure here reads
                  // identically to the same figure one tab away.
                  const factor = catalog?.factors.find((c) => c.id === f.factor_id)
                  const value =
                    f.verdict === 'trend' && f.from_value != null && f.to_value != null
                      ? `${formatValue(f.from_value, factor)} → ${formatValue(f.to_value, factor)}`
                      : f.verdict === 'no-data' ? 'no data'
                        : f.verdict === 'flat' ? 'no clear trend'
                          : ''
                  return (
                  <li
                    key={f.factor_id}
                    className={`ask-fact${f.observed ? '' : ' is-demo'}`}
                  >
                    <span className="ask-fact-label">{f.label}</span>
                    <span className="ask-fact-value">{value}</span>
                    <span className="ask-fact-src">
                      {isReal(f.source) ? f.source.replace('-', ' ') : 'demo data'}
                    </span>
                  </li>
                  )
                })}
              </ul>

              <p className="ask-foot">
                {result.understood.from_year}–{result.understood.to_year}
                {' · computed from the series, not written by a model'}
                {result.phrased_by === 'claude' && ' · wording by Claude'}
              </p>
            </>
          )}

          {result.suggestions && result.suggestions.length > 0 && (
            <ul className="ask-suggestions">
              {result.suggestions.map((s) => (
                <li key={s}>
                  <button
                    type="button"
                    className="ask-suggestion"
                    onClick={() => {
                      setQuestion(s)
                      void submit(s)
                    }}
                  >
                    {s}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}
