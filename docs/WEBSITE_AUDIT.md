# Website, SEO and trust pass

> **Update: the marketing site now exists.** The blocked items below were
> blocked on routes, and there are ten. What remains blocked is blocked on
> *business facts* — real customers, a real address, a real legal entity — and
> that is a different kind of blocker that no amount of building resolves. See
> §"After the site was built".

## Original audit — what was done, and what was blocked

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


---

## After the site was built

### Routes

| Route | Title | Indexable | Breadcrumbs |
| --- | --- | --- | --- |
| `/` | Site Scanner \| Environmental site evidence | yes | none (homepage) |
| `/scanners` | Scanners \| Site Scanner | yes | 2 |
| `/scanners/land` | Land Scanner \| Site Scanner | yes | 3 |
| `/scanners/habitat` | Habitat Scanner \| Site Scanner | yes | 3 |
| `/about` | About \| Site Scanner | yes | 2 |
| `/case-studies` | Case studies \| Site Scanner | yes | 2 |
| `/contact` | Contact \| Site Scanner | yes | 2 |
| `/request-a-site-scan` | Request a site scan \| Site Scanner | yes | 2 |
| `/thank-you` | Enquiry received \| Site Scanner | **noindex** | 2 |
| `/privacy` | Privacy policy \| Site Scanner | yes | 2 |
| `*` → 404 | Page not found \| Site Scanner | **noindex** | 2 |
| `/app` | (application) | disallowed in robots.txt | — |

Verified in a browser: every title unique, every description present, one `h1`
per route, Open Graph on all, no horizontal overflow at 1440×900 or 390×844,
no console errors.

### Canonical URLs and the sitemap are configuration

`VITE_SITE_ORIGIN` supplies the production origin. **Unset, no canonical tag,
no `og:url` and no sitemap are emitted at all** — a wrong canonical tells a
search engine the real page is elsewhere, and a wrong `og:url` is cached by
every platform that reads it. The sitemap is generated at build time from the
route table, so it cannot drift.

    VITE_SITE_ORIGIN=https://the-real-domain.example

### Structured data

`BreadcrumbList` only, and only when an origin is configured. `Organization`
and `LocalBusiness` were **not** added: both require a legal entity, an address
and contact details nobody has supplied, and fabricated structured data is a
machine-readable claim rather than a cosmetic one.

---

## Still requires real business information

Each has a built, working component and an empty state that reads as a
decision rather than a gap.

| What | Where | Needed |
| --- | --- | --- |
| **Contact details** | `/contact` | A monitored email address. A registered address and map only if one exists. |
| **Team** | `/about` | Names, roles, bios, photography. No placeholder people. |
| **Case studies** | `/case-studies` | Real projects. The page says so plainly. |
| **Reviews** | not rendered | No component is shown, because showing an empty testimonials section advertises the absence. |
| **Response time** | `/thank-you` | An SLA. Until then the copy is neutral: *"We will review it and get back to you."* |
| **Legal entity** | `/privacy` | Company name, registered address, data-protection contact, retention period, legal review. |
| **Form endpoint** | `/request-a-site-scan` | **Nothing receives a submission.** The form validates and routes to the thank-you page; there is no backend to store or forward it. |
| **Canonical domain** | build | `VITE_SITE_ORIGIN` |
| **Analytics** | build | `VITE_GA_MEASUREMENT_ID`, plus a consent mechanism and the decision to track at all |

**The form endpoint is the most urgent.** A contact form that goes nowhere is
worse than no form, and this one should not go live until something receives
the submission.

## Deliberately not fabricated

No reviews, case studies, statistics, response times, team members, addresses,
phone numbers, client names, project outcomes, company registration details or
aggregate ratings. No `Organization` or `LocalBusiness` schema. No placeholder
`og:url` or canonical. No measurement ID.

---

# Production-quality audit — second pass

The same 20-item checklist, re-run against the site that now exists, plus the
application. Every row was checked in a browser against a running backend, not
read off the source. Four classifications:

**A** already correct · **B** missing, fixed · **C** not appropriate here ·
**D** needs a product or business decision

