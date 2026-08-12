# Where Site Scanner is

**Read this first in a new session.** It is the state of the product as of the
last commit on `claude/site-scanner-status-iit6d2`. Where this and the code
disagree, the code is right and this file is a bug — check it before trusting it.

The autonomous transformation pass of 2026-08-12 changed the scanner taxonomy,
added the evidence record, the portfolio and the review model, and rewrote the
scanner library. `docs/AUTONOMOUS_CHANGELOG.md` is the decision log for it and
is the file to read second.

Everything below is a fact from the repository. Nothing here is aspiration.

---

## What Site Scanner is

A browser-based environmental site intelligence platform for England. A user
draws an area on a map, picks a scanner, and gets a report that separates what
was found, what was checked and cleared, and what could not be assessed at all.

**The positioning, and the whole reason the codebase looks like it does:**

> It does not score a site, rank one against another, or say whether somewhere
> is suitable for anything. Those are professional judgements and belong to
> the person whose name goes on the report. Site Scanner prepares the question.

Buyers are environmental consultants, ecologists, land managers, and the
planning and development professionals who commission their work.

### The rule everything else follows

**Never claim anything the evidence does not support.** In practice:

- A check that could not run reports **not assessed**, never **clear**.
  Silence is not safety.
- Generated data may never produce a finding. The mock backend stamps every
  response `X-Contour-Mock: true` and the UI says so.
- Every threshold Contour chose is labelled **product-defined** and is never
  described as regulatory, statutory or scientific consensus.
- Every finding states what it does **not** establish.
- No site score exists, and adding one would be the single worst change anyone
  could make to this product.

If a task seems to require breaking one of these, that is the finding — say so
rather than working around it.

---

## Architecture

```
Python / FastAPI  ─ assessment engine, domain-agnostic
  scanners.py     ─ the registry: families → scanners → domains
  radar.py        ─ rules, findings, coverage. Knows no scanner's domain.
  catalog.py      ─ 271 factors
  habitat/, coastal/, historical/  ─ contributing rule packages
  site_record.py  ─ the canonical form of one assessment
  portfolio.py    ─ many sites, one view
  review.py       ─ the professional co-sign model (defined, empty)

React 19 + Vite + TypeScript
  web/src/            ─ the application (/app)
  web/src/site/       ─ the marketing site (/)
```

**The architectural property worth protecting:** there is not one scanner id
anywhere in `web/src` except `lib/scannerVoice.ts`, which is a presentation
lookup table. Components render whatever the API describes. Adding a scanner
is a registry entry plus a row in that table — not a refactor.

Contributing rule packages implement `build(Rule, Insufficient)` and never
import the engine. Adding Habitat needed no engine change. Adding Coastal
needed no engine change. Keep it that way.

---

## The scanners

Eight in four families. Four run today, and three of those four cover **part**
of their subject and say which part.

| Family | Scanner | Status | Rules | Factors |
| --- | --- | --- | --- | --- |
| Foundation | Land | live | 25 | 271 |
| Foundation | Water | partial | 11 | 9 |
| Foundation | Ecology | partial | 16 | 10 |
| Development | Planning | partial | 7 | 7 |
| Development | Development | planned | 0 | 0 |
| Development | Infrastructure | planned | 0 | 0 |
| Culture | Heritage | planned | 0 | 0 |
| Economics | Market | planned | 0 | 0 |

Coverage is England for every built scanner. `partial` means at least one
declared domain has no checks — Water does not read groundwater, drainage or
catchment; Ecology does not read woodland, protected species or connectivity;
Planning does not read application history or policy. Each names its specific
blocker, and the library shows both lists on the card **before** the scanner is
chosen.

**`habitat`, `coastal`, `terrain` and `forestry` are aliases**, resolving to
the scanner that absorbed them. Saved links and stored reports keep working.
They are absent from the catalogue: an alias is a door that still opens, not a
product that still exists.

Land deliberately overlaps the specialists — it is the sweep you run before you
know which question matters. A rule has exactly one definition and is shared by
object, never copied, so two scanners cannot disagree.

Full detail — every rule, threshold, investigation and capability gap — is in
`docs/SCANNER_SPECIFICATION.md`. That is the product truth.

### The two product decisions still unvalidated

1. Coastal's **5 m AOD** low-lying screening height.
2. Coastal's **10 percentage point** water-extent change threshold.

Both are defensible and both are ours. A coastal engineer should sign them off
before launch, or they should be replaced with Environment Agency design sea
levels once those are ingested.

---

## The data problem — read this before promising anything

**Of Land's 271 factors, 28 return real observations and 11 of those are
`verified` (actually run against the live service). The other 243 are
generated.**

The demo backend (`mock_ee_backend`) produces no findings at all: every check
reports "no signal" because nothing may be claimed from generated numbers.
**That is correct behaviour, not a broken install.**

