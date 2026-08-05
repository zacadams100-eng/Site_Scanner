# Handoff — Site Scanner

Branch: `claude/site-scanner-improvements-pfiz4b`
Repo: `zacadams100-eng/Site_Scanner` (public)
Tests: 391 passing, 10 skipped (they need a Postgres server) · 46 frontend

---

## Read this first

**Three things need you, not another coding session.** Each is minutes of
work and each unblocks something no amount of code can:

1. **Send the ESA/Copernicus email** — `docs/licensing/email-copernicus-sentinel-2.md`.
   Fill in a name and send. It is the cheaper of the two licence questions and
   it may make the Google one unnecessary.
2. **Run `vercel login && vercel deploy --prod`.** Everything else is built and
   verified locally; this is one command and then the site has a URL.
3. **Run the two check scripts anywhere with normal internet:**
   `python3 scripts/check_open_data.py` and `python3 -m ons.job --check`. The
   first promotes 22 factors from "written" to "verified" — or tells us which
   integrations are wrong. The second finds which ONS release URLs have moved,
   which some of them will have.

`BLOCKERS.md` has the detail on all of these, plus the honest arithmetic on
why real coverage is 21% rather than the 50% that was asked for, and which
eight sources would actually close that gap.

---

## What changed in the last session

Nine commits, in order:

| | |
| --- | --- |
| `5183237` | 22 factors made real from UK open data — planning designations, Land Registry prices, police.uk crime. No key, no quota. |
| `1c79289` | Both licence emails drafted, with the architectural consequence of every possible reply decided in advance. |
| `912ebc5` | The ingest pipeline run for real over Surrey and benchmarked end to end. |
| `993c5ed` | Every claim of "real" audited, two mislabels fixed, and the ratio drawn in the factor browser. |
| `e4c7377` | Continuous rasters stored as scaled int16 rather than float32 — 0.29x the bytes. |
| `408c778` | The ingest runner tiles, and a national backfill resumes per tile. |
| `6e9abd5` | ONS spreadsheets ingested on a schedule and served from disk. |
| `b03ef80` | The app now reads the report for you, and refuses to overclaim doing it. |
| `df9b07d` | The printed report became a document you could send to a client. |

The two at the end were not asked for. They are what I would build next if it
were my product, and they are described under "Findings" and "The printed
report" below.

---

## What this is

A satellite-backed site-analysis tool for England. You draw an area on a map,
and it returns 15 years of monthly measurements for that exact shape —
vegetation, temperature, land cover, rainfall — as a table, charts and a
timeline you can scrub.

The premise it is built on was measured, not assumed: `BENCHMARK.md` proved a
15-year series for a real AOI returns in 1–50 ms from pre-aggregated storage,
against tens of seconds when queried live from Earth Engine. That gap is the
whole architecture.

---

## The single most important thing to know

**Most of the catalogue is still generated demo data, and the app says so on
every screen.** 46 of 269 factors return real observations — 17% today, 21%
once the ONS job has run. Exactly one of them, NDVI, has ever been checked
against a live service. The rest are plausible-looking numbers from
`series.py`.

This is deliberate and it must stay visible. Every response carries a `source`
of `earth-engine`, `open-data` or `generated`; real factors carry provenance
naming the service that answered and whether anyone has run it; the factor
browser draws the ratio as a bar; and every automatically generated sentence
about a demo factor says "demo data — generated, not observed" **inside the
sentence**, so no layout can drop it.

`scripts/audit_catalogue.py` and `tests/test_catalogue_audit.py` enforce all
of that in CI. A mislabel does not crash — a number just quietly acquires
authority it has not earned — so a test is the only thing that catches one.

Do not "tidy this up" by removing the labels.

---

## State of play

### Working and verified against real Earth Engine
- NDVI — verified by hand, twice, including a false success that had to be
  caught (see below).

### Working, correct-by-construction, verified in CI
23 further factors across four groups. See `ee_series.py`:

