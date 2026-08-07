# Progress log

A running log, appended to each session. Newest entry at the top. Nothing here
is overwritten, so the history of what was true when stays visible.

---

## 2026-08-07 — Uncertainty made visible, and rainfall made real

### Orientation: the checkout was 39 commits stale

The session started on a branch whose tip was a merge commit from 2026-08-05
11:24, while the real tip of the project was `claude/handoff-md-review-e6zlvw`
at 20:59 the same day — 39 commits and 16,650 lines ahead, carrying
`PROGRESS.md`, `BLOCKERS.md`, `nlq.py`, `open_data.py`, `ons/` and `ratelimit.py`.
`main` is still the July prototype, five commits of a different thing.

Worth recording because it will happen again: **the newest work in this repo
is never on `main`, and not reliably on the branch you are handed.** Compare
every remote branch by commit date before starting.

### Confidence is drawn on the map now

`valid_fraction` has always been in the data and the map ignored it. A month
where 8% of the site had a usable observation was painted exactly as
confidently as one at 95%, and the colour is the claim.

Two states are drawn that were not:

- **Low confidence** — sparse 45° hatch over the cells, value still legible.
- **No observation** — dense hatch over the AOI with no fill. Previously the
  overlay just cleared, which is honest about the number and silent about the
  reason: a blank site looked identical to one with nothing selected.
  Sentinel-2 alone leaves 74 of 180 months in that state.

**Why hatching rather than fading the uncertain cells.** The value ramp
already starts near the paper colour, so a low value recedes into the page by
design. Fading low-confidence cells would make "a small number" and "a number
we do not trust" the same picture, and the reader cannot tell which they are
looking at. Hatching is a separate channel, and it is the standing
cartographic convention for unreliable data.

The threshold is `confidenceBand`'s existing 0.4 cut, reused rather than
redefined, and the timeline chip now goes through the same function — two
definitions of "low confidence" is how a table and a map come to disagree
about one number with no way to tell which is lying. The chip quotes the
figure ("28% observed") because that can be checked and an adjective cannot.

### Open question 3 is settled: grade the caveat, and name the direction

A year built from fewer than twelve months was marked with a `·` everywhere,
at one volume. That is wrong in both directions — a year missing one December
is nearly comparable, and NDVI's first year is missing January and February,
the two lowest months, so it reads as the highest vegetation on record.

The grade: nothing at twelve, the dot at one or two missing, the month count
(`8 mo`) and a stepped-back cell beyond that.

**The better part is that the direction is computable.** Which months are
missing matters more than how many — April and October cancel out, January and
February do not. Every factor carries fifteen years of monthly values, so the
seasonal shape is measured from the series itself: average each calendar month
across the record, then ask whether the months a year did observe sit above or
below that. Checked against the same year-to-year noise floor `nlq.py:_spread`
uses, and silent below it.

Three things the tests caught that the first design had wrong, all worth
keeping in mind:

1. **A 2-of-2 stub is not a complete year.** `months_total` counts months
   inside the *requested range*, so grading against it called a two-month stub
   at a range edge "complete". Grading is against twelve; the text tells the
   two causes apart, because months never asked for are not missing data.
2. **A month nobody ever observes is not this year's problem.** The generator
   — and Sentinel-2 — return nothing for Jan, Feb or Dec in *any* year.
   Measuring bias against a "true twelve-month mean" estimates the error from
   a baseline carrying the same error. The baseline is now a typical year of
   this factor as the record can measure it, and the dataset-wide hole is
   reported separately with the conclusion that actually follows: no year is a
   true annual mean, but the years are comparable with each other.
3. **It has to survive the print.** A printed page has no tooltips, so severe
   years are named in prose beneath the table.

### Four rainfall factors are real

`ea_hydrology.py`, against the EA Hydrology API — keyless, so it works on the
deployed URL. Monthly total, heaviest day, wet days, dry days, from one gauge
lookup and one readings query.

**They are new factors, not the existing precipitation ones.** `precip_total`
hangs off HadUK-Grid, a 1 km gridded areal product; a gauge is a point. Over a
20-hectare site those answer different questions and for an area the gridded
one is usually better, so these sit beside it named "(gauge)" under their own
base. Serving gauge readings under HadUK-Grid's provenance would be the exact
mislabel `audit_catalogue.py` exists to catch.

