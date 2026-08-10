# Website, SEO and trust pass — what was done, and what is blocked

A 20-item website quality pass was requested. **Fourteen of the twenty require
a public marketing website, and there isn't one.**

That is not a scoping opinion, it is the state of the repository:

- **no router** — no `react-router`, no route definitions, no `pages/`
- **one HTML document**, whose `<title>` was `web` (the Vite default) until
  this pass
- **no public routes** — no `/about`, `/contact`, `/case-studies`, `/faq`,
  `/privacy`, no thank-you page
- everything below the entry point is client-side state in a URL **fragment**,
  which is never sent to a server and cannot be crawled

So "add unique titles to every public page", "add breadcrumbs to deeper public
pages", "audit internal links" and "add meta descriptions to public marketing
pages" have no pages to act on. Creating them would mean inventing an entire
marketing website — its information architecture, its copy, and above all its
**primary call to action**, which the brief itself says to identify rather than
invent when the business model is unclear.

The brief's own rule settles it: *a professional empty state is better than
fake credibility.* The same applies to structure — a `/case-studies` route with
nothing real behind it is a page that has to be maintained and explained.

---

## Done

| # | Item | What was done |
| --- | --- | --- |
| 2 / 11 | Page title | `Site Scanner \| Environmental site evidence` — was `web` |
| 12 | Meta description | One, describing what the application does |
| 13 | Social metadata | `og:type`, `og:site_name`, `og:title`, `og:description`, Twitter card |
| 10 | `robots.txt` | Created, `Allow: /`, with the reasoning in the file |
| 16 | Alt text | Audited — see below |
| 19 | Analytics | `lib/analytics.ts`: env-configured, consent-gated, inert |

### Alt text audit

Every image in the application is either an inline SVG icon inside a labelled
control, or decoration.

| Asset | Treatment |
| --- | --- |
| `BrandMark` | `role="img"` with `aria-label` |
| Toolbar / rail icons | `aria-hidden`, inside buttons carrying `aria-label` |
| Scanner library contours | `aria-hidden` — decorative, carries no information |
| Map canvas | MapLibre canvas; the surrounding controls are labelled |
| Site thumbnails | Generated previews with the site's own name |

No `alt="image"`, no keyword stuffing, and **no informative image without a
text equivalent**. There is no photography, no team imagery and no case-study
imagery, because none exists.

### `og:url` and `og:image` deliberately omitted

There is no canonical public URL for this deployment and no branded social
image. A placeholder `og:url` is cached by every platform that reads it, so a
wrong one is worse than none. Both need a real deployment and a real asset.

---

## Blocked on a marketing website that does not exist

| # | Item | What it needs first |
| --- | --- | --- |
| 1 | Custom 404 | A router. Nothing can 404 today. |
| 3 | Internal links | Pages to link between |
| 4 | Thank-you page | A contact flow, which needs a form and a recipient |
| 5 | Breadcrumbs | A route hierarchy |
| 6 | Case studies | **Real projects.** Structure without content is maintenance. |
| 7 | FAQ | A route, plus answers that match what the product actually supports |
| 8 | Response-time promise | **A business decision.** No SLA exists. |
| 9 | Sticky mobile CTA | A conversion action to point at |
| 14 | Maps and directions | **A real address.** None exists. |
| 15 | Reviews | **Real customers.** None exist. |
| 17 | Local schema | A real business entity, address and details |
| 18 | Privacy policy | A legal document naming a real data controller |
| 20 | Team section | **Real people and real photography.** |

## Deliberately not fabricated

No reviews, case studies, statistics, response times, team members, addresses,
phone numbers, client names or project outcomes were invented — and no
structure was created that would need fake content to look finished.

Structured data (`Organization`, `LocalBusiness`, `BreadcrumbList`) was **not**
added. Every one of them requires facts about a business that this repository
does not contain, and fabricated structured data is worse than none: it is a
machine-readable claim.

---

## The decision this pass surfaces

Before any of the blocked items can be built, one question needs answering:

> **Is there a marketing website, and what is its single conversion action?**

The brief lists "Request a site scan" and "Talk to us" as examples and says to
identify the decision rather than invent one. It is genuinely unclear from the
repository, which contains an application and no commercial surface: no
pricing, no accounts, no contact route, and `BLOCKERS.md` records that the
commercial licensing questions behind all of it are still open.

Building the marketing site before that is answered would produce pages whose
copy has to be rewritten the moment it is.

### If the answer is "yes, build it"

The order that follows from this audit:

1. A router, and the two pages that carry the decision — home and contact
2. 404, thank-you, privacy policy
3. Titles, meta descriptions, canonical URLs, breadcrumbs, sitemap
4. `og:url` and a branded `og:image`
5. Consent mechanism, then analytics
6. Trust components — FAQ first, since it needs no external input; case
   studies, reviews and team only when there is something real to put in them