| Group | Factors | Coverage |
| --- | --- | --- |
| Sentinel-2 indices | 11 — NDVI, EVI, SAVI, MSAVI, GNDVI, NDMI, NBR, NDBI, NDWI, bare soil, chlorophyll | 2017-03 onward |
| ERA5-Land monthly | 4 — air temperature, soil moisture, evapotranspiration, humidity | full range |
| ERA5-Land daily | 4 — temp max/min, frost days, growing degree days | full range |
| MODIS thermal | 3 — LST day, night, diurnal range | full range |
| ESA WorldCover | 2 — dominant class, tree cover % | 2020 and 2021 only |

### 22 more factors are real without any credentials

`open_data.py` reads UK government open data over plain HTTPS: 11 planning
designations from planning.data.gov.uk, 7 market factors from one Land
Registry Price Paid SPARQL query, 4 from data.police.uk. No key, no quota, no
Earth Engine — so they work in the credential-free backend and in the
serverless deployment too. Six EPC factors register themselves as soon as
`EPC_API_EMAIL` and `EPC_API_KEY` exist.

That takes the catalogue to 46 real of 269 (17%). **None of the 22 have been
run against the live endpoints** — this environment's proxy denies all five
hosts — so they are marked `written`, not `verified`, and that distinction is
carried through `/api/catalog` into the UI. `scripts/check_open_data.py`
promotes them on any machine with open egress. Read `docs/OPEN-DATA.md` before
quoting any of these numbers as real.

### ONS comes from a scheduled spreadsheet job

ONS publishes rents, earnings, affordability and the census as spreadsheets on
a release page, not as an API with per-area endpoints — so there was nothing
for a live client to call. `ons/job.py` downloads each release, `ons/parse.py`
reads it, `ons_store.py` serves it from disk at request time, and
`.github/workflows/ons-refresh.yml` runs it monthly and commits what changed.
No network and no database on the request path, so it works in the serverless
deployment too.

Most of the work is in the parsing, because these files are laid out for a
person and change shape between releases: the header row is found by a label,
the area column by looking for `E07000209` in its values (ONS names that
column four different ways across five files), and `:`, `x`, `..` and `#` are
all read as gaps rather than zeros. A file that parses to nothing raises —
that is the one outcome that looks like a successful refresh while emptying a
factor.

Eight factors, plus two nobody publishes: `rental_growth_yoy`, and
`gross_yield` — annual rent over sale price, combining the stored ONS rent
with the live Land Registry median, which is the number a residential investor
actually asks for.

**The release URLs have never been fetched** and ONS rotates them. Run
`python3 -m ons.job --check` first and expect to fix some.

### The ingest tier tiles, resumes and stores int16

A national run at 10 m is 3.6 billion pixels per timestep and could not happen
in one pass. `ingest/tiling.py` cuts any extent over 25 M pixels into a grid —
England is 154 tiles, 27,720 tile-timesteps — and progress is recorded per
`(dataset, timestep, tile, h3_res)` in the same transaction as that tile's
rows, so a killed backfill resumes at the tile it reached. The schema now lives
in `ingest/migrations/` with a small runner (`python3 -m ingest.migrate`),
because the old inline CREATE TABLE IF NOT EXISTS could not add a column.

Tiling's real hazard is not memory, it is the seams: a cell on a tile boundary
is aggregated once per tile it touches, and overwriting rather than merging
would leave every tile edge in the country holding a sliver's average. Cell
rows carry pixel counts and a sum of squared deviations so partials combine
exactly; a merged row is indistinguishable from a single pass, checked in
Python, in SQL, and end to end through a real database.

Continuous rasters are stored as int16 scaled by the manifest's `storage.scale`
rather than float32 — 0.29x the bytes, and the scale is written into the COG so
QGIS and GDAL unscale it themselves. `ingest/cog.py:read_band` is the only way
anything here reads a band; calling `src.read(1)` on a quantised COG gets
values 10,000x too large with no error.

`docs/INGEST-BENCHMARK.md` is re-measured against all of this.

### The real/generated split is audited and shown