Details that matter: the API's `dist` search is a filter and not an ordering,
so results are re-sorted by true distance; readings flagged `Missing` or
`Invalid` are dropped, because a broken gauge reads zero and zero is also the
most common true value; a part-covered month reports the fraction it managed
rather than being scaled up.

Real coverage 46 → 50 of 273.

**What was deliberately not built, and why it matters more than what was.**
`spi_3month` needs a gamma fit per calendar month; a z-score of three-month
totals is not SPI and they disagree most in the dry tail the index is for. The
EA's flood zones, abstraction and water stress need WFS typenames that could
not be confirmed from this sandbox, and BLOCKERS §2's rule applies — a factor
registered against an endpoint that cannot answer it claims real data in the
UI and then fails on every request. Six factors that 404 forever would have
made the coverage figure look better than the product. `BLOCKERS.md §7` is new
and carries the one curl command that unblocks all six.

### Three bugs found by carrying the coverage work outward

Doing the same reasoning in a second place is what surfaced these. Each was
found by running something, not by reading.

**`/api/ask` reported a missing autumn as a trend.** `nlq.py` never looked at
`months_observed`, and a trend is the difference between two endpoints, so a
short endpoint turns a coverage gap straight into a reported change. Seven
identical years of a seasonal factor plus a current year holding January to
August produced "Air temperature rose from 10.00 °C in 2019 to 10.87 °C in
2026 (9%)" — for a series with no trend in it whatsoever. The existing noise
floor cannot catch this: a stable series has a noise floor of zero, so any
artefact clears it, which means the steadier the factor the more reliably the
artefact is narrated. Ask the question any time before December and the
current year is short.

Years too thin to compare with their neighbours are now set aside, and named
in the answer. The test is **relative to the series** — Sentinel-2 never sees
a January, so an absolute twelve-month threshold would decline every question
about vegetation in the catalogue.

**Every fallback blamed Earth Engine.** "Earth Engine failed, showing demo
data" was true when Earth Engine was the only real source and stopped being
true when `open_data` landed. The registry now holds Earth Engine, five
open-data hosts and the EA API, so the message was sending people to check
credentials for a service that had never been called. Found by exercising the
new EA factors, which fail on every request from here and reported a Google
problem.

**The frontend contradicted itself about NDVI.** Grading against a flat twelve
marked every NDVI year "severe" — nine months is its maximum — and greyed out
the entire column, while the caveat on the same cell said the years were
comparable with each other. A factor's full year is twelve minus the months it
never observes. That fix exposed a second one: the dataset-wide fact was being
repeated on every row when it belongs to the column, so it now appears once
beside the factor's name.

`insights.py` was checked for the same class of bug and is clean — it fits a
line over monthly points rather than comparing annual endpoints, and the
seasonal variance inflates the standard error enough that an unbalanced tail
cannot trip the t-test. Verified by construction rather than assumed.

### A documentation contradiction, two days old

`BLOCKERS.md §4` and `docs/DEPLOYMENT-STATUS.md` both still said there was no
Vercel account and no live URL. The deploy landed 2026-08-05; those were
written 2026-08-04 and nobody came back to them, while `HANDOFF.md` on the
same page said the opposite. Both now say what happened and when, kept as
history rather than deleted.

Not re-verified from here — `vercel.com` is behind the same proxy block as
everything else, so this records what the deploy session reported.

### Still blocked, unchanged

Every upstream is still unreachable (`curl` to all six returns `000`). So the
two things that need a human are exactly what they were: send the ESA licence
email, and run `check_open_data.py`, `ons.job --check` and now
`check_environment_agency.py` somewhere with ordinary internet. Of 50 real
factors, exactly one — NDVI — has ever met its live service.

---

## 2026-08-05 (second pass) — Phase 2, and the gaps the brief still had

Went back through the brief looking for what was genuinely missing rather than
what was already built. Three things were, all in Phase 2.

### Rate limiting (`ratelimit.py`)

There was none, and the API is public, unauthenticated, and calls upstreams
with quotas shared across every user. One script in a loop could spend an
Earth Engine budget that belongs to everybody.

A cost-weighted sliding window per client. Costs are per route because the
routes are not comparable — `/api/catalog` is a cached dictionary at 0.5,
`/api/series` can be twenty-four upstream calls at 6.0. Charging them equally
either throttles browsing or fails to throttle work.

