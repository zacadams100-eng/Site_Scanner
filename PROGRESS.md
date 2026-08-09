# Progress log

A running log, appended to each session. Newest entry at the top. Nothing here
is overwritten, so the history of what was true when stays visible.

---

## 2026-08-09 (second pass) — The number moved

**1 → 9 verified.** It had been 1 since NDVI.

The user ran `scripts/verify.py` from Google Cloud Shell, which has ordinary
outbound internet, and pasted the report back. This is the first time any of
this catalogue has been checked against reality since the project started.

### What came back

**21 of 24 open-data checks passed**, with real figures: median sale price
£425,000, 32 transactions, crime density 230 per km², burglary 5.0 per km².
Nine factors promoted, each recorded in `open_data.VERIFIED` with the value
that was observed — a date and a tick is not a record.

**The flood-zone attribute passed.** `flood-risk-type` is the real name. That
was the riskiest unverified guess in the repository: taken from a published
schema, never seen live, and if wrong the app was at risk of reporting 0% flood
risk on a floodplain. It is right.

### Three of the four failures were not what they looked like

**`price_change_yoy` and `price_growth_5yr` — "every point is a gap".**
Arithmetically correct, wrong question. They derive from 13 and 61 months of
history and the check asked for six, so every point was a legitimate gap. The
check now reports "not testable in this window" and names the `--months` value
that would test it.

**ONS: two moved, three rate limited.** 404 for `private_rents` and `imd_2019`
— genuinely need new URLs. 429 for the other three, which is ONS asking us to
slow down, not a dead link. The check reported all five as FAIL, which would
have sent somebody hunting for replacement links that were never lost. It now
backs off, retries, spaces the requests, and reports `SLOW` separately.

**Earth Engine was never tested at all.** It reported a red failure that was
really a setup step: `verify.py` looked for `EE_SERVICE_ACCOUNT_JSON` and a key
file, found the key file, decided credentials were present and ran — but
`app.py` reads `GOOGLE_APPLICATION_CREDENTIALS_JSON`, which was not loaded. It
now checks the variable the app actually reads and says `source ./setup.sh`.

So the honest scoreline of the first run is **one real problem found (two dead
ONS URLs), one guess confirmed, nine factors verified, and three false alarms
in my own tooling** — which is roughly what a first run should look like.

### The mistake I made while writing the guard against it

I wrote a comment saying "only add to this from an actual run… must never be
written from optimism", and in the same edit added `avg_sale_price` to the
verified list. It was not in the captured output. It is in the same group as
four that passed and it almost certainly works, and "almost certainly" is not
the standard. Removed.

The cause was mine too: `verify.py` kept only the last 14 lines of each check,
so the eleven planning designations and both flood factors scrolled off the
report entirely. A reader could not tell whether they had passed, failed or
never run — the one thing the report exists to say. It now keeps the whole
output, trimming from the middle if it must.

`tests/test_catalogue_audit.py` had a test asserting no open-data factor
claims `verified`, with a docstring saying it should be "updated deliberately,
not discovered to be failing" if anyone promoted them. That is exactly what
happened. It now guards the new invariant instead: a factor may only claim
`verified` if it is in `open_data.VERIFIED`, and every entry there must record
a figure that was actually seen.

`docs/OPEN-DATA.md` carries the full log.

### The planning run: 12 of 13 "passed", and the number is misleading

**Only three were promoted.** `conservation_area_pct` came back 53.3%,
`scheduled_monument_pct` 0.9%, `green_belt_pct` 0.8% — real measurements that
prove the query finds and clips real entities. The other ten returned **0.0**.

That is the correct answer for a Guildford site with no SSSI on it. It is also
exactly what a **misspelled dataset name** returns, because `planning_series`
reports no-entities-found as zero coverage. The two are indistinguishable from
outside, so a run that only ever saw zero has confirmed the code path and
established nothing about whether we asked for the right dataset.

Promoting all twelve would have been the third overclaim of the day. Instead,
`check_open_data.py` now marks an all-zero result `~ok`, says why, and names an
AOI that would settle it — the South Downs, where national park and AONB have
to be non-zero.

### And a real bug, which is what a live run is for

`brownfield_register_pct` died with
`TypeError: object of type 'float' has no len()`. The brownfield land register
publishes **points**, not polygons, and every fixture in the test suite was
written as a polygon — so `_coverage` reached `len()` on a coordinate. Three
weeks of green tests could not have found this.

Fixed to **raise rather than skip**. Filtering the points out and returning 0.0
was the easy repair and would have said "no brownfield land on this site" on
the strength of not knowing how to read the answer. Raising falls back to the
generator, which labels itself demo data — the same rule as the flood-zone
attribute.