`scripts/audit_catalogue.py` checks every factor the catalogue calls real:
that it exists, that it names both a publisher and the host actually queried,
that it declares whether anyone has ever run that host, and that its licence
and attribution are recorded. `tests/test_catalogue_audit.py` runs the same
checks in CI, because a mislabel does not crash — a number just quietly
acquires authority it has not earned.

It found two things worth fixing. Earth Engine factors named ESA and NASA as
the source without saying the numbers come through Earth Engine, which does
the cloud masking and compositing — a user going to the Copernicus Data Space
would get a different number. And eleven designation factors were attributed
to Natural England and Historic England while actually being served by
planning.data.gov.uk. Provenance now carries publisher and endpoint
separately; all 46 real factors differ between the two.

The factor browser shows the ratio as a bar: real against generated, split
into verified and written. Today that reads 46 of 269 (17%), of which one —
NDVI — has been checked against a live service. A written factor's dot is
hollow rather than filled.

### The app reads the report for you

`insights.py` turns 2,160 numbers into a handful of sentences, ranked, and the
report opens on them:

> Land surface temp in November 2025 was 28.2 °C, 3.1 standard deviations
> above the usual November of 23.2 °C — the highest November in the record.

It looks for trends, seasonal anomalies, step changes, static designations and
poor coverage. Most of the work is in what it refuses to say, and those guards
are the part to preserve if this is ever refactored:

- **Generated data never produces an unlabelled claim.** The caveat is in the
  sentence, not a sibling field.
- **Carried-forward values never produce a trend.** A census figure held
  across 144 months is a perfectly flat, perfectly significant series.
- **Noise never gets narrated.** A trend needs |t| ≥ 2; a test runs 60
  pure-noise series and asserts at most 8 are narrated.
- **A step change must beat a straight line,** not merely split the data —
  otherwise every trending factor collects a spurious "shifted up around 2018".
- **Trends are quoted from the fitted line, not the end points.** On a
  seasonal series those are a March and a November, which produced "rose 122%"
  for a temperature series with no trend in it at all.

None of it is a model and none of it predicts. Every statement is arithmetic
over observations already on screen, and each carries the numbers it came from.

### The printed report is a document, not a table

Export → *Printable report / PDF* now produces something you could send to a
client: the site as a map image captured from the live canvas with the
boundary and markers drawn on it, the findings, the annual figures, and the
licence notices.

It also carries an **About this report** panel stating how many factors are
real, how many findings came from demo data, and which service answered each
real factor. This is the copy that leaves the building — the last place the
real-versus-generated split can be allowed to go missing.

Two details make the map work and are easy to lose:
`canvasContextAttributes.preserveDrawingBuffer` on the map (without it
`toDataURL` returns a blank image), and the 3:2 crop around the boundary in
`lib/mapImage.ts` (without it the page is mostly empty countryside with the
site the size of a stamp).

### The interface was rebranded

It is now a light, quiet, instrument-like interface: paper ground, moss
sidebar, one instrument blue used only for "here, now", IBM Plex Sans / Inter /
IBM Plex Mono with mono reserved for measurement, and a proper frame — 64px top
bar, 280px collapsible sidebar, map, report panel, 28px status bar carrying
coordinates, scale, zoom, CRS, cell count and connection state.

`BRAND.md` records the specification and where each rule lives. The old dark
canvas with copper accents and backdrop blur is gone; do not reintroduce blur,
heavy shadows or gradients, and keep colour at roughly 95% neutral.

### The catalogue now serves more than one profession

269 factors across 25 groups and 44 bases. The first half is what the land is
like — vegetation, terrain, climate, water, habitat. The second half is what
can be done with it and at what risk: planning and consents, property market,
buildings and fabric, infrastructure, transport and access, community and
services, ground risk, energy, agriculture, forestry and carbon, siting and
logistics.

Every new base carries the same provenance, licence and attribution as the
old ones, and almost all of them are `stored=False` — a planning register or
an EPC lookup is an API call, not a raster we hold, so the storage argument in
TECHNICAL_PLAN.md §8.2 is untouched (22 stored bases, 7 monthly).