Three decisions worth recording:

- **Sliding window, not a token bucket.** A bucket lets a client spend its
  allowance instantly and then starve, which for an interactive map means the
  fourth shape you draw fails while you watch. A window degrades more gently.
- **Rejected requests are not counted.** Otherwise a client already over the
  limit holds itself over by retrying, turning a one-minute limit into a
  permanent ban.
- **Tracked clients are bounded.** `X-Forwarded-For` is forgeable, so an
  unbounded map of clients would make this middleware the memory exhaustion it
  exists to prevent.

**What it does not do:** the counters live in the process, so on Vercel the
effective limit is per instance, not per deployment. That makes it a guard
against one client hammering one instance, not a global budget. A real budget
needs shared state (Redis, Vercel KV) — a dependency and an account, for a
service with no users yet. `DEPLOY.md` already makes the same argument about
the response cache. Documented rather than dressed up, as the brief asks.

### Staged loading (`LoadingSequence.tsx`)

A frozen "Reading the site…" for eight seconds reads as broken; the same eight
seconds narrated reads as work. The stages are the real ones in the order the
backend performs them, and the sequence holds on its last message rather than
implying completion — the response arriving is the only thing that knows when
it is done. Past nine seconds it says the data source is slow, because at that
point that is more useful than another verb.

### Debouncing (`store.ts`)

Aborting an in-flight request already stopped answers arriving out of order,
but the request had still been *sent* — toggling three factors fired three
round trips, two of which the server did the work for and nobody read. Now
coalesced over 180ms, below the ~250ms where a delay starts to feel like lag.

Implemented with a generation counter rather than a cleared timeout: clearing
a pending timeout leaves its promise permanently unresolved, which quietly
leaks one per keystroke.

### Latency profile — and why the numbers below are not the real ones

Measured locally, 4 factors x 180 months, draw to report:

| | median |
| --- | ---: |
| uncached | 31 ms |
| cached | 31 ms |
| `/api/ask` | 8 ms |

Against targets of 8 s uncached and 2 s cached, that looks like a rout. It is
not, and the number should not be quoted. **This measures `series.py`, the
generator** — the sandbox proxy blocks Earth Engine and all five open-data
hosts, so nothing here touched a network. The real cost of a real factor is
one upstream round trip, and the honest profile needs a machine with open
egress. That, not the arithmetic, is the slow step.

What the measurement does establish: nothing in the app's own request path —
geometry validation, 180-month generation, annual rollup, the cell grid — is
anywhere near the budget. Any latency a user sees is upstream.

### Mobile

Checked at iPhone 13 viewport in a real browser rather than by reading CSS: no
horizontal overflow, tool rail usable, report panel present as a bottom sheet,
viewport meta correct.

### Not attempted, and why

Phase 5's monitoring/alerts, AR mode, multiplayer cursors and cross-site
pattern mining all need something this product does not have — accounts,
persistence, a scheduler, or usage volume. Building any of them now would add
a subsystem with no user. Phase 5's confidence overlays are the best next
candidate: the data already carries `months_observed` and `confidence`, so it
is a rendering job rather than a new pipeline.

---

## 2026-08-05 — Phase 0 inventory, and natural-language querying

### Orientation: the brief describes an older product

The improvement brief describes a Leaflet frontend, `ee-backend/app.py`, a
"Contour" brand on near-black with a gold accent, and `site-scanner.html` as
the live app. None of that is current, and the brief itself says to verify
rather than assume. What is actually here:

| Brief says | Actually |
| --- | --- |
| Leaflet frontend | React + MapLibre GL (`web/`), vector basemap |
| `ee-backend/app.py` | `app.py` at repo root; `mock_ee_backend.py` is the credential-free twin |
| `site-scanner.html` is the app | Kept for reference only; superseded by `web/` |
| Near-black + gold `#D9A83C` | Repaletted — see `BRAND.md`; the gold was deliberately dropped |
| "Year slider, partial" | Full 180-step monthly timeline with scrubbing and sparklines |