**Verified: 1 → 12.** Still to settle: nine designations that need a
non-empty test area, `avg_sale_price`, and the two derived price factors that
need a 72-month window.

523 passing, 10 skipped.

---

## 2026-08-09 — Attacking the bottleneck instead of adding to it

51 factors real, **1 verified**, and that number has not moved since NDVI.
Every session — including the last four passes — added correctly-written,
well-tested, never-run integrations. The pile of `written` grows and
`verified` does not, and the reason was never that the verification was hard.
It was that it was *scattered*: four scripts, four sets of output, four
judgements, and no single answer to the only question that matters.

So this session added no factors.

### `scripts/verify.py`

One command. Runs the open-data check, the flood-zone attribute check, the ONS
URL check and Earth Engine, prints one scoreboard with an explicit next action
against each failure, and writes `verify-report.md` — a file that can be pasted
straight back into a session, because results sitting in a closed terminal are
worth nothing and re-typing "police.uk returned a 500" from memory is how a
real finding becomes a vague one.

**Exit 2 means "nothing could be checked", not "everything failed."** The
difference is load-bearing: reporting a train journey as twelve broken
integrations is how a wasted trip becomes a to-do list of imaginary bugs.

### It immediately found a real bug, which is the point

`scripts/check_open_data.py` called `open_data.locate(args.lon, args.lat)`.
`locate` takes a geometry. The script crashed with a `TypeError` on the first
line of real work, printed a plausible-looking `FAIL locate` and exited 1 — so
**it could never have reached a single endpoint**, and it looked like a broken
integration rather than a broken caller.

That script has been the headline recommendation in `HANDOFF.md` for several
sessions. Anyone who had made the trip to a machine with open internet would
have run it, seen a failure, and learned nothing. Fixed.

A second one, in code written yesterday: `discover_planning_datasets.py
--attributes` reported "no such dataset on the platform" when it simply could
not reach the platform. `main()` had a test for exactly that conflation;
`show_attributes` did not. Both paths now exit 2 and say so, and the test
covers both.

### `docs/USER-TESTING.md`

The other half of the gap. Everything in this product has been built from
inference about what a land agent wants; that inference has never been checked.
Six questions, twenty minutes, no preparation, and one measurement that matters
more than the rest — **how many seconds until they draw a shape**, because
drawing is the entire interaction and if it takes more than about thirty
seconds to discover, nothing else on the backlog is the top priority.

It also records four predictions in advance, so they can be wrong on the record
rather than confirmed in hindsight. `docs/user-tests/` is empty, which is
currently the most informative thing in the repository.

518 passing, 10 skipped.

---

## 2026-08-07 (fourth pass) — Surface water, and the loading state

### JRC Global Surface Water: three more real factors

`water_occurrence`, `water_seasonality` and `water_change` were generated, and
the catalogue already named JRC Global Surface Water as their base at 30 m.
48 → 51 real of 269 (19%).

Chose Earth Engine over an Environment Agency HTTP endpoint deliberately. The
EA spatial layers would have meant guessing at ArcGIS service URLs that cannot
be reached from here to check, adding to a pile of 47 written-but-never-run
factors. These go through the registry `scripts/check_real_factors.py` already
walks, so **the CI job with Earth Engine credentials verifies them without
anybody remembering to** — which is the difference that mattered.

The design decision worth keeping is the split between JRC's two products.
`GlobalSurfaceWater` is one static image summarising 1984–2021; those are
long-baseline statistics with no annual value. `YearlyHistory` is per-year. So
seasonality and change are served static and flagged carried-forward, and only
occurrence varies year to year. Spreading a static statistic across fifteen
years as though it were measured each one would manufacture a trend out of a
constant — the failure `insights.py` already guards against for carried-forward
census figures — so the carried-forward flag is load-bearing and tested.

Two rules carried over from earlier mistakes in that file: extent is summed
from `pixelArea` rather than counted, because a pixel count is a count in
whatever projection the reduction lands in and that inflated coverage 1.6x over
England once already; and a year with no usable classification is a gap, never
0%, because reporting no water is the claim that the site is dry.

### The loading state was narrating a guess

Driven in a browser with the response held for twelve seconds, which is the
only way to see it — locally it returns in about 30 ms, which is why nobody
had ever looked at it.

What was there: one line of grey 12.5px text, centred in a panel 700 px tall,
changing every few seconds on a timer. **It looked frozen** — nothing moved
between stage changes, so for two-second stretches it was indistinguishable
from a dead page, the exact failure its own docstring said it prevented. And
**it was narrating a guess**: "Rolling months into years…" appeared at 2.5
seconds whether or not any months were being rolled.

