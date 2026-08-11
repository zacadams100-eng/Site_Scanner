/**
 * The public website's routes and their metadata.
 *
 * One table, because titles, descriptions, sitemap entries and breadcrumbs all
 * describe the same set of pages and drift the moment they live in four
 * places. `SEO.tsx` reads it, the sitemap script reads it, and a test asserts
 * every entry is unique — which is the check the previous audit could not run
 * because there were no routes.
 *
 * ## The canonical domain is configuration, not a guess
 *
 * `VITE_SITE_ORIGIN` supplies it. Absent, canonical and `og:url` tags are
 * **omitted entirely** rather than pointed at a placeholder: a wrong canonical
 * tells search engines the real page is somewhere else, and a wrong `og:url`
 * is cached by every platform that reads it. Omission is recoverable; a wrong
 * absolute URL is not.
 *
 *     VITE_SITE_ORIGIN=https://the-real-domain.example
 */

export interface PageMeta {
  path: string
  /** The full `<title>`. Unique across the site — asserted by test. */
  title: string
  /** What a reader will actually find here. Not keywords. */
  description: string
  /** Breadcrumb trail, excluding the page itself. Empty on the homepage,
   *  which gets no breadcrumbs. */
  crumbs: { label: string; path: string }[]
  /** In the sitemap. Application routes are not. */
  indexable: boolean
}

export const PAGES: Record<string, PageMeta> = {
  home: {
    path: '/',
    title: 'Site Scanner | Environmental site evidence',
    description:
      'Site Scanner establishes what satellite and open data can show about a '
      + 'site, states what that evidence does not settle, and names what a '
      + 'professional should investigate next.',
    crumbs: [],
    indexable: true,
  },
  scanners: {
    path: '/scanners',
    title: 'Scanners | Site Scanner',
    description:
      'Specialist scanners for land and habitat, each establishing evidence '
      + 'about a place and the professional questions that remain. Four '
      + 'further verticals are in development.',
    crumbs: [{ label: 'Site Scanner', path: '/' }],
    indexable: true,
  },
  land: {
    path: '/scanners/land',
    title: 'Land Scanner | Site Scanner',
    description:
      'Site constraints and land assessment: designations, flood, ground and '
      + 'planning evidence, with every finding traced to its source and its '
      + 'limits stated.',
    crumbs: [
      { label: 'Site Scanner', path: '/' },
      { label: 'Scanners', path: '/scanners' },
    ],
    indexable: true,
  },
  habitat: {
    path: '/scanners/habitat',
    title: 'Habitat Scanner | Site Scanner',
    description:
      'Ecological condition and habitat investigation from fifteen years of '
      + 'Sentinel-2 observation, with a product-defined reporting threshold '
      + 'and an explicit statement of what a spectral index cannot establish.',
    crumbs: [
      { label: 'Site Scanner', path: '/' },
      { label: 'Scanners', path: '/scanners' },
    ],
    indexable: true,
  },
  coastal: {
    path: '/scanners/coastal',
    title: 'Coastal Scanner | Site Scanner',
    description:
      'Coastal site and frontage assessment: low-lying exposure and change '
      + 'in surface water extent, with the limits of a polygon-based '
      + 'assessment stated rather than implied.',
    crumbs: [
      { label: 'Site Scanner', path: '/' },
      { label: 'Scanners', path: '/scanners' },
    ],
    indexable: true,
  },
  about: {
    path: '/about',
    title: 'About | Site Scanner',
    description:
      'Why Site Scanner reports what it could not establish as carefully as '
      + 'what it could, and the evidence model that keeps it honest.',
    crumbs: [{ label: 'Site Scanner', path: '/' }],
    indexable: true,
  },
  caseStudies: {
    path: '/case-studies',
    title: 'Case studies | Site Scanner',
    description:
      'Worked examples of Site Scanner assessments. None are published yet — '
      + 'this page will carry real projects rather than illustrations.',
    crumbs: [{ label: 'Site Scanner', path: '/' }],
    indexable: true,
  },
  contact: {
    path: '/contact',
    title: 'Contact | Site Scanner',
    description:
      'Get in touch about a site, a scanner, or whether Site Scanner suits '
      + 'the work you are doing.',
    crumbs: [{ label: 'Site Scanner', path: '/' }],
    indexable: true,
  },
  request: {
    path: '/request-a-site-scan',
    title: 'Request a site scan | Site Scanner',
    description:
      'Describe a site or project you would like assessed and start a '
      + 'conversation about what Site Scanner can establish about it.',
    crumbs: [{ label: 'Site Scanner', path: '/' }],
    indexable: true,
  },
  thanks: {
    path: '/thank-you',
    title: 'Enquiry received | Site Scanner',
    description:
      'Your enquiry has been received. We will review it and get back to you.',
    crumbs: [{ label: 'Site Scanner', path: '/' }],
    // Deliberately not indexable: a thank-you page in search results is a page
    // people arrive at without having done the thing it thanks them for.
    indexable: false,
  },
  privacy: {
    path: '/privacy',
    title: 'Privacy policy | Site Scanner',
    description:
      'What data Site Scanner collects, why, and how long it is kept.',
    crumbs: [{ label: 'Site Scanner', path: '/' }],
    indexable: true,
  },
  notFound: {
    path: '/404',
    title: 'Page not found | Site Scanner',
    description:
      'That page could not be found. Return to Site Scanner or view the '
      + 'available scanners.',
    crumbs: [{ label: 'Site Scanner', path: '/' }],
    indexable: false,
  },
}

/** Where the application lives. Not in the sitemap: everything below it is a
 *  drawn shape and a chosen scanner held in a URL fragment, which no crawler
 *  can reach and none should try to. */
export const APP_PATH = '/app'

/** The configured production origin, or empty. Empty means no canonical or
 *  `og:url` is emitted at all — see the module docstring. */
export function siteOrigin(): string {
  return ((import.meta.env?.VITE_SITE_ORIGIN as string | undefined) ?? '')
    .replace(/\/$/, '')
}

/** An absolute URL, or empty when the origin has not been configured. */
export function absoluteUrl(path: string): string {
  const origin = siteOrigin()
  return origin ? `${origin}${path}` : ''
}

/** The one conversion action, named once so every button agrees. */
export const PRIMARY_CTA = { label: 'Request a site scan', path: PAGES.request.path }
