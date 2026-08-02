# Site Scanner — Technical Plan

A plan for turning the current prototype into an accessible, time-first GIS
application. Written against the code that exists today (`site-scanner.html`,
`app.py`, `mock_ee_backend.py`, `cache.py`, `summary.py`), not from a blank page.

---

## 0. Where the project actually stands

Worth being explicit, because it changes what "build this" means:

| Required feature | Status today |
| --- | --- |
| 1. Centralised data storage | **Partial, and not what the spec says.** `app.py` proxies live Earth Engine calls per request. The user downloads nothing — good — but nothing is *stored* either. Every request re-computes. |
| 2. Timeline / timescale tool | **Partial.** A year slider (2016–2026) with play/pause exists and debounces at 250 ms. It is annual-only, and each step costs a live `reduceRegion`. |
| 3. Drawing tools | **Done, and genuinely good.** Rect / circle / freehand are hand-rolled on Leaflet with touch support, and they feel right. Keep this. |
| 4. Automatic attribute table | **Does not exist.** The report panel renders a score and a prose note, not a table. |
| 5. Automatic graph generation | **Does not exist.** No charting at all. |

So features 4 and 5 are greenfield, feature 1 needs an architecture it currently
doesn't have, and feature 2 needs to get roughly 50× faster to feel like the
product being described. Feature 3 is close to finished.

---

## 1. The one decision that determines everything else

Everything in the brief hangs on one sentence: *"scrub through temporal data and
instantly update the map view."*

Right now, moving the slider one year triggers a Sentinel-2 composite and a
`reduceRegion` on Earth Engine's servers. That is **2–10 seconds** for a modest
AOI, longer for a big one. No amount of frontend polish hides that. A 15-year
scrub at that cost is 30–150 seconds of waiting, which is exactly the experience
you are trying to escape from.

There are three ways out, and you should pick deliberately:

**(a) On-demand, optimised.** Keep computing per request, but against your own
Cloud-Optimised GeoTIFFs (COGs) instead of Earth Engine, with windowed reads and
parallel fan-out across years. Realistic latency: **150–600 ms per year**, all 15
years in parallel in under a second for AOIs below ~50 km². Degrades on large AOIs.

**(b) Fully precomputed.** Pre-aggregate every variable to a fixed spatial
tiling (H3 hexagons, or admin units) for every timestep, and store it in Postgres.
A drawn AOI becomes `SELECT ... WHERE h3 IN (...) GROUP BY year` — **10–50 ms for
the whole 15-year series**. Instant. But answers are snapped to the tiling, so a
drawn field boundary is approximated by the hexagons it overlaps.

**(c) Hybrid — recommended.** Precomputed H3 answers the moment the shape closes,
so the timeline, table and charts populate instantly with a visible "approximate"
badge. An exact windowed-COG job runs in the background and swaps the numbers in
1–3 seconds later, badge flipping to "exact". The user never waits, and never
gets misled about precision.

The hybrid is more work than either pure option, but it is the only one that
delivers the actual promise. **Plan for (b) first, add (a) as the refine pass,
and present it as (c).** Everything below assumes this.

---

## 2. Recommended tech stack

### Frontend