Several Phase 1–4 items were already done before this session: the cache layer
(`cache.py`, keyed on geometry hash + factor + range), CSV/PDF-style export
(`web/src/lib/exports.ts`), compare mode (`Compare.tsx`), permalink round-trip
(`lib/permalink.ts` with tests), boundary upload, anomaly-style callouts
(`insights.py`), and CI (`.github/workflows/ci.yml`).

### The single most important fact: what is real

Measured, not estimated — `scripts/audit_catalogue.py` and the registries in
`routes_catalog.REAL_SERIES`.

| | Count | Notes |
| --- | ---: | --- |
| Factors in the catalogue | 269 | `catalog.py`, 44 bases |
| Have a real implementation | **46** | 17% of the catalogue |
| — Earth Engine | 24 | `ee_series.FACTOR_COVERAGE` |
| — Open data | 22 | `open_data.py`: planning.data.gov.uk, Land Registry, police.uk |
| Return generated data | 223 | `series.py`, labelled `source: "generated"` everywhere |

**On the deployed URL, only the 22 open-data factors can be real.** The 24
Earth Engine factors need `app.py`, a service account and a container; the
Vercel function deliberately excludes `app.py` and `ee_series.py` because
`earthengine-api` will not fit a serverless bundle. Cloud Run is blocked on
Google requiring a billing account before Cloud Run, Cloud Build or Artifact
Registry can be enabled at all — see `DEPLOY.md §0`. Nothing in this repo can
work around that.

Only **1** factor is marked `verified` rather than `written` (NDVI, checked by
hand against live Earth Engine). The other 45 are implemented and unit-tested
but have not been confirmed against the live upstream. `scripts/check_open_data.py`
and `python3 -m ons.job --check` are what turn `written` into `verified`, and
both need ordinary internet — this sandbox's proxy blocks the upstreams.

Eleven Sentinel-2 factors carry a licence warning: `sentinel2_sr` is recorded
as CC BY-SA 3.0 IGO with `commercial="verify"`, and share-alike on a commercial
derived product would be a real constraint. `docs/licensing/DECISION-LOG.md`
has the branches. Still unresolved.

### Built this session: natural-language querying

The brief calls this "the single highest-differentiation feature". It did not
exist — no `/api/ask`, no query input, nothing.

`nlq.py` parses a question against the catalogue and answers it **from the
series**, not from a language model. That ordering is the whole design:

- The parser picks factors and a time range from the question text.
- The answer is computed arithmetically from the returned annual rollups.
- A model, when `ANTHROPIC_API_KEY` is set, only ever *rephrases* an answer
  that was already computed. It is never asked what the numbers are.

So the deployed URL — which has no API key — gives real answers, and a wrong
model cannot invent a number. This matches the rule the project already holds
for `/api/summary`: `generated_by` says who wrote the prose, and the prose is
constrained by data either way.

Refusals are part of the feature. The answer says so when the underlying
factor is generated, when the year range has no observations, and when a
change is too small relative to the year-to-year spread to be worth calling a
trend. Narrating noise would be the easiest way to make this feature
impressive and useless.

### Decisions and trade-offs

**Deterministic parsing over model-based routing.** A model would parse more
phrasings, but it cannot run on the deployed URL, and a feature that only
works with a key is a demo. Token-overlap scoring against factor name, group
and synonyms covers the phrasings in the brief's own example ("has tree cover
dropped near this site since 2019?"). The model path is an enhancement, not a
dependency.

**Answers use the annual rollup, not the monthly series.** Monthly values
carry seasonality that swamps a trend — a February-to-August comparison is a
season, not a change. The rollup already handles partial years and carries
`months_observed`, which the answer uses to caveat itself.

### What I would do next

1. Resolve the Sentinel-2 licence question. An hour of reading, and it gates
   commercial use of 11 factors.
2. Run `scripts/check_open_data.py` somewhere with ordinary internet — that
   moves 22 factors from `written` to `verified`, or names which integrations
   are wrong. Expect some URLs to have moved.
3. Earth Engine on Cloud Run, once billing exists. The image builds and serves;
   only billing is missing.

### Risks worth knowing

- The open-data factors call third-party APIs at request time. They are cached,
  but a slow upstream is a slow response, and `data.police.uk` in particular is
  not fast.
- Earth Engine remains registered non-commercial. `TECHNICAL_PLAN.md §8.9` and
  `BLOCKERS.md` cover the mitigation (ingest-then-store), which is built but
  unused.
