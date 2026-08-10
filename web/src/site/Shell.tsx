import { useState, type ReactNode } from 'react'
import { Link, NavLink } from 'react-router-dom'
import BrandMark from '../components/BrandMark'
import { BreadcrumbSchema, useSEO } from './SEO'
import { PAGES, PRIMARY_CTA, APP_PATH, type PageMeta } from './site'

/**
 * The public website's frame.
 *
 * Deliberately separate from the application shell. The marketing site
 * explains what a scanner does; the application performs the analysis, and
 * merging their chrome would make the boundary between "reading about it" and
 * "using it" invisible — which is the specific confusion this structure
 * exists to prevent.
 *
 * One primary call to action, everywhere: **Request a site scan**. A page with
 * three competing buttons has no primary action, and the header, the footer
 * and every page end agree on this one.
 */
export default function Shell({ page, children }:
                              { page: PageMeta; children: ReactNode }) {
  useSEO(page)
  const [navOpen, setNavOpen] = useState(false)

  return (
    <div className="mk">
      <BreadcrumbSchema page={page} />
      <a className="mk-skip" href="#main">Skip to content</a>

      <header className="mk-top">
        <div className="mk-top-inner">
          <Link className="mk-brand" to={PAGES.home.path}
                onClick={() => setNavOpen(false)}>
            <BrandMark className="mk-brand-mark" />
            <span className="mk-brand-name"><b>Site</b> Scanner</span>
          </Link>

          {/* Not a hamburger that hides everything: on a phone the nav
              collapses but the conversion action stays visible, because the
              one thing a visitor might want to do should never be two taps
              behind an icon. */}
          <nav className={`mk-nav${navOpen ? ' is-open' : ''}`}
               aria-label="Primary">
            <NavLink to={PAGES.scanners.path} onClick={() => setNavOpen(false)}>Scanners</NavLink>
            <NavLink to={PAGES.about.path} onClick={() => setNavOpen(false)}>About</NavLink>
            <NavLink to={PAGES.caseStudies.path} onClick={() => setNavOpen(false)}>Case studies</NavLink>
            <NavLink to={PAGES.contact.path} onClick={() => setNavOpen(false)}>Contact</NavLink>
          </nav>

          <div className="mk-top-right">
            <Link className="mk-cta" to={PRIMARY_CTA.path}>{PRIMARY_CTA.label}</Link>
            <button className="mk-nav-toggle" aria-expanded={navOpen}
                    aria-label={navOpen ? 'Close menu' : 'Open menu'}
                    onClick={() => setNavOpen(!navOpen)}>
              <span aria-hidden>{navOpen ? '✕' : '☰'}</span>
            </button>
          </div>
        </div>
      </header>

      {page.crumbs.length > 0 && (
        <nav className="mk-crumbs" aria-label="Breadcrumb">
          <div className="mk-crumbs-inner">
            <ol>
              {page.crumbs.map((c) => (
                <li key={c.path}><Link to={c.path}>{c.label}</Link></li>
              ))}
              <li aria-current="page">{page.title.split(' | ')[0]}</li>
            </ol>
          </div>
        </nav>
      )}

      <main id="main" className="mk-main">{children}</main>

      <footer className="mk-foot">
        <div className="mk-foot-inner">
          <div className="mk-foot-brand">
            <BrandMark className="mk-brand-mark" />
            <p className="mk-foot-line">
              A clear result means we checked. An empty result means we could not.
            </p>
          </div>
          <nav className="mk-foot-nav" aria-label="Footer">
            <div>
              <h2>Scanners</h2>
              <Link to={PAGES.land.path}>Land</Link>
              <Link to={PAGES.habitat.path}>Habitat</Link>
              <Link to={PAGES.scanners.path}>All scanners</Link>
            </div>
            <div>
              <h2>Company</h2>
              <Link to={PAGES.about.path}>About</Link>
              <Link to={PAGES.caseStudies.path}>Case studies</Link>
              <Link to={PAGES.contact.path}>Contact</Link>
            </div>
            <div>
              <h2>Use</h2>
              <Link to={PRIMARY_CTA.path}>{PRIMARY_CTA.label}</Link>
              <a href={APP_PATH}>Open the application</a>
              <Link to={PAGES.privacy.path}>Privacy</Link>
            </div>
          </nav>
        </div>
      </footer>

      {/* Sticky on mobile only, and never on the pages where it would be
          noise: the conversion page itself and the thank-you page. Respects
          the safe-area inset so it clears a phone's home indicator. */}
      {page.path !== PRIMARY_CTA.path && page.path !== PAGES.thanks.path && (
        <div className="mk-sticky">
          <Link className="mk-cta mk-cta-block" to={PRIMARY_CTA.path}>
            {PRIMARY_CTA.label}
          </Link>
        </div>
      )}
    </div>
  )
}