| Choice | Why |
| --- | --- |
| **React 18 + TypeScript + Vite** | `site-scanner.html` is 43 KB of inline everything, and it is at its ceiling — adding a data grid and a chart engine to it will not end well. Vite keeps dev startup near-instant. TypeScript matters here specifically because GeoJSON, unit-carrying stats and time-indexed records are exactly the shapes that rot silently in plain JS. |
| **MapLibre GL JS** (replacing Leaflet) | The hard requirement is smooth scrubbing. Leaflet redraws DOM/canvas per layer per frame — the existing `repaintYear()` loops `NX × NY` rectangles and calls `setStyle()` on each, which is the wrong shape for 60 fps. MapLibre keeps raster and vector on the GPU, supports **cross-fading two raster sources** (the trick that makes time scrubbing look continuous rather than steppy), and is BSD-licensed with no Mapbox billing. |
| **terra-draw** (or port the existing hand-rolled tools) | terra-draw is map-library-agnostic and has clean rect/circle/freehand/polygon modes. That said, your current drawing code is one of the better parts of the prototype — if porting it to MapLibre is under a day, port it and keep the exact feel. Do not adopt `mapbox-gl-draw`; its UX is developer-grade, which is the thing you're trying to avoid. |
| **TanStack Table v8** | Headless — you own every pixel, which matters when the target is "feels like Excel". Handles virtualisation, column sizing, sorting, grouping and pinning for 100k+ rows without a rewrite. |
| **Observable Plot** for auto-charts, **ECharts** if you later need interaction-heavy views | Plot is a grammar of graphics: you describe *"x is time, y is value, colour is series"* and it picks sensible scales and axes. That is precisely the API you need when the chart is chosen by code rather than by a human. Chart.js is the wrong fit — it wants you to name the chart type up front, which is the decision you're trying to automate away. |
| **Zustand** for state | The state graph here is small but cross-cutting (AOI, time index, active layers, table selection, chart selection). Redux is ceremony; prop-drilling through map + table + charts is worse. |
| **Tailwind + Radix primitives** | Radix gives accessible sliders, popovers, tabs and dialogs unstyled; Tailwind gives you the tactile Procreate-ish surface without a component library fighting you. Accessibility here is not optional — a time slider that is keyboard-operable and screen-reader-labelled is a genuine differentiator over ArcGIS Pro. |
| **DuckDB-WASM** (phase 2) | Lets the attribute table run real SQL — filters, joins, group-bys, window functions — entirely in the browser over the Arrow payload you already sent. This is how you get "Excel, but it doesn't fall over at 50k rows" without a server round-trip per keystroke. |

### Backend

| Choice | Why |
| --- | --- |
| **Keep FastAPI + Python** | Already working, already tested, and Python is where the geospatial libraries actually live (`rasterio`, `rio-tiler`, `xarray`, `geopandas`, `shapely`, `h3`). Switching to Node would cost you the entire raster ecosystem for no gain. |
| **TiTiler** (`rio-tiler`) | Dynamic XYZ tiles straight from COGs on object storage, with rescaling and colormaps as URL params. Replaces `getMapId()` on the request path. Crucially it makes tile serving *yours* — no Earth Engine quota between your user and their map. |
| **PostgreSQL 16 + PostGIS 3.4 + TimescaleDB** | PostGIS for geometry, Timescale for the aggregate hypertable. Timescale's continuous aggregates and native compression are the difference between a 15-year table that queries in 20 ms and one that queries in 2 s. |
| **pgSTAC + stac-fastapi** | A STAC catalogue is the standard way to answer "which assets cover this AOI at this time". It also gives you a documented, boring path to adding new datasets later — and interop with QGIS and every other STAC client, which matters for user trust. |
| **Object storage (GCS or S3) + COGs** | COGs give HTTP range reads: pull the 200 KB you need for one AOI out of a 2 GB raster without downloading it. This *is* the "no downloads" promise, implemented. |
| **Redis** | Fixes the limitation already documented in `README.md` §Caching — the current cache is per-process, so Cloud Run instances don't share it. Redis makes the cache shared, and doubles as the job broker. |
| **Cloud Run Jobs + Cloud Tasks** (or Celery if you prefer) | Ingest and backfill are long-running batch work; keep them off the request path entirely. |
| **Earth Engine — demoted to an ingest source** | Keep `app.py`'s EE code, but move it behind the ingest pipeline: EE computes and exports a derived product, you store it, users hit your storage. This removes EE latency and quota from the user path — and sidesteps the licensing issue in §8. |

### What to keep from the prototype

`mock_ee_backend.py` and the `tests/` suite are more valuable than they look.
The pattern of "a mock backend that serves identical shapes, with a header saying
which one answered" should be preserved and extended to every new service. It is
the reason you can build frontend and data pipeline in parallel.

---

## 3. Data and pipeline architecture

### 3.1 Storage tiers

