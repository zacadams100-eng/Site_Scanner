import { useEffect, useMemo, useState } from 'react'
import { useStore } from '../store'
import {
  MAX_ROWS, SLOW_AFTER_S, explainWait, selectedFactors, waitingOn,
} from '../lib/loading'

/**
 * What the app is doing while a report is being built.
 *
 * The previous version was one line of grey text, centred in a panel seven
 * hundred pixels tall, changing every few seconds on a timer. Two things were
 * wrong with it, and only the second is about looks.
 *
 * **It looked frozen.** Nothing moved between stage changes, so for two-second
 * stretches the panel was indistinguishable from a page that had died. That is
 * the exact failure its own docstring said it existed to prevent.
 *
 * **It was narrating a guess.** "Rolling months into years…" appeared at 2.5
 * seconds whether or not any months were being rolled — the schedule was
 * derived from what the work usually costs, not from what this request was
 * doing. Everything else in this project refuses to present an estimate as an
 * observation, and a progress message is not exempt just because it is small.
 *
 * So this now shows what the app actually knows, which turns out to be a lot:
 * exactly which layers were asked for, which of them are real, and which
 * upstream each real one has to reach. Naming them does the reassuring that
 * the animation was being asked to do, and it is true.
 *
 * **The temptation to resist** is ticking the rows off one at a time. It would
 * look better than anything here. The app cannot do it honestly: `/api/series`
 * is one POST that returns every factor at once, so there is no moment at
 * which the client learns NDVI has landed and precipitation has not. A row
 * that filled in on a timer would be the same lie as before, wearing a nicer
 * coat. If per-factor progress is ever wanted, the server has to stream it.
 */

interface Stage {
  /** Seconds after the request starts at which this message takes over. */
  at: number
  text: string
}

/**
 * The summary line. Deliberately fewer stages than before, and none of them
 * claims a specific internal step — they describe how long this has been
 * going, which is the one thing the client can observe.
 */
const STAGES: Stage[] = [
  { at: 0, text: 'Reading the site' },
  // Past this point something upstream is slow rather than merely working,
  // and saying so is more useful than another verb.
  { at: SLOW_AFTER_S, text: 'Still waiting on the data source' },
]

interface Props {
  /**
   * `full` when there is nothing on screen yet, `strip` when a report is
   * already up and this is a refetch.
   *
   * The distinction is the point. Adding a fifth factor used to replace the
   * four you were reading with a skeleton — the app taking away the answer it
   * had already given in order to tell you it was working. A refetch keeps the
   * previous report and puts a strip above it instead, which is stale for a
   * few hundred milliseconds and legible throughout.
   */
  variant?: 'full' | 'strip'
}

export default function LoadingSequence({ variant = 'full' }: Props) {
  const selected = useStore((s) => s.selected)
  const catalog = useStore((s) => s.catalog)
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const started = performance.now()
    const id = window.setInterval(() => {
      setElapsed((performance.now() - started) / 1000)
    }, 250)
    return () => window.clearInterval(id)
  }, [])

  const factors = useMemo(
    () => selectedFactors(selected, catalog?.factors), [selected, catalog])

  const stage = STAGES.reduce((acc, s) => (elapsed >= s.at ? s : acc), STAGES[0])

  // Both of these are pure and live in lib/loading.ts, where they are tested.
  // The wording is a claim about what the app is doing, and this project does
  // not let a claim go untested because it is small and grey.
  const explanation = catalog ? explainWait(factors) : null
  const hosts = waitingOn(factors)

  if (variant === 'strip') {
    return (
      <div className="loading-strip" role="status" aria-live="polite">
        <span className="loading-strip-track" aria-hidden />
        <span className="loading-strip-text">
          {elapsed >= SLOW_AFTER_S && hosts.length
            ? `Still waiting on ${hosts.join(' and ')}`
            : 'Updating the report'}
          {/* The figures below are the previous answer, and saying so is the
              whole reason keeping them is honest rather than misleading. */}
          <em> — figures below are from the last query</em>
        </span>
        {elapsed >= 2.5 && (
          <span className="loading-elapsed mono">{elapsed.toFixed(0)}s</span>
        )}
      </div>
    )
  }

  return (
    <div className="loading">
      {/* Only the summary is announced. Putting the live region around the
          whole block would have a screen reader read seven layer names every
          250ms tick. */}
      <div className="loading-head" role="status" aria-live="polite">
        <span className="loading-text">
          {stage.text}
          <span className="loading-dots" aria-hidden>
            <i /><i /><i />
          </span>
        </span>
        {elapsed >= 2.5 && (
          <span className="loading-elapsed mono">{elapsed.toFixed(0)}s</span>
        )}
      </div>

      {explanation && <p className="loading-why">{explanation}</p>}

      {/* A skeleton shaped like the findings that are about to replace it, so
          the panel does not jump when they arrive. */}
      <ul className="loading-rows" aria-hidden>
        {factors.slice(0, MAX_ROWS).map((f, i) => (
          <li key={f.id} className={`loading-row${f.real ? ' is-live' : ''}`}
              // Staggered so the panel reads as several things in flight
              // rather than one bar sliding. Nothing is implied about order:
              // they all start and finish together.
              style={{ animationDelay: `${i * 90}ms` }}>
            <span className="loading-row-name">{f.name}</span>
            {/* A hostname is an identifier and gets mono, per BRAND.md; "demo
                data" is prose and setting it in mono made it read as one. */}
            {f.real ? (
              <span className="loading-row-src mono">
                {f.provenance?.endpoint ?? 'live source'}
              </span>
            ) : (
              <span className="loading-row-src">demo data</span>
            )}
            <span className="loading-bar" />
          </li>
        ))}
        {factors.length > MAX_ROWS && (
          <li className="loading-row loading-row-more">
            and {factors.length - MAX_ROWS} more
          </li>
        )}
      </ul>

      {elapsed >= SLOW_AFTER_S && hosts.length > 0 && (
        <p className="loading-slow">
          Waiting on {hosts.join(' and ')}. Nothing is lost by waiting — the
          shape and the layers stay as they are.
        </p>
      )}
    </div>
  )
}
