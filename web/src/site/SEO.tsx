import { useEffect } from 'react'
import { PAGES, absoluteUrl, type PageMeta } from './site'

/**
 * Per-page metadata, applied to the document head.
 *
 * A hook rather than a library: this site has ten routes and one `<head>` to
 * manage, and a helmet dependency for that is more moving parts than the
 * problem has.
 *
 * **Absolute URLs are emitted only when `VITE_SITE_ORIGIN` is configured.** A
 * wrong canonical tells search engines the real page is elsewhere and a wrong
 * `og:url` is cached by every platform that reads it — so with no configured
 * origin, those tags are absent rather than guessed.
 */
function setMeta(attr: 'name' | 'property', key: string, value: string): void {
  const selector = `meta[${attr}="${key}"]`
  let tag = document.head.querySelector<HTMLMetaElement>(selector)
  if (!value) { tag?.remove(); return }
  if (!tag) {
    tag = document.createElement('meta')
    tag.setAttribute(attr, key)
    document.head.appendChild(tag)
  }
  tag.setAttribute('content', value)
}

function setLink(rel: string, href: string): void {
  let tag = document.head.querySelector<HTMLLinkElement>(`link[rel="${rel}"]`)
  if (!href) { tag?.remove(); return }
  if (!tag) {
    tag = document.createElement('link')
    tag.setAttribute('rel', rel)
    document.head.appendChild(tag)
  }
  tag.setAttribute('href', href)
}

export function useSEO(page: PageMeta): void {
  useEffect(() => {
    document.title = page.title
    setMeta('name', 'description', page.description)
    setMeta('property', 'og:title', page.title)
    setMeta('property', 'og:description', page.description)
    setMeta('property', 'og:type', 'website')
    setMeta('name', 'twitter:title', page.title)
    setMeta('name', 'twitter:description', page.description)

    const url = absoluteUrl(page.path)
    setLink('canonical', url)
    setMeta('property', 'og:url', url)

    // A page that should not be indexed says so explicitly. The thank-you page
    // in search results is a page people reach without having done the thing
    // it thanks them for.
    setMeta('name', 'robots', page.indexable ? '' : 'noindex, follow')
  }, [page])
}

/**
 * Breadcrumb structured data.
 *
 * The one schema type emitted, because it is the only one describing something
 * that verifiably exists: this site's own navigation. `Organization` and
 * `LocalBusiness` need a legal entity, an address and contact details that
 * nobody has supplied, and fabricated structured data is a machine-readable
 * claim rather than a cosmetic one.
 */
export function BreadcrumbSchema({ page }: { page: PageMeta }) {
  if (!page.crumbs.length || !absoluteUrl(page.path)) return null
  const items = [...page.crumbs, { label: page.title.split(' | ')[0], path: page.path }]
  const json = {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: items.map((c, i) => ({
      '@type': 'ListItem',
      position: i + 1,
      name: c.label,
      item: absoluteUrl(c.path),
    })),
  }
  return <script type="application/ld+json">{JSON.stringify(json)}</script>
}

export { PAGES }
