import { useStore } from '../store'
import BrandMark from './BrandMark'
import type { ScannerInfo } from '../types'
import { voiceFor } from '../lib/scannerVoice'

/**
 * The scanner library — the application's front door.
 *
 * Site Scanner is a platform of specialist scanners, and the first decision is
 * which one you need. That is a product statement, so it gets a screen rather
 * than a dropdown: a picker in a toolbar says "mode", and a library says
 * "these are different instruments".
 *
 * ## One source of truth
 *
 * Every scanner here comes from `/api/catalog`'s `scanners` list, which is the
 * backend registry. There is no frontend roadmap array — a second list would
 * drift, and the first symptom would be a card offering a scanner the API
 * refuses. Availability is `implemented`, decided by whether the scanner has
 * any rules. The topic and factor counts are the registry's own, so a scanner
 * moving from declared to built changes this screen with no frontend edit.
 *
 * ## Two compositions, because they are two different statements
 *
 * The available scanners are **plates**: full-width, dark, indexed, with the
 * name set large in condensed caps and the registry's own counts beside it.
 * They are the decision, and they are sized like one.
 *
 * The declared scanners are a **roster** — a compact technical index, not
 * cards. This is deliberate and it is the part that keeps the screen honest.
 * Six identical cards with four greyed out reads as "four things are broken".
 * A list under the heading "In development" reads as a roadmap, which is what
 * it is. What it must never do is pretend: an unavailable scanner has no call
 * to action, cannot be clicked, and says so in words rather than by being
 * dimmed.
 *
 * ## Design
 *
 * Field equipment catalogue. The index number and the contour field are the
 * language of a technical catalogue; every colour comes from the shared token
 * system, so the library and the workspace are recognisably one product rather
 * than two designs.
 */
export default function ScannerLibrary() {
  const catalog = useStore((s) => s.catalog)
  const choose = useStore((s) => s.chooseScanner)
  const scanners = catalog?.scanners ?? []

  const available = scanners.filter((s) => s.implemented)
  const upcoming = scanners.filter((s) => !s.implemented)

  return (
    <div className="lib">
      <div className="lib-inner">
        <header className="lib-head">
          <div className="lib-brand">
            <BrandMark className="lib-brand-mark" />
            <span className="lib-kicker">Site Scanner</span>
          </div>
          <h1 className="lib-title">Choose your scanner</h1>
          <p className="lib-sub">
            Specialist instruments for reading a real place. Each scanner
            establishes evidence about a site, states what that evidence does
            not settle, and names what a professional should investigate next.
          </p>
          {/* The shape of the platform, in one line of measurement. Counted
              from the registry, so it cannot claim more than exists. */}
          {scanners.length > 0 && (
            <p className="lib-tally mono">
              {scanners.length} scanners
              <span className="lib-tally-sep" aria-hidden>·</span>
              {available.length} available
              <span className="lib-tally-sep" aria-hidden>·</span>
              {upcoming.length} in development
            </p>
          )}
        </header>

        {available.length > 0 && (
          <section className="lib-section" aria-labelledby="lib-available">
            <h2 className="lib-label" id="lib-available">
              Available<span className="lib-count mono">{available.length}</span>
            </h2>
            <ul className="lib-plates">
              {available.map((s, i) => (
                <ScannerPlate key={s.id} scanner={s} index={i + 1}
                              onOpen={() => choose(s.id)} />
              ))}
            </ul>
          </section>
        )}

        {upcoming.length > 0 && (
          <section className="lib-section" aria-labelledby="lib-upcoming">
            <h2 className="lib-label" id="lib-upcoming">
              In development<span className="lib-count mono">{upcoming.length}</span>
            </h2>
            {/* A roster, not a grid of disabled cards. See the module note. */}
            <ul className="lib-roster">
              {upcoming.map((s, i) => (
                <li className="lib-roster-row" key={s.id}>
                  <span className="lib-roster-index mono">
                    {String(available.length + i + 1).padStart(2, '0')}
                  </span>
                  <span className="lib-roster-name">{s.name}</span>
                  <span className="lib-roster-subject">{s.subject}</span>
                  <span className="lib-roster-status">Not built</span>
                </li>
              ))}
            </ul>
            <p className="lib-roster-note">
              Declared in the registry so the platform's shape is honest. None
              of them can assess anything yet, and none of them is offered.
            </p>
          </section>
        )}

        <footer className="lib-foot">
          <p>
            A clear result means we checked. An empty result means we could not.
          </p>
        </footer>
      </div>
    </div>
  )
}

/** One available scanner, as a plate. Dark ground, index, name, and the
 *  registry's own counts — a specialist instrument in a case, not a tile. */
function ScannerPlate({ scanner, index, onOpen }:
                      { scanner: ScannerInfo; index: number; onOpen: () => void }) {
  // Only rendered when the registry supplied them. A zero is a fact; an absent
  // field is a backend that predates the count, and inventing one there would
  // be exactly the fabrication this screen is built to avoid.
  const stats = [
    scanner.topic_count != null ? { label: 'Topics', value: String(scanner.topic_count) } : null,
    scanner.factor_count != null ? { label: 'Factors', value: String(scanner.factor_count) } : null,
    scanner.coverage_name ? { label: 'Coverage', value: scanner.coverage_name } : null,
  ].filter((x): x is { label: string; value: string } => x != null)

  // The instrument case: each scanner is its own drawer, with its own
  // vocabulary and its own mark. `data-scanner` drives the palette, exactly as
  // it does in the workspace, so a scanner looks the same in the case as it
  // does in the hand.
  const voice = voiceFor(scanner.id)

  return (
    <li className="lib-plate" data-scanner={scanner.id}>
      <button className="lib-plate-face" type="button" onClick={onOpen}
              aria-label={`Open the ${scanner.name} scanner`}>
        <Contours />

        <span className="lib-plate-index mono">{String(index).padStart(2, '0')}</span>

        <span className="lib-plate-body">
          <span className="lib-plate-inst mono">
            Field instrument {voice.instrument}
          </span>
          <span className="lib-plate-name">{scanner.name}</span>
          <span className="lib-plate-title">{voice.title}</span>
          <span className="lib-plate-subject">{scanner.subject}</span>
          <span className="lib-plate-question">{voice.question}</span>
        </span>

        {stats.length > 0 && (
          <span className="lib-plate-stats">
            {stats.map((s) => (
              <span className="lib-stat" key={s.label}>
                <span className="lib-stat-label">{s.label}</span>
                <span className="lib-stat-value mono">{s.value}</span>
              </span>
            ))}
          </span>
        )}

        <span className="lib-plate-open">
          Open scanner
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor"
               strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M5 12h13M13 6l6 6-6 6" />
          </svg>
        </span>
      </button>
    </li>
  )
}

/** Contour lines, as decoration. `aria-hidden` and no alt text: it carries no
 *  information a reader needs, and describing it would be noise in a screen
 *  reader. */
function Contours() {
  return (
    <svg className="lib-contours" viewBox="0 0 640 200" aria-hidden
         preserveAspectRatio="none">
      {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
        <path key={i} fill="none" stroke="currentColor" strokeWidth="1"
              d={`M-10 ${28 + i * 24} C 120 ${4 + i * 24}, 240 ${62 + i * 24},
                  360 ${26 + i * 24} S 560 ${0 + i * 24}, 660 ${38 + i * 24}`} />
      ))}
    </svg>
  )
}
