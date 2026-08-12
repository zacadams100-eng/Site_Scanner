import { useStore } from '../store'
import BrandMark from './BrandMark'
import type { ScannerInfo } from '../types'
import { voiceFor } from '../lib/scannerVoice'
import {
  STATUS_LABEL, STATUS_NOTE, domainGaps, builtDomains, isOpenable, sections,
  statusOf, tally,
} from '../lib/library'

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
 * Every scanner, every family and every status here comes from `/api/catalog`,
 * which is the backend registry. There is no frontend roadmap array and no
 * grouping table — a second description of the product's shape drifts, and the
 * frontend's copy is the one nobody remembers to update. `lib/library.ts`
 * holds the rules and is tested without rendering; this file decides how a
 * section looks and nothing about what is in it.
 *
 * ## Why the taxonomy is on the screen
 *
 * Eight scanners in a flat grid is a list of tools. Grouped into Foundation,
 * Development, Culture and Economics, it is a company with a direction — and
 * the grouping is not decoration, because it tells a reader where to look for
 * a question this product does not answer yet. Someone who needs heritage
 * finds Heritage under Culture, marked "not built", with the reason. That is
 * more useful than not finding it at all and assuming it is not coming.
 *
 * ## The part that keeps this honest: partial coverage
 *
 * The library previously drew two states, available and not. That is no longer
 * enough and the gap was dangerous: three of the four built scanners cover
 * *part* of their subject. A card reading "Water · available" invites a user
 * to read a clear result as "no water issues", when it means "no flood,
 * surface water or coastal issues — groundwater, drainage and catchment were
 * never asked".
 *
 * So a partial scanner shows both lists on its plate — what it covers, and
 * what it does not — before the user picks it. Finding that out after running
 * an assessment is finding it out too late.
 *
 * ## Design
 *
 * Field equipment catalogue. The index number, the contour field and the
 * technical margin are the language of one; every colour comes from the shared
 * token system, so the library and the workspace are recognisably one product
 * rather than two designs.
 */
export default function ScannerLibrary() {
  const catalog = useStore((s) => s.catalog)
  const choose = useStore((s) => s.chooseScanner)
  const openPortfolio = useStore((s) => s.setPortfolio)

  const groups = sections(catalog)
  const counts = tally(catalog)

  return (
    <div className="lib">
      <div className="lib-inner">
        <header className="lib-head">
          <div className="lib-brand">
            <BrandMark className="lib-brand-mark" />
            <span className="lib-kicker">Site Scanner</span>
          </div>
          <h1 className="lib-title">Evidence infrastructure for land</h1>
          <p className="lib-sub">
            Specialist instruments for reading a real place. Each scanner
            establishes evidence about a site, states what that evidence does
            not settle, and names what a professional should investigate next.
          </p>
          {/* The shape of the platform, in one line of measurement. Counted
              from the registry, so it cannot claim more than exists. */}
          {counts.scanners > 0 && (
            <p className="lib-tally mono">
              {counts.scanners} scanners
              <span className="lib-tally-sep" aria-hidden>·</span>
              {counts.families} families
              <span className="lib-tally-sep" aria-hidden>·</span>
              {counts.openable} you can run today
            </p>
          )}
          {/* The second question, reachable from the first screen. A portfolio
              is not a scanner and does not belong among them, so it is a link
              rather than a ninth plate. */}
          <button className="lib-portfolio-link" type="button"
                  onClick={() => openPortfolio(true)}>
            Or view a portfolio of sites
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none"
                 stroke="currentColor" strokeWidth="2" strokeLinecap="round"
                 strokeLinejoin="round" aria-hidden>
              <path d="M5 12h13M13 6l6 6-6 6" />
            </svg>
          </button>
        </header>

        {groups.map((section) => (
          <section className="lib-family" key={section.family.id}
                   aria-labelledby={`fam-${section.family.id}`}
                   data-openable={section.openable ? 'yes' : 'no'}>
            <div className="lib-family-head">
              <h2 className="lib-family-name" id={`fam-${section.family.id}`}>
                {section.family.name}
                <span className="lib-count mono">{section.scanners.length}</span>
              </h2>
              {section.family.subject && (
                <p className="lib-family-subject">{section.family.subject}</p>
              )}
            </div>

            <ul className="lib-plates">
              {section.scanners.map((s, i) => (
                <ScannerPlate key={s.id} scanner={s} index={i + 1}
                              onOpen={() => choose(s.id)} />
              ))}
            </ul>
          </section>
        ))}

        <footer className="lib-foot">
          <p>
            A clear result means we checked. An empty result means we could not.
          </p>
        </footer>
      </div>
    </div>
  )
}

