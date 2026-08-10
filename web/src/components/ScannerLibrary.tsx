import { useStore } from '../store'
import type { ScannerInfo } from '../types'

/**
 * The scanner library — the first screen.
 *
 * Site Scanner is a platform of specialist scanners, and the first decision is
 * which one you need. That is a product statement, so it gets a screen rather
 * than a dropdown: a picker in a toolbar says "mode", and a library says
 * "these are different tools".
 *
 * ## One source of truth
 *
 * Every scanner here comes from `/api/catalog`'s `scanners` list, which is the
 * backend registry. There is no frontend roadmap array — a second list would
 * drift, and the first symptom would be a card offering a scanner the API
 * refuses. Availability is `implemented`, decided by whether the scanner has
 * any rules.
 *
 * ## Why unavailable scanners are shown at all
 *
 * Because the shape of the product is the message. Six verticals with two
 * live says "platform, early"; two cards says "two tools". What they must not
 * do is pretend — an unavailable scanner has no call to action, cannot be
 * clicked, and says so in words rather than by being greyed.
 *
 * ## Design
 *
 * Field equipment, not dashboard. The index number, the coordinate ticks and
 * the contour field are the visual language of a technical catalogue; they are
 * drawn from the existing token system rather than a new palette, so the
 * library and the workspace are recognisably one product.
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
          <p className="lib-kicker">Site Scanner</p>
          <h1 className="lib-title">Choose your scanner</h1>
          <p className="lib-sub">
            Specialist tools for understanding land, ecology and environmental
            conditions. Each scanner establishes evidence about a place, states
            what that evidence does not settle, and names what a professional
            should investigate next.
          </p>
        </header>

        {available.length > 0 && (
          <section className="lib-section" aria-labelledby="lib-available">
            <h2 className="lib-label" id="lib-available">
              Available<span className="lib-count">{available.length}</span>
            </h2>
            <ul className="lib-grid is-primary">
              {available.map((s, i) => (
                <ScannerCard key={s.id} scanner={s} index={i + 1}
                             onOpen={() => choose(s.id)} />
              ))}
            </ul>
          </section>
        )}

        {upcoming.length > 0 && (
          <section className="lib-section" aria-labelledby="lib-upcoming">
            <h2 className="lib-label" id="lib-upcoming">
              In development<span className="lib-count">{upcoming.length}</span>
            </h2>
            <ul className="lib-grid is-secondary">
              {upcoming.map((s, i) => (
                <ScannerCard key={s.id} scanner={s}
                             index={available.length + i + 1} />
              ))}
            </ul>
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

function ScannerCard({ scanner, index, onOpen }:
                     { scanner: ScannerInfo; index: number; onOpen?: () => void }) {
  const live = Boolean(onOpen)
  const Tag = live ? 'button' : 'div'

  return (
    <li className={`lib-card${live ? '' : ' is-upcoming'}`}>
      <Tag className="lib-card-face"
           {...(live
             ? { onClick: onOpen, type: 'button' as const,
                 'aria-label': `Open the ${scanner.name} scanner` }
             : { 'aria-disabled': true })}>
        {/* Decorative: a contour field, drawn rather than imported so it
            inherits the theme and costs no request. */}
        <Contours />

        <span className="lib-index mono">{String(index).padStart(2, '0')}</span>
        <span className="lib-name">{scanner.name}</span>
        <span className="lib-subject">{scanner.subject}</span>

        <span className="lib-card-foot">
          <span className={`lib-status${live ? ' is-live' : ''}`}>
            {live ? 'Available' : 'In development'}
          </span>
          {live && <span className="lib-cta">Open scanner →</span>}
        </span>
      </Tag>
    </li>
  )
}

/** Contour lines, as decoration. `aria-hidden` and no alt text: it carries no
 *  information a reader needs, and describing it would be noise in a screen
 *  reader. */
function Contours() {
  return (
    <svg className="lib-contours" viewBox="0 0 320 180" aria-hidden
         preserveAspectRatio="none">
      {[0, 1, 2, 3, 4, 5, 6].map((i) => (
        <path key={i} fill="none" stroke="currentColor" strokeWidth="1"
              d={`M-10 ${34 + i * 22} C 60 ${14 + i * 22}, 120 ${58 + i * 22},
                  180 ${30 + i * 22} S 280 ${10 + i * 22}, 330 ${40 + i * 22}`} />
      ))}
    </svg>
  )
}
