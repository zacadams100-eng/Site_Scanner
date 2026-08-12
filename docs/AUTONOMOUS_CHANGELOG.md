# Autonomous transformation pass — decision log

**2026-08-12.** One session, no founder available. Branch
`claude/site-scanner-status-iit6d2`, based on `claude/sitescanner-handoff-fx0yid`.

This is the record to review the work against. It states what changed, what was
decided without asking, what was deliberately not built, and what is still
risky. Where a decision could reasonably have gone the other way, the reasoning
is here rather than only in a commit message.

**Baseline at start:** 938 Python tests, 317 frontend, clean build.
**At end:** 1053 Python, 343 frontend, 36 e2e (both viewports), clean build.

---

## Decisions taken without asking

### 1. Land keeps everything; the specialists overlap it

**The brief said** Terrain → Land, Coastal → Water, Habitat → Ecology, Forest →
Ecology.

**What the code showed:** the land scanner was already carrying seven topics —
flood, surface water, ground, terrain, vegetation, ecology, planning — and 25
rules across all of them. The specialist scanners were latent in the rule set
before anyone drew the taxonomy.

**The decision:** the obvious reading was to *move* those rules out of Land into
the new scanners. I did not, because it would have destroyed working
functionality: Land would have dropped from 25 rules to 5, and a professional
running the foundation scanner would no longer be told about Flood Zone 3. That
is a taxonomy failing its user.

Instead Land keeps all seven topics and the whole catalogue, and the specialists
present the same rules through their own lens. **A rule has exactly one
definition** — Land and Water share the identical `Rule` object, selected by
topic, never copied — so the two cannot disagree. `test_where_land_overlaps_a_specialist_it_is_the_same_rule_not_a_copy`
asserts object identity.

**If this was wrong,** the alternative is to make Land a *composite* that
declares it presents other scanners' domains, rather than owning them. That is a
presentational change, not a structural one; the rule identity property already
makes it safe either way.

### 2. Planning was promoted to a scanner rather than declared

Seven planning rules were already running and already tested inside Land.
Registering Planning as a fourth built scanner cost nothing and gave the
Development family something real in it.

It is **not new evidence and does not claim to be** — the same checks, reachable
by someone whose question is planning rather than land. Its status is `partial`
because applications, history and policy are not built, and those are the
domains a planning consultant would most want.

### 3. `status` is derived, not stored

`live` / `partial` / `planned`, computed from the domains. A stored status is a
claim someone has to remember to update. Derived, it cannot go stale, and it
moves in the honest direction: a scanner that declares a new domain drops to
`partial` the moment it does.

**Consequence worth knowing:** three of the four built scanners are `partial`.
That is a less flattering front page than "four scanners available" and it is
the accurate one.

### 4. Retired ids became aliases, not deletions

`habitat`, `coastal`, `terrain`, `forestry` resolve to the scanner that absorbed
them. Saved permalinks, stored reports and any API client keep working. They are
absent from `ids()`, so they do not appear in the catalogue, the library or the
error message listing valid ids — an alias is a door that still opens, not a
product that still exists.

### 5. The evidence record was built before anything needed it

Nothing consumes two records yet. It was built anyway because **a longitudinal
record can only be assembled from assessments that were recorded comparably at
the time.** Nothing retrofits it, and the records not kept today are the ones
that can never be compared tomorrow. This is the single highest-leverage thing
in the pass and it is currently unused.

### 6. `site_id` is a content hash of the geometry

So the same field assessed in March and August is one site, without requiring an
account, a saved-sites table or a naming convention. Rounded to ~0.1 m to absorb
float noise from permalinks and redrawing; both directions tested.

**Risk:** a site whose boundary is *slightly* redrawn — a corner moved five
metres — is a different site and loses its history. That is the correct
behaviour for evidence (a different polygon is a different area of ground) and it
will surprise a user. A future "is this the same site as..." affordance would
need to be explicit rather than automatic.

### 7. No storage was built

The storage decision is bound up with authentication, which does not exist, and
with tenancy, which is a business decision. Building a store now would encode
guesses about a data model whose main constraint has not been decided. Everything
downstream of one is built and tested; when a store arrives it fills `entries`
and nothing else changes.

### 8. The demonstration portfolio serves generated evidence

The only place in the product that does, deliberately. An empty portfolio cannot
show what a portfolio does, and there is no real one to show. The entire safety
of that decision is in the labelling, so it is stamped on the record, the entry
and every row — a legend does not survive a row being copied into a deck.

