import { useStore } from '../store'
import { STATE_GLYPH, STATE_LABEL, voiceFor } from '../lib/scannerVoice'
import type { RadarTopic } from '../types'

/**
 * The scanner's topics, as its own checklist.
 *
 * An index card per topic, numbered, stamped with its state. What each
 * instrument calls a check comes from `scannerVoice` — a land surveyor runs a
 * field check, an ecologist makes an observation, a coastal survey takes a
 * sounding — so the same component reads as three different instruments'
 * paperwork.
 *
 * The state glyph carries the meaning: filled, half, hollow. Colour is a
 * second channel rather than the only one, so the list survives greyscale
 * printing and colour-blind reading, which is the same rule the value ramp
 * follows.
 *
 * Coverage is printed on every card. "Clear" without "3 of 3 read" is an
 * adjective; with it, it is a result.
 */
export default function FieldChecks({ topics }: { topics: RadarTopic[] }) {
  const scannerId = useStore((s) => s.scannerId)
  const voice = voiceFor(scannerId)
  if (!topics.length) return null

  return (
    <section className="checks">
      <h2 className="ovw-h">{voice.checkLabelPlural}</h2>
      <ol className="checks-list">
        {topics.map((topic, i) => (
          <li className={`check check-${topic.state}`} key={topic.id}>
            <div className="check-tab mono">
              {voice.checkLabel} {String(i + 1).padStart(2, '0')}
            </div>
            <div className="check-body">
              <h3 className="check-name">{topic.name}</h3>
              <p className="check-detail">{topic.detail}</p>
              <p className="check-cover mono">
                {topic.coverage.assessed} of {topic.coverage.total} read
                {topic.flags > 0 && ` · ${topic.flags} to investigate`}
                {topic.informational > 0 && ` · ${topic.informational} noted`}
              </p>
            </div>
            <div className="check-state">
              <span className="check-glyph" aria-hidden>
                {STATE_GLYPH[topic.state] ?? '○'}
              </span>
              <span className="check-label mono">
                {STATE_LABEL[topic.state] ?? topic.state}
              </span>
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}