46 of the 269 are real today and every one of the rest is labelled. Do not
remove the labels; the answer is to implement more of them, and BLOCKERS.md §2
lists the eight sources that would take it past half.

### The map has its own cartography

`scripts/build_basemap.py` bundles coastline, urban areas, water, motorways,
railways and place names from Natural Earth (public domain) into
`web/public/basemap/england.json` — 600 KB, styled to the brand, no network
needed. The OSM raster now fades in above zoom 10 for detail rather than being
the only thing on the canvas.

Place labels are DOM markers, not a symbol layer: MapLibre needs a glyph server
to render text, and standing one up to write "Guildford" on a map is the wrong
trade.

### Added since
- **Place search.** A postcode, place name or pasted `lat, lng` moves the map.
  Until then the only way to reach a field was to pan across England on an
  unlabelled basemap, which made the drawing tools unreachable for anyone who
  did not already know where they were. Lookups go to postcodes.io (ONS/OS
  open data, OGL — notice shown with the results); coordinates are parsed
  locally and never leave the browser. Searching moves the map and nothing
  else: guessing a boundary from a place name would be exactly the invented
  precision this project refuses everywhere else.
- **Saved sites are workspaces.** Shape, factors and timeline position, with
  rename, overwrite, and backup/restore to a file. Entries saved before this
  restore the shape alone, as they always did.
- **The catalogue says which factors are real.** `/api/catalog` marks each
  factor `real`, and the browser can filter to just those — the honesty label
  now arrives before the query rather than after it.
- **A drawn area can be moved and resized.** Drag inside it, or drag a corner.
  Redrawing was the only adjustment before, which is cheap for a rectangle and
  destroys a hand-traced outline. The camera deliberately does not refit after
  an edit; it still does after a fresh draw.
- **Comparison is reachable and exportable.** "vs a year ago" pins the same
  month twelve steps back — shift-clicking the track, the only route before,
  is not something anyone discovers — and the change table exports as CSV
  carrying the panel's rules with it.
- **Dead ends removed.** A failed query offers to retry rather than requiring
  the area to be redrawn, and the timeline date is clickable as a month field.
- **The layout was driven on a tablet and a phone for the first time**, which
  found the drawing tools sitting underneath the report sheet on a phone —
  the entire point of the app, behind a panel.
- **`/api/series` is cached per factor.** Adding a factor used to re-run every
  Earth Engine query already on screen. One short browsing session against a
  six-live-factor backend measured 18 hits to 6 misses.

### Not built
- No deployment. It runs in Cloud Shell; there is no public URL for the real
  app. `DEPLOY.md` has the Cloud Run and Vercel steps, untried.
- No accounts, and no persistence beyond `localStorage` — saved sites are
  per-browser, which is why they can now be exported to a file.
- The ingest pipeline (`ingest/`) works on synthetic rasters only. Nothing has
  been ingested for real, so the fast H3 path is unused in production.

---

## How to run it

```bash
cd ~/Site_Scanner
source ./setup.sh          # must be `source`, not ./setup.sh
```

`setup.sh` builds a venv, installs dependencies, finds the service account key
by globbing `~/ee-backend/*.json`, and reads the project id from `gcloud`.
Nothing is hardcoded — the repo is public.

Then, in two Cloud Shell tabs:

```bash
uvicorn app:app --port 8000        # tab 1
cd web && npm install && npm run dev   # tab 2
```

Web Preview → change port → **5173**. Both halves must be on the same machine;
a browser on your laptop cannot reach a backend in Cloud Shell.

Verify the data layer at any time:

```bash
python3 scripts/check_real_factors.py 2024
```

---

## Hard-won lessons — read before changing the data layer

Each of these cost real time and is easy to reintroduce.

**A tick is not a verification.** The first real NDVI run returned 0.37–0.46
for every month of 2024 and printed `✓ Real NDVI is working`. The only numeric
test was that values fell inside −1..1, which a pipeline averaging unmasked
cloud passes comfortably. Any check must test the *shape* of the data —
seasonality, spread — not just its bounds.