```
┌─ Tier 0: Source ────────────────────────────────────────────────┐
│ Earth Engine · Copernicus/AWS Open Data · EA flood zones ·      │
│ HM Land Registry PPD · PVGIS · OS Boundary-Line                 │
└───────────────────────────┬─────────────────────────────────────┘
                            │  ingest jobs (batch, idempotent, versioned)
┌─ Tier 1: Object storage ──▼─────────────────────────────────────┐
│ COGs, one per (variable, timestep, tile)                        │
│ gs://scanner-data/ndvi/2024/06/S2_NDVI_2024-06_30TXQ.tif        │
│ Indexed by a STAC catalogue in pgSTAC                           │
└───────────────────────────┬─────────────────────────────────────┘
                            │  zonal aggregation jobs
┌─ Tier 2: Postgres ────────▼─────────────────────────────────────┐
│ H3-cell aggregates (the "instant" tier) + vector features       │
│ + user AOIs, projects, saved views                              │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌─ Tier 3: Redis ───────────▼─────────────────────────────────────┐
│ Tile URLs, AOI stat results, in-flight job dedup                │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Core schema

```sql
-- Dataset registry: every number in the UI must trace back to a row here.
CREATE TABLE datasets (
  id              text PRIMARY KEY,        -- 'ndvi_s2', 'landcover_esa'
  name            text NOT NULL,
  unit            text,
  kind            text NOT NULL CHECK (kind IN ('continuous','categorical')),
  native_res_m    numeric NOT NULL,
  temporal_step   interval,                -- '1 month', '1 year', NULL = static
  valid_from      date,
  valid_to        date,
  source_name     text NOT NULL,
  source_url      text NOT NULL,
  licence         text NOT NULL,
  class_map       jsonb                    -- categorical code -> label + colour
);

-- The instant tier. H3 res 8 ≈ 0.74 km² per cell — a reasonable balance
-- between fidelity for a drawn field and row count for a country.
CREATE TABLE cell_stats (
  h3              bigint NOT NULL,
  dataset_id      text   NOT NULL REFERENCES datasets(id),
  t               timestamptz NOT NULL,
  mean            real,
  min             real,
  max             real,
  stddev          real,
  valid_fraction  real NOT NULL,           -- fraction of pixels not cloud/nodata
  class_counts    jsonb,                   -- categorical only
  PRIMARY KEY (h3, dataset_id, t)
);
SELECT create_hypertable('cell_stats', 't', chunk_time_interval => INTERVAL '1 year');
ALTER TABLE cell_stats SET (timescaledb.compress,
  timescaledb.compress_segmentby = 'dataset_id, h3');

-- User work. This is what makes the tool feel like a workspace, not a viewer.
CREATE TABLE aois (
  id          uuid PRIMARY KEY,
  user_id     uuid NOT NULL,
  project_id  uuid REFERENCES projects(id),
  name        text NOT NULL,
  geom        geography(Polygon, 4326) NOT NULL,
  draw_method text CHECK (draw_method IN ('rect','circle','freehand','upload')),
  created_at  timestamptz DEFAULT now()
);
CREATE INDEX ON aois USING GIST (geom);
```

`valid_fraction` is not optional decoration. Without it, a cloudy month reads as
a genuine NDVI crash and your users make bad decisions. It should surface in the
UI (see §6.5 and §7.7).

### 3.3 Ingest pipeline

Each dataset gets a declarative manifest, and one generic runner executes them:

```yaml
# ingest/manifests/ndvi_s2.yaml
id: ndvi_s2
kind: continuous
unit: NDVI
source:
  driver: earthengine
  collection: COPERNICUS/S2_SR_HARMONIZED
  expression: "(B8 - B4) / (B8 + B4)"
  cloud_mask: {band: SCL, exclude: [8, 9, 10]}
temporal: {step: 1 month, from: 2016-01, to: now}
spatial:  {aoi: uk_bbox, resolution_m: 10, crs: EPSG:27700}
outputs:
  - {type: cog,        path: "ndvi/{yyyy}/{mm}/"}
  - {type: cell_stats, h3_res: 8}
```

Pipeline stages: **fetch → mask → composite → reproject → COG-ify → upload →
STAC-register → zonal-aggregate → mark ready**. Each stage idempotent and keyed
by `(dataset, timestep, tile)` so a failed backfill resumes rather than restarts.

Run the backfill once (15 years × 12 months is 180 jobs per dataset — a weekend
of batch compute, not a research project), then a monthly cron for new data.

### 3.4 The two query paths

**Fast path** — fires the instant the shape closes:

```sql
WITH cells AS (SELECT h3_polygon_to_cells($1::geometry, 8) AS h3)
SELECT t, dataset_id,
       sum(mean * valid_fraction) / nullif(sum(valid_fraction), 0) AS mean,
       avg(valid_fraction) AS confidence