| # | Item | | Finding |
| --- | --- | --- | --- |
| 1 | Deployment URL | **D** | `vercel.json` is complete: SPA rewrite, CSP, security headers, immutable asset caching, `must-revalidate` on the document. The *domain* is a business decision, and everything that depends on it is gated on `VITE_SITE_ORIGIN` rather than guessed. |
| 2 | view-source / initial HTML | **D** | A 2,099-byte SPA shell carrying the homepage's real title, description and Open Graph tags. Fine for the application; a limit for the marketing pages, whose copy is invisible to a crawler that does not execute JavaScript. See "The one open SEO question" below. |
| 3 | 404 page | **B / D** | The page exists, is `noindex, follow`, offers a way back, and is now covered by an e2e test. **But it answers HTTP 200**, because the SPA rewrite serves `index.html` for everything — a soft 404. Fixing it properly needs a serverless catch-all or prerendering; both are deployment decisions, so this is recorded rather than guessed at. |
| 4 | Vite + React production behaviour | **A** | Builds clean with no warnings. Verified by serving the built output, not the dev server. |
| 5 | Unique page titles | **A** | 10 of 10 unique, from one route table. Asserted by unit test and re-verified in a browser. |
| 6 | Meta descriptions | **A** | 10 of 10 unique and specific. |
| 7 | `og:image` | **D** | Absent because no branded social image exists. A generated placeholder would be worse: it is cached by every platform that reads it. Needs an asset, not code. |
| 8 | Structured data | **A** | `BreadcrumbList` only, gated on a configured origin. `Organization` was correctly refused — it needs a legal entity nobody has supplied, and invented structured data is a machine-readable lie. |
| 9 | Multiple H1s | **A** | Exactly one per route, all ten verified. |
| 10 | Missing H1 | **B** | The public site was fine. The **report view had no h1 at all** — the site name was an `h2` under nothing. Promoted, with its sections following to `h2`. No visual change; the CSS is class-based. |
| 11 | Canonical tags | **A** | Emitted only with `VITE_SITE_ORIGIN`. Omission is recoverable; a wrong canonical tells a search engine the real page is somewhere else. |
| 12 | `llms.txt` | **C** | Not added. It is a proposed convention with thin adoption, and this site is ten pages of plain prose that any crawler can already read. It would be a file asserting we are current with a fashion, maintained by nobody. Revisit if the documentation grows. |
| 13 | robots.txt / AI crawlers | **A / D** | `robots.txt` exists and reasons in the file: `/app` disallowed (client-side state, nothing to index), `/thank-you` disallowed, everything else open. **No AI-specific blocks**, deliberately — this product's problem is being found, not being read. Whether to exclude AI crawlers is a commercial decision, not a technical default. |
| 14 | Favicon | **B** | `favicon.svg` was present and served. Added a 180×180 `apple-touch-icon.png` — iOS does not synthesise one from SVG and falls back to a screenshot of the page — and a `theme-color`. No web manifest: without a real install experience it is a file that exists to be found by an audit. |
| 15 | `sitemap.xml` | **A** | Generated at build from the route table, so it cannot list URLs that no longer exist. Skipped entirely without an origin, because a sitemap of relative paths is invalid. |
| 16 | `html lang` | **A** | `lang="en"` on every route. |
| 17 | Image alt text | **A / B** | No `<img>` in the product is missing `alt`. Seven **icon SVGs inside labelled buttons** were exposed to the accessibility tree as unnamed graphics — now hidden, since the button's own name is the information. |
| 18 | Source maps | **A** | Not emitted in production; Vite's default is off and nothing overrides it. No action, and none wanted: this repository is public, so the source is not secret, but shipping maps to every visitor costs bandwidth for nothing. |
| 19 | Console errors | **A / B** | Zero across the whole journey at both viewports. Now **enforced** rather than observed: the e2e suite fails on any console error or uncaught exception, third-party tile noise excluded. |
| 20 | Bundle size | **B** | Was one 1,694 kB chunk for every route — the About page downloaded MapLibre, seven turf modules and Observable Plot to render three paragraphs. Now 81 kB gzipped for the public site, 298 kB for the application, 96 kB for charts on demand. |

## Site Scanner is not a marketing website

The checklist assumes a content site. This is a browser-based GIS application
with a marketing site attached, and the two want opposite things.

- **The public site** — homepage, scanner pages, about, contact, privacy — is
  content, and every SEO item above applies to it in full.
- **The application** at `/app` is not content and should not be treated as
  content. Its state is a drawn shape and an open investigation held in a URL
  fragment that never reaches a server. There is nothing to index, and an
  assessment URL in search results would be **someone else's site**. It is
  disallowed in `robots.txt` for that reason, not for SEO hygiene.

Nothing was added to the application to satisfy a checklist. No structured data
describes a report, no headings were invented to fill an outline, and no
rendering strategy changed to make the HTML source look busier.

## The one open SEO question

The marketing pages render client-side, so their copy is invisible to a crawler
that does not execute JavaScript. Google generally does execute it; most other
crawlers, and most social-preview fetchers, do not.

This did not get fixed, and the reason is that the fix is a decision rather than
a task:

- **Prerendering** the ten public routes to static HTML at build time would
  resolve it, keep the SPA intact, and cost one build plugin. It would also
  give the 404 a real status code.
- **SSR** would resolve it and impose a server, a runtime and a rendering
  discipline on a codebase that currently deploys as static files plus one
  function.

Prerendering is the proportionate answer **if and when organic search matters
commercially**. Until then this is a known limit, not an accident. Rebuilding
the architecture so that view-source looks impressive would be work done for an
audience of one, and that audience is a checklist.