It now shows what the app actually knows, which turns out to be plenty — which
layers were requested, which are real, and which host each real one reaches:

> 2 of 4 are live sources, and those are the ones taking the time.
> NDVI (vegetation vigour) · demo data
> Flood Zone 3 coverage · planning.data.gov.uk

Past nine seconds it names the host rather than saying "the data source is
slow", because a hostname is something a person can act on.

**The temptation resisted** is ticking rows off one at a time. `/api/series` is
one POST returning every factor at once, so the client never learns that NDVI
has landed and precipitation has not — a row filling in on a timer would be the
same lie in a nicer coat. A test asserts the copy never implies per-factor
progress. Per-factor progress needs the server to stream.

### The bigger flaw underneath it

Driving the real flow — add a layer to a report you are already reading —
showed that `loading` hid `data` even when data was present. **Adding a fifth
factor blanked the four you were reading**: the app taking away the answer it
had already given in order to say it was working.

A refetch now keeps the previous report and puts a thin strip above it, saying
the figures below are from the last query. Only a first query gets the full
skeleton. Verified by driving the factor browser: the fifteen-year table stays
readable throughout.

Reduced motion is honoured — animations off, content identical, checked by
emulating the media query rather than by reading the CSS.

The copy lives in `lib/loading.ts` with 20 tests, because the wording is a
claim about what the app is doing and this project does not let a claim go
untested for being small and grey.

502 Python passing, 102 frontend (up from 85).

---

## 2026-08-07 (third pass) — Flood risk made real, and guessing made measurable

Picked the highest-value unblocked work while the user was away: everything at
the top of `BLOCKERS.md §2` needs either their key (EPC), their billing
(Earth Engine) or open internet (the check scripts), but the Planning Data
Platform is already integrated and fixture-tested here.

### `flood_zone2_pct` and `flood_zone3_pct` are real

The single most-referenced factor in the whole template set —
`flood_zone3_pct` appears in five of the twenty-seven templates — and it was
generated. It is also the regulatory screening factor the strategy doc's item 4
is about, and the one a developer checks before buying land.

Both come from the platform's `flood-risk-zone` dataset, which is one dataset
and two factors: Zone 2 requires a flood risk assessment, Zone 3 risks a
sequential-test refusal, and they cannot share a number. So `planning_series`
grew a `field`/`values` filter. **Without it both factors measure every
returned feature and report an identical figure** — which a reader would not
question, because Zone 3 genuinely is a subset of Zone 2 and two similar
numbers look right. The test for this fails at `assert 50.0 > 50.0` when the
filter is removed, which is what it is for.

Real coverage 46 → 48 of 269.

### The dangerous part, and what was done about it

The attribute name `flood-risk-type` comes from the platform's published schema
and **has never been seen in a live response**. The obvious implementation
treats "no feature matched the filter" as "no Zone 3 here" — so a wrong
attribute name would make the app report **0% flood risk, confidently, on a
floodplain**. That is the worst failure available in `open_data.py`: it is
silent, it is on the factor with the most consequence attached, and it looks
exactly like good news.

So the filter now checks the attribute *exists* before trusting a non-match,
and raises when it does not. `_series_for` catches that and falls back to the
generator, which labels itself demo data. Wrong and labelled beats wrong and
authoritative.

### `scripts/discover_planning_datasets.py`