Real observations need Earth Engine credentials and the real backend:

```bash
export GOOGLE_APPLICATION_CREDENTIALS_JSON="$(cat service-account-key.json)"
export EE_PROJECT="your-gcp-project-id"
python3 -m uvicorn app:app --port 8000
```

Check which one answered:

```bash
curl -sD- localhost:8000/api/catalog -o /dev/null | grep -i contour-mock
```

**This is the single biggest constraint on the business right now.** It blocks
product screenshots, blocks any demo that shows a finding, and blocks the
marketing site from doing its job.

---

## The marketing site

Eleven public routes at `/`, structured as an investigation unfolding: hero →
platform → instrument → field record → assessment → change → request.

Design direction is **field science × 1990s outdoor equipment × editorial** —
bone ground, charcoal type, deep forest structure, signal orange rationed
hard. Explicitly not SaaS, not ArcGIS, not AI-startup.

### The asset system

**The user art-directs; Claude does not source or generate imagery.**

21 named slots in `web/src/site/assets.ts`, files dropped into
`web/public/assets/<section>/`. A slot with no file renders a frame the same
size stating which file goes there, what it should show, and what to export at.
`web/public/assets/README.md` is the source of truth.

**Currently 0 of 21 supplied.** Six of those are product screenshots that
cannot be taken until Earth Engine credentials exist — a screenshot of the mock
is invented findings with a badge admitting it.

---

## What blocks launch

| | What | Why it matters |
| --- | --- | --- |
| 1 | **The enquiry form goes nowhere** | It validates and routes to a thank-you page. Nothing receives the submission. A contact form that silently discards enquiries is worse than no form. |
| 2 | **Earth Engine credentials** | Without them there are no findings, no screenshots, and no demo. |
| 3 | **Business facts** | Contact details, team, case studies, legal entity, canonical domain. Each has a built component and an honest empty state. None has been invented. |
| 4 | **21 unsupplied assets** | The site reads as a shot list. |

Two smaller ones: the 404 answers HTTP 200 (SPA rewrite — a soft 404), and
marketing copy is invisible to crawlers that do not run JavaScript.
Prerendering the eleven public routes fixes both; SSR would be
disproportionate. `docs/WEBSITE_AUDIT.md` has the reasoning.

---

## How to run it

`docs/CLOUD-SHELL.md` has the verified commands. Briefly, two terminals:

```bash
python3 -m uvicorn mock_ee_backend:app --port 8000    # API
cd web && npm run dev -- --port 8080 --host           # site
```

`--host` is not optional in Cloud Shell — without it Vite binds to localhost
and the preview button returns a blank page with no error.

## Tests

```
1053 Python     pytest tests/
 343 unit       cd web && npm run test
  36 e2e        cd web && npx playwright test     (both viewports)
```

In this sandbox the pinned Playwright expects a Chromium build that is not
installed. Run it with a config that sets
`use.launchOptions.executablePath = '/opt/pw-browsers/chromium'`.

Production build is authoritative — `npm run build`, not `tsc --noEmit`.

**Never weaken a test to make a change pass.** Several of these exist because a
bug shipped past a green suite.

---

## How this project works

The user is the creative director and the domain authority. Claude is the
engineer. Some things that have been established the hard way:

- **Verify in the browser, not by reading code.** Two real defects — a clipped
  report panel and the active scanner never reaching the assessment requests —
  shipped past a green unit suite and were found by driving the app.
- **Prove a regression test fails on the broken code before keeping it.** One
  layout assertion passed with the bug reintroduced; it was measuring the wrong
  thing.
- **Report honestly.** If something is blocked, say so and say what would
  unblock it. Do not make a report look complete by hiding a gap.
- **Do not pad.** A scanner with five defensible rules beats one with twenty
  invented ones. The same goes for factors, findings and marketing claims.

### One environment warning

The development container **resets to an old commit without warning**, several
times per session. The remote branch is the only source of truth. On starting,
and after anything unexpected:

```bash
git fetch origin claude/site-scanner-status-iit6d2
git reset --hard origin/claude/site-scanner-status-iit6d2
```

Commit and push early and often. Work that is not pushed will be lost.

---

## The next opportunity

The engine is more generic than the product presents, and the taxonomy pass
made that visible rather than changing it: four scanners now share it with no
engine branching, and Planning was built entirely from rules that already
existed.

What is new and unused is the **evidence record**. Every assessment can now be
stored in a stable, addressable, versioned form with the site identified by its
geometry — which is what makes monitoring, portfolios and a longitudinal dataset
possible. Nothing consumes two records yet, and that is the largest piece of
value sitting one feature away.

In order: **credentials, then a screenshot, then the enquiry endpoint.** Those
three turn a well-built thing into a sellable one, and none of them is
engineering work. After that: Heritage ingestion, which would take a declared
scanner to partial and prove the taxonomy carries a genuinely new domain.
