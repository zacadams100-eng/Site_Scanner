# Handoff — Site Scanner

Written at the end of the session that took the app from 4 real Earth Engine
factors to 24, repalletted the interface, and set up automated verification.

Branch: `claude/accessible-gis-web-app-tktvmz`
Repo: `zacadams100-eng/Site_Scanner` (public)

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

**Roughly two thirds of the catalogue is still generated demo data, and the
app says so on every screen.** 24 of ~118 factors return real satellite
observations. The rest are plausible-looking numbers from `series.py`.

This is deliberate and must stay visible. Every response carries a `source`
field of `earth-engine` or `generated`, the Sources tab says *"Demo data —
generated, not observed"* where it applies, and the badge in the top bar
counts live factors. A half-real catalogue is honest; pretending it is
uniformly one or the other is not.

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
| `catalog.py` | Single source of truth: 20 bases, ~118 factors, licences, attribution |
| `ee_series.py` | Real Earth Engine queries, grouped so siblings share one pass |
| `routes_catalog.py` | API contract, mounted by both real and mock backends |
| `series.py` | The generator that stands in for unbuilt factors |
| `mock_ee_backend.py` | Credential-free backend; keeps frontend work unblocked |
| `web/src/index.css` | Three-layer token system and the elevation ladder |
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