The platform publishes many more datasets, several of which map onto factors
still being generated. Which ones, under what names, is a question about a live
service — and this repo has a standing rule against answering those from
memory (`BLOCKERS.md §3`: "Guessing at them would have produced five specs that
fail on every run").

So the candidates are listed but **not registered**, each carrying an honest
confidence — `documented`, `likely` or `guess` — and one command on ordinary
internet turns the list into an answer, printing a block ready to paste into
`PLANNING_DATASETS`. Guessing becomes measuring for the price of a script.

Its first job is smaller and more urgent:

```
python3 scripts/discover_planning_datasets.py --attributes flood-risk-zone
```

prints the attribute names the platform really returns, which either confirms
`flood-risk-type` or says exactly what to change it to.

The script distinguishes "we asked and it does not exist" from "we could not
reach the platform", and exits 2 rather than 0 for the second — because
conflating them produces a confident list of datasets to delete, generated by a
network outage. There are tests for that distinction specifically.

488 passing, 10 skipped.

---

## 2026-08-07 (second pass) — Item 11 measured, and it does not pass

Asked to test item 11, the user-contributed library of environmental
assessments — the data network effect. The context doc is explicit that the
anonymisation design must be settled before the upload mechanic is built, so
this is a measurement, not a feature: `experiments/eia_library/`, imported by
nothing, mounted on no route.

`experiments/eia_library/FINDINGS.md` is the write-up.
`python3 -m experiments.eia_library.report` prints the numbers.

**Test A — stripping identifiers from EIA text.** 30.8% of identifiers survive
on held-out passages, at 100% retention of the findings. The residue is not
random: bare settlement names (`Guildford`) need a gazetteer, and client-name
variants (`BHSE`, `Bloor's`, after the full company name was correctly removed
from the header) cannot be caught by any pattern, because recognising `BHSE` as
a client requires knowing who the client is.

Twice, the mechanism protecting the *valuable* content punched a hole in the
redaction. Species binomials were protected by shape — capitalised word then
lowercase word — which matched `Homes ownership` and `Hartley and`, and a
protected span blocks every redaction rule, so the false species match shielded
the client name behind it. The fix used Latin epithet endings including `-e`,
`-a` and `-is`, which are also the endings of a large share of ordinary
English, so `Road frontage` parsed as a species and shielded the site name.
Both looked correct while reading the code and were caught only by measuring.
The general form is worth keeping: **the protection mechanism and the redaction
mechanism are adversaries**, and every exception carved out to save the ecology
is a doorway an identifier walks through.

**Test B — the geometry, which is worse.** Rounding a boundary to ~1 m leaves
100% of sites matchable to their own original; fuzzing only anonymises at
~111 m, by which point a 0.3 ha parcel has no shape left. Generalising to an H3
cell needs resolution 6 — 36 km² — before a site hides among fifteen. Expressed
without depending on the synthetic population: for a 74 ha cell to hide one site
among five, EIA'd sites would have to occur about seven times per square
kilometre, everywhere.

So the library can answer "what habitats are typical around here", not "what is
on this site".

**Three things the doc does not mention, and one of them is a blocker.**
Protected-species locations are themselves sensitive — the NBN Atlas blurs
badger setts and great crested newt ponds because publishing them enables
persecution — so a findings library is partly a map of where the protected
species are, which anonymising the client does not fix. Contributor attribution
and client anonymity are in tension, since a consultancy's client list is often
on its own website. And an EIA is commissioned work that is generally the
client's property, so a consultant may have no right to upload it at all. That
last one is the same shape as the Sentinel-2 licence question: cheap to ask,
expensive to get wrong, and nobody here can answer it.

**What the feature could be instead** is in FINDINGS.md. The load-bearing change
is publishing structured records rather than documents — extract a typed record
and never pass prose through, so the schema is the safety boundary rather than a
regex, because a field of type `habitat_type` cannot contain a developer's name.

Two of the CI tests are deliberately inverted: they assert the redactor still
fails. If somebody improves it enough to pass, that is a real result and the
findings document is out of date, and a failing test is the right way to be told.

**Not tested:** whether enough public-sector EIAs exist in machine-readable form
to seed the library, which is the other thing that decides viability. The
sandbox proxy refuses every host that could answer it.

---

## 2026-08-07 — The three moat items, made real

Worked from the competitive context doc, which says to default to items 1–3
(speed, accessibility, shareability) when a call is not obvious, because those
are the structural moat and the rest only matters if they hold. Three things
were claimed rather than true.

### The shared link was dropping data (item 3)

The doc calls a URL that reconstructs a whole analysis a structural moat, and
sets the bar at "does this survive a fresh page load from a pasted link" as a
hard requirement. It did not. Markers and the site's name were held in the
store and saved into workspaces, but never encoded — so sending someone an
annotated site sent them the shape and silently discarded every note on it,
and the site arrived as an unnamed rectangle.

Worse, `permalink.ts` had **no test file at all**, despite `HANDOFF.md` listing
"permalink round-trip (`lib/permalink.ts` with tests)" as already done.

Both fields now encode, every marker mutation syncs the URL, and there is a
`permalink.test.ts` with 16 tests. The one worth keeping is the completeness
guard: it walks `URL_STATE_KEYS`, clears each field in turn, and fails naming
any field that decodes the same with and without it. Adding a field to
`UrlState` without teaching the encoder about it now breaks the build on
purpose. Verified by deleting the marker encoder and watching it fail with
`these UrlState fields do not survive a shared link: markers`.

Two details that took a second attempt:

- **The marker separators are `;` and `,` specifically because
  `encodeURIComponent` escapes both.** The obvious choices — `~`, `*`, `!` —
  are all left untouched by it, so a marker called "north gate; by the oak"
  would have worked in testing and broken on the first real user.
- **Marker ids are reissued by position rather than carried.** They are local
  handles for React keys, never seen outside one browser, and spending URL
  length on a timestamp buys nothing.

Driven in a real browser from a pasted link: the name and both markers come
back.

### Latency was never measured (items 1 and 10)

The doc says to treat a response-time regression as a P0 and to instrument
from day one so speed is measurable rather than assumed. Nothing measured the
request a user actually waits on. `/api/series` reported a per-factor
`elapsed_ms`, which is the upstream call, not validation plus fan-out plus
rollup plus serialisation.

`telemetry.py` now times every `/api/*` request on both backends, emits
`Server-Timing` (which devtools plots for free) and `X-Response-Time`, writes
one structured JSON line per request, and serves the distribution at
`/api/metrics` — a real endpoint returning structured data, per item 7, not a
debug page that has to be rebuilt when the first integrator asks for it.

Decisions worth recording:

- **Percentiles, not averages.** A mean hides the tail and the tail is the
  experience. A test drives 99 requests at 20 ms and one at 10 s and asserts
  the p50 stays 20 and the max stays 10,000.
- **A rejected request is still timed.** Installed outside the rate limiter, so
  a 429 is measured. Otherwise a limiter that had started refusing everything
  would show up as a sudden, flattering improvement in latency.
- **Bounded on both axes** — 512 samples per route, 64 routes. A caller probing
  `/api/<random>` would otherwise turn the instrumentation into the memory leak.
- **`sampled_from` is in the payload**, saying "per-instance, not
  per-deployment", because the figure most likely to be misquoted is the one
  read straight off an endpoint by somebody who never opened the file.
- **No client address, no geometry, no question text** in the log line. A
  latency log is a poor place to start keeping records of who asked what about
  which piece of land, and two tests assert it stays that way.

`tests/test_docker_context.py` caught the new module missing from the
Dockerfile — exactly the failure it was written for.

### The map claimed more certainty than it had (item 8)

The table has greyed poorly-observed numbers for a while. The map painted every
cell at uniform opacity, so a December mean scraped from 26% cloud-free
coverage rendered exactly as solidly as a clear May — on the artefact people
screenshot and paste into a report.

Colour still means value; opacity now means confidence, from the month's
`valid_fraction`. Three things that matter:

- **A floor of 0.35, never zero.** A thin month still has a value, and hiding
  it would replace an honest weak reading with the appearance of no data,
  which is a different claim and a false one.
- **Square root, not linear.** Perceived opacity is markedly non-linear, and a
  linear ramp made everything below about 0.5 look equally washed out —
  collapsing the distinction the overlay exists to draw.
- **The paint expression multiplies.** Each cell carries `alpha`; the overlay
  slider sets `['*', ['coalesce', ['get','alpha'], 1], overlayOpacity]`.
  Writing a bare number there, as the slider used to, silently discards every
  cell's confidence the first time it is touched. There is a test for it.

The timeline chip changed from a binary "low confidence" below 0.4 to
`26% observed`, shown for `fair` as well as `poor`. A map that goes pale with
no stated cause reads as a rendering fault.

Checked in a browser at two months of the same site: May 2019 paints solid
with no chip, November 2025 paints washed out with an amber `26% observed`.

### Not attempted, and why

**BNG pre-screen (item 4), the highest-value item on the list.** The catalogue
has `bng_units_available`, `bng_uplift_potential` and `priority_habitat_pct`
and a Biodiversity net gain template that selects them — and every one of those
factors is `series.py` output. Building a compliance screen on generated
numbers would attach the product to a legal deadline and answer it with
invented data, which is the one thing this repo has consistently refused. It
needs the Natural England / DEFRA priority-habitat and Environment Agency work
in `BLOCKERS.md §2` first. That is the real prerequisite, and it is a data job
before it is a feature.

**Monitoring (item 6) and the shared EIA library (item 11)** both need accounts
and server-side storage, which do not exist. Item 6's advice — make "saved
sites" and "changes since last check" first-class in the data model now — is
worth taking, but a saved site is still a `localStorage` entry, so there is no
model to put it in yet.

**Export counts** are not in `/api/metrics`. Exports happen entirely in the
browser, so counting them means a beacon endpoint, which is a privacy decision
rather than a coding one. The counter mechanism is there when that is settled.

### Test counts

455 Python passing, 10 skipped (Postgres). 85 frontend passing, up from 59 —
the 26 new ones are the permalink round trip and the confidence rendering.

(The commit message for this session's first batch says 465. It is wrong; the
figure was never verified against a summary line, only against a screen of
dots. 455 is the counted number.)

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