**Flat is not always broken.** Chasing that flat NDVI turned out to be a badly
chosen test field, not a bug: a box near Guildford mixing roads at 0.14 with
evergreen at 0.75 in fixed proportion really does average 0.42 every month.
`scripts/diagnose_ndvi.py` exists to separate "the code is wrong" from "the
land is like that" — it runs the same code over intensive arable, which has
the strongest seasonal swing in England.

**Pixel counts are not area.** `reduceRegion` works in the image's projection,
and a composite built through `ee.Algorithms.If` has none, so Earth Engine
falls back to EPSG:4326 where a "10 m" pixel is 10 m tall but 10/cos(latitude)
m wide. Counts came back inflated by ~1.6× over England, so `valid_fraction`
always clamped to 100% and cloudy midwinter months claimed perfect coverage.
Coverage is now summed from `pixelArea()`, which is projection-independent.

**Never average a class code.** Halfway between Grassland (30) and Cropland
(40) is Built-up (50). Categorical factors reduce with `frequencyHistogram`
and resolve to the modal class. `catalog.py` marks these `kind='categorical'`.

**Never interpolate a gap.** A month with no usable observation returns
`value: None`. Sentinel-2 starts in March 2017, so 74 of 180 months are blank
for every S2 factor — that is the correct answer, not a bug to paper over.

**Approximation is worse than absence.** Four Sentinel-2 indices the catalogue
declares are deliberately *not* implemented: greenness, wetness and brightness
need published tasselled-cap coefficients, and leaf area index needs a
validated canopy model. Inventing them would produce numbers that look right
and are not.

---

## Things that will bite you

**MapLibre's worker fails silently in production.** It requests
`/assets/maplibre-gl-worker.mjs` at runtime, which Vite never emits because
the reference is computed. The SPA catch-all rewrite returns index.html with a
200, so there is no console error and no map error event — only
`isSourceLoaded: false` forever and a blank map. Fixed by copying the worker
and its `maplibre-gl-shared.mjs` dependency verbatim into `public/maplibre/`
(`web/scripts/copy-maplibre-worker.mjs`) and calling `setWorkerUrl`. Do not
"simplify" this to a `?url` import; that copies one file without its
dependency graph.

**MapLibre's stylesheet loads after ours** and wins the specificity tie on
`.map-canvas`, collapsing the container to zero height and swallowing every
pointer event. The `.app .map-canvas` selector is load-bearing.

**AOI size limit is 250,000 ha** (`routes_catalog.py`). Larger returns 400.
Earth Engine would time out long before that anyway.

**The repo is public.** `redaction.py` strips credentials from anything headed
for a log, a browser or CI, because Earth Engine embeds the credentials dict in
some error messages and `routes_catalog` puts error text in the API response.
Nothing formats an exception from the Earth Engine path without
`safe_message()`.

---

## CI

`.github/workflows/ci.yml`, two jobs:

- **Tests** — pytest, vitest, TypeScript. No credentials, runs on every push.
- **Real data** — runs `check_real_factors.py 2024` against live Earth Engine
  using repository secrets `EE_SERVICE_ACCOUNT_JSON` and `EE_PROJECT_ID`.
  Missing secrets warn rather than fail.

The second job exists because every Earth Engine query in this repo was written
without being able to reach Earth Engine, and that gap already produced one
silent failure that passed its own check.

The key belongs to a throwaway project (`sitescanner-verify`) with no billing,
separate from the production project, and can be deleted without consequence.

---

## Open decisions, still unanswered

1. **What "project management" means.** Saved workspaces — name a site, reopen
   it, everything comes back — now exists, in the browser only. Real PM with
   tasks, deadlines and assignees is months and a different product, and the
   step in between is accounts and server-side storage, which is what turns a
   per-browser list into something a team can share. Still parked.

2. **Whether commodity trading belongs in this product at all.** Property and
   construction are things *at places*. Commodity trading is about flows
   *between* places, which fights a draw-an-area interface. It probably wants
   its own view, or its own product.

