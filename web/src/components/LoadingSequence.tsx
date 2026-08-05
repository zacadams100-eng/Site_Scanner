import { useEffect, useState } from 'react'

/**
 * What the app is doing while a report is being built.
 *
 * A single frozen "Reading the site…" for eight seconds reads as broken; the
 * same eight seconds narrated reads as work. The stages below are the real
 * ones, in the order the backend performs them — clipping the geometry,
 * fetching each factor's series (which for a real factor is an upstream call
 * to Earth Engine or a government endpoint), rolling the months into years,
 * then the cell grid the map paints from.
 *
 * The honesty rule that applies everywhere else applies here too: these are
 * not decorative. The timings below are drawn from what the work actually
 * costs, so the message on screen is the step most likely to be running. What
 * it must never do is imply completion — the sequence holds on its last stage
 * rather than pretending to finish, because the response arriving is the only
 * thing that knows when it is done.
 */

interface Stage {
  /** Seconds after the request starts at which this message takes over. */
  at: number
  text: string
}

const STAGES: Stage[] = [
  { at: 0, text: 'Clipping the area…' },
  { at: 0.6, text: 'Fetching observations…' },
  { at: 2.5, text: 'Rolling months into years…' },
  { at: 4.5, text: 'Building the report…' },
  // Past this point something upstream is slow rather than merely working, and
  // saying so is more useful than another verb.
  { at: 9, text: 'Still waiting on the data source…' },
]

export default function LoadingSequence() {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const started = performance.now()
    const id = window.setInterval(() => {
      setElapsed((performance.now() - started) / 1000)
    }, 250)
    return () => window.clearInterval(id)
  }, [])

  // The last stage whose threshold has passed, so a fast response never shows
  // a message for work that had not started.
  const stage = STAGES.reduce((acc, s) => (elapsed >= s.at ? s : acc), STAGES[0])

  return (
    <div className="loading" role="status" aria-live="polite">
      <span className="loading-text">{stage.text}</span>
      {elapsed >= 2.5 && (
        <span className="loading-elapsed">{elapsed.toFixed(0)}s</span>
      )}
    </div>
  )
}