FROM cell_stats JOIN cells USING (h3)
WHERE dataset_id = ANY($2) AND t BETWEEN $3 AND $4
GROUP BY t, dataset_id ORDER BY t;
```

Whole 15-year series, every active layer, one round trip, tens of milliseconds.

**Exact path** — queued immediately after, results streamed back over SSE:

1. STAC search for assets intersecting AOI × time range.
2. Fan out one task per timestep; `rasterio.mask` windowed read + `rasterstats`.
3. Emit `{t, dataset_id, mean, ...}` per timestep as it lands, so the chart
   sharpens progressively rather than blocking on the slowest year.
4. Cache the completed series in Redis, keyed by `(geohash(AOI), datasets, range)`.

Reuse `cache.py`'s `cache_key()` shape here — the hashing approach is sound, it
just needs Redis behind it instead of a dict.

---

## 4. Frontend component breakdown

```
<AppShell>                        Procreate-style: tools float over the canvas
├─ <MapCanvas>                    MapLibre; owns nothing but rendering
│  ├─ <RasterTimeLayer>           two sources + opacity cross-fade
│  ├─ <DrawLayer>                 rect / circle / freehand
│  ├─ <AOIOverlay>                committed shapes, selection, vertex handles
│  └─ <MapHUD>                    scale bar, coords, "12 of 15 years loaded"
│
├─ <ToolDock>                     left rail. Icon-first, ≤7 items, tooltips
│  ├─ <DrawToolGroup>             rect · circle · freehand · upload
│  ├─ <LayerStack>                drag-reorder, opacity sliders, blend modes
│  └─ <BasemapSwitcher>
│
├─ <Timeline>                     bottom bar — the signature component
│  ├─ <TimeScrubber>              draggable head, keyboard ←/→, snap to steps
│  ├─ <DataAvailabilityStrip>     per-timestep bar: dark = good, faded = cloudy
│  ├─ <SparklineTrack>            AOI's series drawn *inside* the timeline
│  ├─ <PlaybackControls>          play/pause, speed, loop
│  └─ <RangeSelector>             brush two handles to define a comparison window
│
├─ <DataPanel>                    right side — the "Excel" half. Resizable.
│  ├─ <TabBar>                    Table · Charts · Summary · Sources
│  ├─ <AttributeTable>            TanStack; row-mode switch (§6.4)
│  ├─ <ChartStack>                auto-generated, reorderable cards
│  ├─ <SiteNote>                  existing /api/summary output
│  └─ <ProvenancePanel>           dataset, resolution, licence per column
│
└─ <CommandPalette>               ⌘K — power users get speed without menu depth
```

**State (Zustand, one store, four slices):**

```ts
interface AppState {
  aoi:   { current: Feature | null; saved: AOI[]; drawMode: DrawMode | null };
  time:  { index: number; steps: Date[]; playing: boolean; range: [number, number] | null };
  data:  { layers: LayerConfig[]; series: Record<DatasetId, TimeSeries>;
           precision: 'approx' | 'exact' | 'loading' };
  view:  { panelWidth: number; activeTab: Tab; selectedRows: RowId[] };
}
```

The critical rule: **`time.index` is the single source of truth.** Map, timeline,
table and charts all subscribe to it; none of them own a copy. Every "the chart
and the map disagree" bug comes from violating this.

---

## 5. UI direction — what "Procreate meets Excel" means concretely

Since this is a stated goal rather than a vague aesthetic, it's worth pinning down:

- **The map is the canvas, not a widget in a frame.** Full-bleed, edge to edge.
  Panels float above it with backdrop blur and shadow. No chrome around the map.
- **Tools are icons on a floating rail**, radius-heavy, with a clear pressed
  state and a one-line hint on hover — which the prototype already does well
  (`#hintText`).
- **Gestures over dialogs.** Drag to draw. Drag the panel edge to resize. Drag
  the timeline. Scroll to zoom. Right-click for context, never a modal for a
  routine action.
- **The table half is unapologetically dense.** Monospace numerals
  (`font-variant-numeric: tabular-nums`), right-aligned numbers, sticky headers,
  zebra rows, real column resize handles. Do not "design" this half — Excel's
  conventions are load-bearing, and users' hands already know them.
- **Every panel is dismissible.** The path from "landed on the page" to "drew a
  shape" must be under five seconds with nothing in the way.
- **One accent colour.** The prototype's `#DDAE5C` amber against desaturated
  greens is good — keep it, and reserve saturated colour for data, never chrome.

---

## 6. Feature-by-feature implementation

### 6.1 Centralised data storage