3. **How loudly to flag a caveat.** A year built from fewer than 12 months is
   marked with a `·` and a tooltip. That caveat now survives into every export,
   but a dot may still be too quiet for something that makes a row
   non-comparable. Worth deciding once and applying everywhere.

---

## Commercial blockers, not yet resolved

**Earth Engine is registered non-commercial.** Selling a product built on it
requires a commercial licence. `TECHNICAL_PLAN.md` §8.9 flags this; the
mitigation is the ingest-then-store architecture, where Earth Engine derives
products in batch and users are served from our own storage. That path is built
but unused.

Both licence questions now have emails drafted and waiting to be sent, in
`docs/licensing/` — one to Google about the batch-derivation pattern, one to
ESA about which licence Sentinel-2 actually carries. Send the ESA one first;
it is cheaper and it may make the Google one unnecessary.
`docs/licensing/DECISION-LOG.md` decides in advance what to do for every
possible reply, so nobody re-argues the architecture when one arrives. The
standing conclusion across all six branches: ingest-then-store is mandatory in
four of them and merely advisable in the other two, so `ingest/` is the real
architecture and the on-request Earth Engine path is a prototype that survived.

**Sentinel-2's licence is recorded as CC BY-SA 3.0 IGO and flagged
`commercial="verify"`** in `catalog.py`. Share-alike on a commercial derived
product would be a real constraint, but Copernicus data is generally
distributed under terms permitting commercial reuse with no share-alike. One of
those is wrong and it matters which.

**Attribution is now carried** — every base has the exact notice its licence
requires, and it travels into the UI and every export. Showing a licence name
is not the same as meeting its condition, and the app was doing the former.

---

## Where to look

| File | What it holds |
| --- | --- |
| `catalog.py` | Single source of truth: 44 bases, 269 factors, licences, attribution |
| `ee_series.py` | Real Earth Engine queries, grouped so siblings share one pass |
| `routes_catalog.py` | API contract and the per-factor series cache, mounted by both backends |
| `web/src/store.ts` | One store; `timeIndex` is the only source of truth for "when" |
| `web/src/lib/places.ts` | Postcode, place-name and coordinate lookup, with its OGL notice |
| `web/src/lib/exports.ts` | Every way data leaves: CSV, Excel, GeoJSON, print, saved-site files |
| `web/src/components/MapCanvas.tsx` | Drawing, editing, cell painting — and every MapLibre trap |
| `open_data.py` | 22 live open-data factors, and what each source cannot answer |
| `ons/` + `ons_store.py` | The scheduled spreadsheet ingest and the store it writes |
| `insights.py` | What the numbers say, in sentences — and the guards that keep it honest |
| `ingest/` | The raster pipeline: manifests, tiling, migrations, H3 aggregation |
| `scripts/audit_catalogue.py` | Checks every claim of "real"; runs in CI |
| `BLOCKERS.md` | Everything that needs a human, and why |
| `series.py` | The generator that stands in for unbuilt factors |
| `mock_ee_backend.py` | Credential-free backend; keeps frontend work unblocked |
| `web/src/index.css` | Three-layer token system, the frame, every component rule |
| `BRAND.md` | The brand spec and where each rule lives in the code |
| `TECHNICAL_PLAN.md` | Architecture and the reasoning behind it |
| `BENCHMARK.md` | The measurements the design rests on |
| `DESIGN_SPEC.md` | Feature spec and UI plan, with the open questions in §0 and §8 |

---

## Working style that produced this

The user is a university student (Environment & Sustainability, graduating
2027), not a professional developer. What worked:

- Explain fixes plainly, give the exact command, say what success looks like.
- **Verify by running things, not by reasoning about them.** Nearly every real
  bug in this project was found by executing something — a benchmark, a
  screenshot, a diagnostic — and missed by reading the code.
- Screenshots from the user were the highest-signal input available. Two
  separate bugs were diagnosed from them that had been read past in source.
- Short vague reactions ("I don't like the gold", "make it milder") were more
  productive than specifications.