/**
 * One scanner, as a plate in an instrument case.
 *
 * The same composition whether or not it can be opened, which is a change from
 * the previous version and a deliberate one. Unbuilt scanners used to be a
 * compact roster under a separate heading, on the reasoning that six identical
 * cards with four greyed out reads as "four things are broken". With families
 * that reasoning inverts: a family whose members are all unbuilt is a
 * *direction*, and demoting its entries to a list would hide the platform's
 * shape rather than clarify it.
 *
 * What must never happen is pretending. An unbuilt scanner has no call to
 * action, is not a button, and says in words rather than by being dim that it
 * cannot assess anything.
 */
function ScannerPlate({ scanner, index, onOpen }:
                      { scanner: ScannerInfo; index: number; onOpen: () => void }) {
  const status = statusOf(scanner)
  const open = isOpenable(scanner)
  const gaps = domainGaps(scanner)
  const covers = builtDomains(scanner)
  const voice = voiceFor(scanner.id)

  // Only rendered when the registry supplied them. A zero is a fact; an absent
  // field is a backend that predates the count, and inventing one there would
  // be exactly the fabrication this screen is built to avoid.
  const stats = open ? [
    scanner.rule_count != null ? { label: 'Checks', value: String(scanner.rule_count) } : null,
    scanner.factor_count != null ? { label: 'Factors', value: String(scanner.factor_count) } : null,
    scanner.coverage_name ? { label: 'Coverage', value: scanner.coverage_name } : null,
  ].filter((x): x is { label: string; value: string } => x != null) : []

  const body = (
    <>
      <Contours />
      <span className="lib-plate-index mono">{String(index).padStart(2, '0')}</span>

      <span className="lib-plate-body">
        <span className="lib-plate-inst mono">
          {open ? `Field instrument ${voice.instrument}` : 'Registered · not built'}
          <span className={`lib-badge lib-badge-${status}`}>
            {STATUS_LABEL[status]}
          </span>
        </span>
        <span className="lib-plate-name">{scanner.name}</span>
        {open && <span className="lib-plate-title">{voice.title}</span>}
        <span className="lib-plate-subject">{scanner.subject}</span>
        {open && <span className="lib-plate-question">{voice.question}</span>}

        {/* The honest half of the plate. A partial scanner names what it
            covers and what it does not, here, before the scanner is chosen. */}
        {status === 'partial' && (
          <span className="lib-coverage">
            {covers.length > 0 && (
              <span className="lib-coverage-row">
                <span className="lib-coverage-key mono">Covers</span>
                <span className="lib-coverage-val">
                  {covers.map((d) => d.name).join(' · ')}
                </span>
              </span>
            )}
            {gaps.length > 0 && (
              <span className="lib-coverage-row lib-coverage-gap">
                <span className="lib-coverage-key mono">Not yet</span>
                <span className="lib-coverage-val">
                  {gaps.map((d) => d.name).join(' · ')}
                </span>
              </span>
            )}
          </span>
        )}

        <span className="lib-plate-note">{STATUS_NOTE[status]}</span>

        {/* For an unbuilt scanner the blockers *are* the content. They are
            what makes a declared scanner useful to read: a professional
            learns this question is not answerable here today, and why. */}
        {!open && gaps.length > 0 && (
          <ul className="lib-blockers">
            {gaps.map((d) => (
              <li className="lib-blocker" key={d.id}>
                <span className="lib-blocker-name mono">{d.name}</span>
                <span className="lib-blocker-why">{d.blocked_by}</span>
              </li>
            ))}
          </ul>
        )}
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

      {open && (
        <span className="lib-plate-open">
          Open scanner
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor"
               strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M5 12h13M13 6l6 6-6 6" />
          </svg>
        </span>
      )}
    </>
  )

  return (
    <li className="lib-plate" data-scanner={scanner.id} data-status={status}>
      {open ? (
        <button className="lib-plate-face" type="button" onClick={onOpen}
                aria-label={`Open the ${scanner.name} scanner`}>
          {body}
        </button>
      ) : (
        // Not a disabled button. A disabled control invites clicking and then
        // refuses, which reads as a fault; this is simply not a control, and
        // the words say why.
        <div className="lib-plate-face lib-plate-static">{body}</div>
      )}
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
