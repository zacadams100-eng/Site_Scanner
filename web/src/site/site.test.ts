import { describe, expect, it } from 'vitest'
import { PAGES, PRIMARY_CTA, APP_PATH, absoluteUrl, siteOrigin } from './site'

/**
 * The SEO audit, as a test.
 *
 * The previous website pass could not run these checks because there were no
 * routes. Now there are, and "every title is unique" is the kind of claim that
 * is true on the day it is written and false three pages later — so it is
 * asserted rather than reported.
 */

const pages = Object.values(PAGES)

describe('every public route is described once', () => {
  it('has a unique path', () => {
    const paths = pages.map((p) => p.path)
    expect(new Set(paths).size).toBe(paths.length)
  })

  it('has a unique title', () => {
    const titles = pages.map((p) => p.title)
    expect(new Set(titles).size).toBe(titles.length)
  })

  it('has a unique meta description', () => {
    const d = pages.map((p) => p.description)
    expect(new Set(d).size).toBe(d.length)
  })

  it('titles describe the page and carry the brand', () => {
    for (const p of pages) {
      expect(p.title.length, p.path).toBeGreaterThan(12)
      expect(p.title, p.path).toContain('Site Scanner')
      // No internal or debug terminology reaching a browser tab.
      expect(p.title.toLowerCase(), p.path).not.toMatch(/todo|test|debug|untitled|\bweb\b/)
    }
  })

  it('descriptions say what a reader will find, without stuffing', () => {
    // Length is checked on indexable pages only: the rule exists because a
    // description appears under a search result, and a noindex page has none.
    for (const p of pages.filter((x) => x.indexable)) {
      expect(p.description.length, p.path).toBeGreaterThan(40)
      expect(p.description.length, p.path).toBeLessThan(320)
      // The same phrase five times is keyword stuffing.
      const brand = (p.description.match(/Site Scanner/g) ?? []).length
      expect(brand, p.path).toBeLessThan(3)
    }
  })
})

describe('breadcrumbs', () => {
  it('are absent on the homepage and present below it', () => {
    expect(PAGES.home.crumbs).toEqual([])
    for (const p of pages.filter((x) => x.path !== '/')) {
      expect(p.crumbs.length, p.path).toBeGreaterThan(0)
    }
  })

  it('start at the homepage and only reference real routes', () => {
    const known = new Set(pages.map((p) => p.path))
    for (const p of pages) {
      for (const c of p.crumbs) expect(known.has(c.path), `${p.path} → ${c.path}`).toBe(true)
      if (p.crumbs.length) expect(p.crumbs[0].path).toBe('/')
    }
  })

  it('nest a scanner page under scanners', () => {
    expect(PAGES.land.crumbs.map((c) => c.path)).toEqual(['/', '/scanners'])
    expect(PAGES.habitat.crumbs.map((c) => c.path)).toEqual(['/', '/scanners'])
  })
})

describe('indexability', () => {
  it('keeps the thank-you page and 404 out of the index', () => {
    // A thank-you page in search results is a page people reach without
    // having done the thing it thanks them for.
    expect(PAGES.thanks.indexable).toBe(false)
    expect(PAGES.notFound.indexable).toBe(false)
  })

  it('indexes every marketing page', () => {
    for (const key of ['home', 'scanners', 'land', 'habitat', 'about',
                       'caseStudies', 'contact', 'request', 'privacy']) {
      expect(PAGES[key].indexable, key).toBe(true)
    }
  })

  it('keeps the application out of the marketing route table', () => {
    expect(pages.map((p) => p.path)).not.toContain(APP_PATH)
  })
})

describe('the canonical origin is configuration, never a guess', () => {
  it('emits no absolute URL until an origin is configured', () => {
    // A wrong canonical tells search engines the real page is elsewhere, and a
    // wrong og:url is cached by every platform that reads it. Omission is
    // recoverable; a wrong absolute URL is not.
    expect(siteOrigin()).toBe('')
    expect(absoluteUrl('/scanners')).toBe('')
  })
})

describe('one conversion action', () => {
  it('names the primary CTA once, so every button agrees', () => {
    expect(PRIMARY_CTA.label).toBe('Request a site scan')
    expect(PRIMARY_CTA.path).toBe(PAGES.request.path)
  })
})