Two things I changed after looking at the first output: 19 of 24 sites carried a
finding (reads as an alarm, not an instrument) and none was unassessed (hiding
`sites_unassessed`, the radar's most important number). Now 6 of 24 are never
scanned and most of the rest are quiet.

### 9. The portfolio got a screen; the public site was brought with it

The portfolio had an API, a demonstration dataset and 36 tests and no way to
look at it. It is now a third top-level view, because "all of these sites" is a
different question from "this site" rather than a tab within it.

The public marketing site had drifted badly — "Six scanners, three you can run
today", Habitat and Coastal listed as products, Water and Terrain under "in
development" when both were built or absorbed. Both scanner listings are now
grouped by family and state partial coverage explicitly.

**URLs were deliberately left alone.** `/scanners/habitat` still resolves and
still describes habitat, which is still exactly what that domain does. Renaming
public routes would break anything indexed or bookmarked for a gain that is
purely cosmetic, and the backend already treats the old ids as aliases. If the
founder wants canonical `/scanners/ecology` URLs, that is a redirect map plus a
prerender change and should be done as one deliberate SEO decision rather than
as a side effect of a refactor.

### 10. The review model was built empty

No reviewer accounts, authentication, signing or workflow — each depends on
decisions the product cannot make alone. What *can* be decided now is what a
review must contain in order to mean anything, and that is the useful half.

`unreviewed` is a state rather than a missing value, because a record whose
review status is unrepresentable can only ever be machine output.

---

## Defects found and fixed

| | What | How it was found |
| --- | --- | --- |
| 1 | **`email-validator` undeclared in both manifests.** `routes_enquiry` imports `EmailStr` at module scope, so the container failed its revision and every serverless route returned 500 — not just the form | Baseline test run in a clean environment |
| 2 | **A missing rules package would have produced a silent empty scanner.** A domain names its package as a string and `rules_from` swallows ImportError by design, so Water could have claimed to cover coastal exposure and never looked | Introduced by my own change; caught by the Dockerfile test complaining the packages were unused, then closed at the registry |
| 3 | **Water, Ecology and Planning fell back to the neutral instrument voice** | Driving the page in a browser |
| 4 | **Workspace and library palettes keyed on retired scanner ids** | Same |
| 5 | **Every declared scanner rendered as a dark block with grey text.** `.lib-plate[data-scanner]` is (0,2,0); `.lib-plate-static` is (0,1,0), so the background it set never applied | Same. No test could have seen it |
| 6 | **Three vacuous tests.** Assertions about findings that passed by being unreached, because the mock produces no findings by design | Checking my own new tests against real output before committing |
| 7 | **A duplicate `.lib-plate-inst` rule** I had introduced, where a canonical one already existed further down | Reading the file after the specificity bug |
| 8 | **Four e2e failures.** The library now renders a plate per registered scanner, so a count of `.lib-plate` was 8 where 4 was expected; three specs drove "Habitat", which is no longer a scanner | Running the e2e suite, which neither the unit suite nor the build could substitute for |
| 9 | **A stale prerender assertion** requiring "Habitat" and "Coastal" in the built `/scanners` page | Same |
| 10 | **Every demonstration row read "Date not recorded"**, which looks like a rendering fault | Looking at the finished screen |

Defects 3–5 all shipped past a green unit suite *and* a clean `tsc --noEmit`
*and* a clean production build. That is the third time this project has recorded
the same lesson, and it is now in `docs/DESIGN_SYSTEM.md` under "verifying a
change".

---

## Tests: what changed and why

**Added:** `test_dependency_manifests.py`, `test_site_evidence_record.py` (30),
`test_portfolio.py` (21), `test_portfolio_route.py` (15), `test_review.py` (23),
and new registry/taxonomy tests. Frontend: `library.test.ts` rewritten against a
real module (17).

**One test inverted rather than deleted.**
`test_the_three_scanners_ask_different_questions` asserted that no two scanners
share a rule id. The overlap decision makes that false by design.

Deleting it would have thrown away the guarantee it was protecting — which was
never disjointness, but **two scanners must not be able to disagree**. It became
two stricter tests: specialists stay disjoint from each other, and where Land
overlaps a specialist it must be the *same object*. The second fails loudly if
the overlap disappears entirely, so it cannot quietly stop asserting anything.

**No test was weakened to make a change pass.** Tests scoped to coastal or
habitat rules were re-scoped through the new `Scanner.rules_in(domain)` — the
same assertions against the same rules, addressed by domain instead of by
scanner.

---

## Deliberately not implemented

- **Storage, accounts, authentication, tenancy.** See decision 7.
- **A job queue.** Assessing a portfolio is N assessments.
- **Change detection across records.** The record makes it possible.
- **Third-party scanner isolation.** `rules_from` imports and calls arbitrary
  code in-process. Fine for first-party packages, unacceptable for external
  ones.
- **Any new data source.** No ingestion was written. The data problem is
  unchanged: 28 of 271 factors real, 11 verified.
- **Anything in Heritage, Infrastructure, Development or Market beyond
  registration and stated blockers.**

---

## Remaining risks

**1. The product looks less finished than it did.** Three of four scanners now
say "partial coverage" where they previously said "available". This is accurate
and it is a worse first impression. If a demo is imminent, that is a real cost —
but the alternative is a clear result being read as a clean site.

**2. Land's 271-factor catalogue is mostly generated.** Unchanged by this pass
and still the biggest constraint on the business. The taxonomy makes the
*shape* honest; it does nothing about the *data*.

**3. The record is unused.** The portfolio now consumes summaries of it, but
nothing consumes two records, which is the capability it exists for. Well-tested
code with no consumer is code that drifts.

**7. The portfolio screen only ever shows the demonstration portfolio.** There
is no store, so there is nothing else to show. The labelling is thorough and
tested, but a screen whose only content is generated is a standing hazard —
anyone screenshotting it for a deck must keep the banner in frame.

**4. `site_id` stability across redrawing.** See decision 6.

**5. The demonstration portfolio is a standing hazard.** It is labelled at every
level and tested on every path, but it is generated evidence served over HTTP.
Any future change to it should re-read `tests/test_portfolio_route.py` first.

**6. Coastal's two thresholds remain unvalidated** — 5 m AOD and 10 percentage
points. Unchanged by this pass; now surfaced in the Water scanner rather than a
Coastal one, which does not change who needs to sign them off.

---

## What I would do next, in order

1. **Earth Engine credentials.** Everything else is downstream. It is a founder
   action, not an engineering one.
2. **Heritage ingestion.** The National Heritage List is open under OGL. It
   would take Heritage from `planned` to `partial` and prove the taxonomy carries
   a genuinely new domain.
4. **Storage**, once there is a view on accounts.
5. **Two records compared.** The moment there are two, monitoring is reachable.