- Ship with a **fixed catalogue of ~8 curated datasets** rather than "any dataset".
  Curation is the product; an empty dataset picker is ArcGIS's problem restated.
  Suggested launch set: NDVI (S2, monthly, 2016–), land cover (ESA WorldCover,
  annual), surface water (JRC), elevation + slope (SRTM/LIDAR, static), land
  surface temperature (MODIS/Landsat, monthly), precipitation (CHIRPS, monthly),
  built-up area (GHSL, 5-yearly), flood zones (EA, static vector).
- **Store derived products, not raw imagery** (see §8.2 — the storage maths is
  decisive here).
- Every dataset carries a `datasets` row; nothing renders in the UI without
  provenance attached to it.
- Serve tiles via TiTiler from your COGs. Users never see an external hostname.

### 6.2 Timeline / timescale tool

This is the feature that has to feel exceptional, so it gets the most detail.

**Rendering.** Hold two MapLibre raster sources. Scrubbing sets opacity on both
(`t` and `1-t`) so intermediate positions cross-fade rather than flash. Prefetch
`index ± 2` tiles at idle priority so ordinary scrubbing hits warm cache.

```ts
// Cross-fade, not swap. This is what makes scrubbing feel continuous.
function setTimePosition(pos: number) {
  const i = Math.floor(pos), frac = pos - i;
  map.setPaintProperty(`layer-${i}`,   'raster-opacity', 1 - frac);
  map.setPaintProperty(`layer-${i+1}`, 'raster-opacity', frac);
}
```

**Timeline as data display, not just a control.** Once an AOI exists, draw its
series as a sparkline *inside* the timeline track, with the availability strip
beneath. The user sees the whole 15-year story before touching anything, and the
scrubber head becomes a read-head on a chart they can already see. This single
detail does more for "fast and intuitive temporal analysis" than any other.

**Playback.** Replace the prototype's `setInterval(900)` with
`requestAnimationFrame` and continuous interpolation — stepping integer years on
a timer is what makes the current version feel like a slideshow rather than film.

**Accessibility.** Native `<input type="range">` under the custom visuals (Radix
Slider does this for you): arrow keys step, Home/End jump, PageUp/Down jump a
year, `aria-valuetext` announces "June 2024, NDVI 0.62".

**Keep the debounce.** `YEAR_SETTLE_MS` in the prototype is exactly the right
instinct. With the fast path it can drop to ~80 ms; the exact path stays debounced
at ~400 ms and is cancellable via `AbortController`.

### 6.3 Drawing tools

Largely done — this section is about porting and hardening.

- Port the existing mouse+touch handlers to MapLibre. Keep the interaction feel
  identical; only the rendering target changes.
- **Rectangle**: drag corner to corner; hold Shift for a square.
- **Circle**: drag centre outward; show live radius and area readout while dragging.
- **Freehand**: capture at ~60 Hz, then **simplify with `turf.simplify`** (Douglas-Peucker,
  tolerance scaled to zoom) on release. Without this a two-second scribble is
  ~600 vertices, which slows every subsequent PostGIS and rasterio call.
- **Always validate on commit**: `turf.kinks` for self-intersection, then repair
  (`ST_MakeValid` server-side) or reject with a clear inline message. Freehand
  shapes self-intersect constantly and an invalid polygon fails *downstream*, in
  the stats call, where the error message will make no sense to the user.
- Add **edit-after-draw** (drag vertices, drag whole shape) and **undo/redo**
  (`Cmd+Z`) — a Procreate-like tool that can't undo breaks the metaphor immediately.
- Add **AOI upload** (GeoJSON / KML / zipped Shapefile drag-and-drop). Most
  serious users already have their boundary in a file; making them re-trace it is
  the exact friction you're removing.
- Cap area (e.g. 500 km² on the exact path) with a friendly explanation and an
  offer to run it as a background job rather than a hard refusal.

### 6.4 Automatic attribute table

**Flag first: "attribute table" is underspecified in the brief, and it needs a
decision from you.** In traditional GIS an attribute table has one row per vector
feature. Here the user draws one shape over raster data — so what is a row?

Three answers, all legitimate, and the tool should offer all three via a row-mode
switch, defaulting to **By time**:

| Row mode | A row is | Columns | Best for |
| --- | --- | --- | --- |
| **By time** *(default)* | one timestep | mean/min/max/σ per dataset, valid % | "how did this site change?" — the core use case |
| **By feature** | one intersecting vector feature (parcel, LSOA, field) | zonal stats at current timestep | "which parcel is worst?" |
| **By cell** | one H3 cell in the AOI | value per dataset at current timestep | spatial variation within the AOI |

Implementation:

- Server returns **Apache Arrow** (not JSON) for anything over ~1k rows. Roughly
  5–10× smaller on the wire, zero-copy into DuckDB-WASM, and correct numeric types.
- TanStack Table with `@tanstack/react-virtual`; virtualise past 200 rows.
- Column type drives formatting automatically: continuous → 2 dp + unit;
  categorical → coloured chip from `class_map`; temporal → locale date;
  percentage → inline micro-bar in the cell.
- **Cells with `valid_fraction < 0.4` render greyed with a hover explanation.**
  Never silently show a number derived from three cloud-free pixels.
- Excel muscle memory, honoured: click-drag range selection, `Cmd+C` copies TSV
  (pastes straight into Excel), sortable headers, resizable columns, a filter row,
  frozen first column, `Cmd+F`.
- Selecting rows highlights the corresponding geometry or timesteps on the map
  and timeline. Bidirectional linking is what makes it feel like one application
  instead of a map with a spreadsheet bolted to it.

### 6.5 Automatic graph generation

The table is the source of truth; charts are a projection of it. Rule: **charts
render from the current table view, including its filters and sort.** Filter the
table, the charts follow. That single invariant removes an entire class of
"which data is this chart showing?" confusion.

Chart selection is inferred from column types:

```ts
function inferCharts(cols: Column[], rowMode: RowMode): ChartSpec[] {
  const t = cols.filter(c => c.type === 'temporal');
  const n = cols.filter(c => c.type === 'continuous');
  const c = cols.filter(c => c.type === 'categorical');
  const specs: ChartSpec[] = [];

  // Time on x + numbers on y -> line, one per unit family (never mix units on an axis)
  if (t.length && n.length)
    for (const [unit, group] of groupBy(n, m => m.unit))
      specs.push({ type: 'line', x: t[0], y: group, unit, band: 'stddev' });

  // Categorical composition over time -> stacked area (land cover's natural view)
  if (t.length && c.length)
    specs.push({ type: 'stacked-area', x: t[0], series: c[0], normalise: true });

  // No time axis -> distribution of each measure
  if (!t.length && n.length)
    specs.push(...n.map(m => ({ type: 'histogram', x: m })));

  // Correlated pairs are worth surfacing, but only if actually correlated
  if (n.length >= 2)
    for (const [a, b] of pairs(n))
      if (Math.abs(pearson(a, b)) > 0.5)
        specs.push({ type: 'scatter', x: a, y: b, trend: 'linear' });

  return rank(specs).slice(0, 4);   // four cards maximum — more is noise
}
```

Then:

- Render with Observable Plot; each spec becomes a card in `<ChartStack>`.
- **Gaps stay gaps.** A cloudy month is a break in the line, not an interpolated
  point. Show `valid_fraction` as a faint band under the series.
- **The chart is hooked to the timeline**: a vertical rule marks the current
  timestep and moves as you scrub. Clicking the chart moves the scrubber.
- Every chart offers "edit" (change type, swap axes, change aggregation) — the
  automation is a starting point, not a cage — plus PNG/SVG export and
  "copy as data".
- Cap at four auto-charts. The failure mode of auto-generation is twelve charts
  nobody reads.

---

## 7. Additional feature suggestions

Grounded in the actual friction points of GIS work rather than feature-list padding.

**7.1 Shareable permalinks and saved projects.**
Encode AOI, time position, active layers and panel state in the URL; a "Save"
turns it into a named project. *Why:* the single biggest failure of GEE workflows
is irreproducibility — a colleague asks "how did you get that number?" and the
answer is a script nobody can run. A URL that restores exact state is the cheapest
credibility feature you can build, and it's your primary organic growth channel.

**7.2 Change detection between two dates.**
Brush two handles on the timeline, get a swipe/split map, a difference raster, and
a table of what changed and by how much. *Why:* "what changed between X and Y" is
the most common real question in temporal GIS, and in ArcGIS it's a multi-step
raster-calculator chore. Here it's already implied by your timeline — you get most
of the way there for free.

**7.3 Export everything, in formats people already use.**
CSV and XLSX from the table, GeoJSON/Shapefile/GeoPackage for the AOI, GeoTIFF
clipped to the AOI, PNG/SVG per chart, and a one-click PDF report. *Why:*
counter-intuitively, making it easy to leave makes people stay. A tool you can't
get data out of doesn't get used for real work — and clipped-GeoTIFF export is
what lets a QGIS user adopt you for the *tedious* half of their workflow without
abandoning their existing one.

**7.4 Threshold alerts and monitoring on a saved AOI.**
"Email me if NDVI drops more than 2σ below its 5-year seasonal mean." *Why:* this
converts the product from a thing you visit into a thing that works for you, and
it's the most natural paid tier. Technically it's a cron over `cell_stats` plus a
notification — the data is already there.

**7.5 No-code band-math / index builder.**
A visual formula editor (`(NIR − RED) / (NIR + RED)`) with a live preview and
presets for NDWI, NDBI, EVI, SAVI. *Why:* right now, wanting an index you don't
ship means learning the Earth Engine JS API — a cliff edge in the middle of your
UX. A formula box keeps advanced users inside the product.

**7.6 Multi-AOI comparison.**
Draw several shapes, get small-multiple charts and a comparison table. *Why:*
site selection and benchmarking are inherently comparative ("which of these five
fields is degrading fastest?"), and every mainstream tool makes you do it one
shape at a time and reconcile the results by hand.

**7.7 Data-quality transparency, surfaced not buried.**
Per-timestep valid-pixel percentage in the timeline strip, greyed table cells
below threshold, source/resolution/licence per column in the provenance tab.
*Why:* the fastest way to lose a technical user is one number they can tell is
wrong with no explanation. This is also your honest answer to "how do I know I can
trust this?" — and it's a genuine differentiator, since GEE makes users compute
this themselves.

**7.8 Guided templates / recipes.**
Pre-built flows: "Vegetation change over 10 years", "Flood exposure of a site",
"Urban growth". Each preselects datasets, time range and charts. *Why:* the target
user knows GIS concepts but not your interface. A template is a worked example
that produces their answer on the first visit, which is the entire onboarding
problem solved without a tutorial.

**7.9 Annotations and pinned observations.**
Drop a pin or note at a location + timestep, attached to the project. *Why:* the
Procreate metaphor implies a workspace you return to. It also makes the tool
usable for collaboration, which is where a report-writing workflow actually lives.

**7.10 Offline-capable AOI cache (PWA).**
Cache recently viewed AOIs and their series in IndexedDB. *Why:* fieldwork.
Anyone doing site assessment is sometimes standing in a field with one bar of
signal, and every desktop GIS fails them there.

---

## 8. Technical challenges to anticipate early

**8.1 "Instant" is a physics problem, not a UI problem.** Covered in §1 — this is
the risk that decides whether the product delivers on its premise. Prototype the
H3 fast path *first*, on one dataset, before building any UI around it. If a
15-year series doesn't return in under 100 ms, everything downstream needs
rethinking.

**8.2 Storage cost will surprise you. Do the arithmetic before committing.**
Sentinel-2 at 10 m over the UK is ~2.4 billion pixels per band per timestep.
Fifteen years of monthly, multi-band, uncompressed is **petabytes** — not a
budget, a research facility. The only viable approach:

- Store **derived single-band products** (NDVI, not all 13 bands): ~2.4 GB per
  monthly timestep at 10 m, ~430 GB for 15 years for one index over the UK.
  Manageable.
- Use **overviews plus internal deflate/zstd**; serve low zooms from overviews.
- **Tier by age**: last 2 years at 10 m hot, older years at 30 m in nearline.
- Cell-level aggregates are tiny by comparison — H3 res 8 over the UK is ~330k
  cells; 15 years monthly × 8 datasets ≈ 475M rows, which is comfortable for
  compressed Timescale (~15–25 GB).

Decide the spatial scope early. "The UK" and "the world" are different companies.

**8.3 Projection and area errors.** Web Mercator badly distorts area with
latitude. Compute areas geodesically (`ST_Area(geography)`, `turf.area`) — the
prototype already does this correctly, so preserve that. Run analysis in an
equal-area or national grid CRS (EPSG:27700 for the UK, EPSG:6933 globally) and
reproject only for display.

**8.4 Temporal alignment across datasets.** Sentinel-2 is 5-day, Landsat 16-day,
WorldCover annual, CHIRPS pentadal. A shared timeline forces a resampling policy:
declare each dataset's native step in the registry, resample to a common display
step, and **make the resampling visible** (a dotted line for interpolated
timesteps). Silently interpolating annual land cover to monthly produces charts
that are confidently wrong.

**8.5 Categorical statistics are not continuous statistics.** The mean of land
cover class codes is meaningless — `10` (tree) and `80` (water) do not average to
`45` (shrubland). The current `/api/stats` returns a `frequencyHistogram` for land
cover, which is right; keep the `kind` discriminator in the schema and let it drive
which reducers, chart types and table formatters are legal. This is a very easy
bug to ship and a very embarrassing one to explain.

**8.6 Cloud gaps and missing data.** Northern-latitude winters can have zero
usable observations for a month. Decide the policy explicitly — recommendation:
**never interpolate silently**; show gaps, expose `valid_fraction`, and offer an
optional smoothed overlay the user turns on knowingly.

**8.7 Freehand polygon pathologies.** Self-intersections, sub-pixel slivers,
thousands of vertices, and shapes crossing the antimeridian. Validate, simplify
and repair at the moment of commit — not at query time, where errors surface as
opaque server failures. Budget real time for this; it's a bigger source of bugs
than it appears.

**8.8 Unbounded AOIs as accidental self-DoS.** Nothing stops a user drawing a
rectangle over Europe. Enforce area caps per path, downsample resolution as area
grows, queue anything large, and rate-limit per user. Do this before launch, not
after the first incident.

**8.9 Earth Engine licensing.** EE is free for research, education and
non-commercial use; commercial use requires a paid Google licence. If Site Scanner
becomes a product, the EE-on-the-request-path model is a legal and cost exposure.
The ingest-then-store architecture in §3 mitigates this — you use EE for batch
derivation under whatever licence you hold, and serve users from your own
storage — but confirm the terms for your specific use before building on it.
Copernicus data direct from AWS/Sentinel Hub Open Data avoids the question
entirely and is worth evaluating as the primary source.

**8.10 The `README.md` caching caveat is real and unfixed.** The in-process cache
means Cloud Run instances don't share entries and cold starts always miss. Redis
is a small change with a large effect on both latency and Earth Engine quota;
do it early.

**8.11 Cold-start latency on serverless.** FastAPI plus `earthengine-api` plus
`rasterio` is a heavy import graph — several seconds of cold start, which lands
squarely on the unlucky first user. Set `min-instances: 1` on Cloud Run, or
accept it and warm on page load.

**8.12 The mock-backend discipline is an asset — don't let it lapse.** Every new
service needs its `mock_ee_backend.py` equivalent with identical response shapes
and an identifying header. It's what keeps frontend work unblocked and the test
suite credential-free.

---

## 9. Suggested build order

Sequenced so that each phase produces something demonstrable, and the riskiest
assumption is tested first.

| Phase | Scope | Proves |
| --- | --- | --- |
| **0 — De-risk (1–2 wks)** | Ingest *one* dataset (NDVI) for *one* county, 15 years monthly, to COG + `cell_stats`. Benchmark the fast-path query. | That "instant" is achievable. **Stop and rethink if it isn't.** |
| **1 — Foundation (2–3 wks)** | React/Vite/TypeScript scaffold, MapLibre, port drawing tools, Redis cache, TiTiler. | The prototype's good parts survive the rewrite. |
| **2 — Timeline (2 wks)** | Cross-fade scrubbing, availability strip, in-timeline sparkline, playback, keyboard access. | The signature feature. |
| **3 — Table + charts (3 wks)** | Arrow transport, TanStack table with row modes, chart inference, table↔chart↔map linking. | Features 4 and 5, the greenfield half. |
| **4 — Breadth (3–4 wks)** | Remaining datasets, exact-path refine, provenance panel, exports (7.3), permalinks (7.1). | It's a tool, not a demo. |
| **5 — Depth (ongoing)** | Templates (7.8), change detection (7.2), multi-AOI (7.6), alerts (7.4), index builder (7.5). | Retention and differentiation. |

The honest summary: the drawing tools are nearly done, the timeline needs a
rebuild on faster foundations, the table and charts are entirely new, and the
data layer is the real project — probably 60% of the total effort and the whole
of the technical risk. Phase 0 exists to find that out in two weeks rather than
two months.
