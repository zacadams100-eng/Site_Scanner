# Ingest benchmark — NDVI over Surrey, end to end

> **Re-measured after tiling and int16 storage landed.** Every figure below is
> from the current pipeline. The first run of this benchmark is what motivated
> both changes; where a number moved, the old one is shown beside it.

`BENCHMARK.md` measured the read side and closed with a list of what it did not
prove. Top of that list: *"Ingest cost. This measures reads. Populating the
aggregates from real rasters is the other half, and it is what `ingest/`
addresses."* This is that other half.

**Verdict: the pipeline works end to end, tiles correctly, resumes per tile,
and a national backfill is a weekend of batch compute as TECHNICAL_PLAN.md §3.3
claimed. The aggregation stage still costs one full pass over the raster per
resolution tier, which is not how the plan describes it.**

## What was run

```bash
pg_ctlcluster 16 main start
createdb ingest_bench
DSN=postgresql://postgres@127.0.0.1:5432/ingest_bench

# The schema, including the tile column. Idempotent.
python3 -m ingest.migrate --dsn "$DSN"

# The run itself — under two minutes, ~390 MB of COGs across 2 tiles x 12 months.
python3 -m ingest.run ingest/manifests/ndvi_s2_surrey.yaml \
  --synthetic --out /tmp/cogs --dsn "$DSN"

# Kill it partway and run it again: it resumes at the tile it reached.

# Result 2 — query what it wrote, from real Surrey AOIs.
python3 -m bench.ingest_readback --dsn "$DSN"

# Result 5 — the same raster written four ways.
python3 -m bench.cog_formats
```

Everything below reproduces from those commands. Timings will differ by
machine; the ratios should not.

| | |
| --- | --- |
| Dataset | `ndvi_s2_surrey` — Sentinel-2 NDVI, 10 m, monthly |
| Extent | Surrey's administrative bbox, `[-0.85, 51.07, 0.06, 51.47]` — 63.4 × 44.5 km, **2,822 km²** |
| Raster | 6,338 × 4,453 = **28.2 M pixels** per timestep |
| Time span | 12 months, 2024-01 to 2024-12 |
| Tiers | H3 res 7 and res 8, both written |
| Tiling | 2 tiles on a 2x1 grid — Surrey at 10 m is 28.2 M px, over the 25 M budget |
| Machine | 4 cores, 16 GB, PostgreSQL 16 with stock settings (128 MB shared_buffers) |
| Pixels | **Synthetic.** See "What this does not prove". |

## Result 1 — it completes, tiles, and every stage is measured

```
ndvi_s2_surrey: done in 116.4s, 61,860 cell-rows
  per tile: fetch 1.05s  cog 1.50s  aggregate 2.21s  load 0.10s
  4.85s/tile, 16.2 MB COG/tile, 2,578 cells/tile
```

24 tile-timesteps — 12 months x 2 tiles — so per timestep that is **9.7 s** and
**32.4 MB** of COG, against 12.6 s and 91.1 MB before tiling and int16.

| Stage | s/tile | s/timestep | Share | What it is |
| --- | ---: | ---: | ---: | --- |
| fetch | 1.05 | 2.10 | 22% | **Synthetic generation — not a real fetch.** |
| COG write | 1.50 | 3.00 | 31% | zstd-9, int16, 512 px tiles, 6 overview levels |
| aggregate | 2.21 | 4.42 | 46% | 14.1 M pixels -> 2,578 H3 cells, twice (once per tier) |
| DB load | 0.10 | 0.20 | 2% | ~2,578 rows, merged not overwritten |

The load stage being 2% is worth stating plainly: **the database is not the
bottleneck and pre-aggregation is close to free**, even now that every row is
a read-modify-write merge rather than a blind overwrite. Everything expensive
happens before Postgres is involved, so effort spent tuning the write path
would be wasted.

The merge is not free of *correctness* risk, though, which is Result 8.

## Result 2 — the fast tier answers a real Surrey AOI

Ingest that writes rows nobody can read is not ingest. Three real AOIs, resolved
to cells the way the application does, queried against what the run produced:

| AOI | Area | Tier | Cells | Months | p50 | p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A field near Shere | 0.5 km² | 8 | 4 | 12 | 0.28 ms | 0.42 ms |
| Guildford town centre | 3.5 km² | 8 | 12 | 12 | 0.38 ms | 0.52 ms |
| Surrey Hills AONB core | 298 km² | 7 | 85 | 12 | 1.18 ms | 1.78 ms |

Every AOI returned all twelve ingested months with no nulls, including the
0.5 ha-scale field that `BENCHMARK.md` Result 2 showed would silently return
nothing under H3's default containment. The overlap-containment fix holds
against real ingested data, not just against a synthetic cell table.

**These timings are not comparable to `BENCHMARK.md`'s** and should not be
quoted as an improvement. That table held 70.8 M rows; this one holds 52,824.
Sub-millisecond here means "the table fits in shared_buffers", not "the
architecture got faster". `BENCHMARK.md` remains the authority on query cost.

## Result 3 — an independent check on the national cell count

Two unrelated methods now agree on how many res-8 cells England needs:

- `bench/england.py` tiled a real England outline: **196,554 cells**.
- This run produced 4,402 res-8 cells for 2,822 km². Scaling by England's
  130,279 km² of land gives **~203,000**, 3% apart.

Both include the boundary cells that overlap containment adds — 15% over the
naive area ÷ 0.737 km² figure for Surrey's bbox, 11% for England, which is the
right direction since a larger area has proportionally less perimeter. The
storage and row-count extrapolations below use the measured 196,554 and a
scale factor of **44.7×** from this run.

## Result 4 — extrapolated to England, 15 years

| | Per timestep | 180 timesteps |
| --- | ---: | ---: |
| Wall time, all stages | 7.2 min | **21.7 h** |
| Wall time, excluding the synthetic fetch | 5.6 min | **16.8 h** |
| Cell rows (both tiers) | 226,000 | 40.7 M |
| COG storage, int16 as now stored | 1.45 GB | **260 GB** |
| COG storage, float32 as previously | 4.5 GB | **810 GB** |

Tiles: 154 on an 11x14 grid, so a national backfill is **27,720 tile-timesteps**
per resolution pair. That is the number the scheduler has to survive, and it is
why progress is recorded per tile.

Single-threaded. The aggregation stage is embarrassingly parallel across cells
and the COG writer across tiles, so four cores should bring 28 hours to
roughly eight, and a cloud batch job with sixteen to about two.

**TECHNICAL_PLAN.md §3.3 said a full backfill is "a weekend of batch compute,
not a research project". That holds** — for one dataset, at England's land
extent, ignoring the fetch. It does not hold for eleven Sentinel-2 indices
stored separately; see Result 6.

## Result 5 — int16 storage costs a third of float32

The same Surrey raster written four ways, same compression settings, on the
current generator:

| Format | COG size | vs float32 |
| --- | ---: | ---: |
| float32, ~15% cloud as blobs | 118.5 MB | 1.00× |
| float32, 15% per-pixel nodata | 107.9 MB | 0.91× |
| float32, no nodata at all | 123.5 MB | 1.04× |
| **int16 scaled ×10,000, blob nodata** | **34.5 MB** | **0.29×** |

**Treat the ratio as the finding and the megabytes as scenery.** The absolute
sizes are a property of synthetic data — they moved substantially when the
generator changed, because zstd with horizontal differencing is very sensitive
to how a surface is built, and a linear ramp compresses far better than a
smoothstepped one. The int16 ratio did not move: 0.30× on the old generator,
0.29× on this one. That is the number to rely on, and real imagery will land
somewhere near it because the mechanism is arithmetic, not statistics — half
the bytes per pixel, and an integer predictor that actually applies.

**NDVI does not need float32.** It is bounded to [-1, 1] and nobody reads it
past three decimals. `int16 × 10,000` gives four. This was the single largest
cost lever in the pipeline and it is now the default for every continuous
manifest — see `ingest/cog.py`, and `storage:` in each manifest.

The earlier finding that **the pipeline's own test data overstated storage by
79%** has also been fixed: `synthetic_raster` used to scatter nodata as
independent per-pixel holes, which is incompressible noise a real cloud mask
would never produce. Gaps are now contiguous blobs from a second smooth field.

## Result 6 — aggregation scales with pixels, not with cells

| Tier | Cells | `cells_for_bounds` | Aggregate | Per cell | Pixels per cell |
| --- | ---: | ---: | ---: | ---: | ---: |
| res 7 | 669 | 8 ms | 2,083 ms | 3,114 µs | 42,187 |
| res 8 | 4,406 | 50 ms | 2,438 ms | 553 µs | 6,406 |

Res 7 has 6.6× fewer cells and costs 85% as much, because both tiers walk every
pixel exactly once. Throughput is **~12 M pixels/second/tier**, flat across
resolution. Finding H3 cells is 2% of the stage; the other 98% is the
point-in-hexagon test over pixel centres.

`BENCHMARK.md` Result 3 concluded that storing two tiers "costs very little,
because the coarse tier is 7× smaller". That is true of **storage and query**,
and false of **ingest**: a second tier is another full pass, +85% CPU. It does
not change the recommendation — 85% of the cheapest stage is worth paying for
6.7× on large AOIs — but "two tiers are nearly free" should not be repeated
without that qualifier. Adding a third tier would cost another full pass, which
is a second reason res 9 was right to reject.

The obvious optimisation, if this ever matters: one pass that computes the
res-8 cell index per pixel and derives res 7 by `cell_to_parent`, rather than
two independent passes. It would roughly halve the stage. Not worth doing until
the fetch stage is real, because fetch may dwarf it.

## Result 7 — a national run at 10 m is tiled, and resumes per tile

England's bbox at 10 m is 55,078 x 66,235 = **3.6 billion pixels**, 14.6 GB as
float32 before the COG writer takes its copy. The runner now cuts any extent
over 25 M pixels into a grid:

```
ndvi_s2: 180 timestep(s), H3 res [7, 8], kind=continuous
  extent (-6.42, 49.86, 1.77, 55.81)  ->  55,078x66,235 px at 10 m (3648.1 M/timestep)
  154 tiles on a 11x14 grid, largest 23.7 M px, 27,720 tile-timesteps to do
```

Progress is recorded per `(dataset, timestep, tile, h3_res)`, in the same
transaction as that tile's rows. A killed run comes back and does exactly the
tiles it had not finished — asserted directly in `tests/test_tiling.py`, by
failing a run on its fourth tile and checking the resumed run skips three and
does the rest.

Surrey itself now runs as 2 tiles rather than 1, which is what makes the
equivalence checkable at benchmark scale: the tiled run produced **4,402
distinct res-8 cells and 52,824 rows, identical to the untiled run** recorded
in Result 3.

## Result 8 — tiling's real hazard is the seams, not the memory

An H3 cell on a tile boundary is aggregated once per tile it touches, over only
that tile's pixels. The obvious `ON CONFLICT DO UPDATE SET mean = EXCLUDED.mean`
leaves such a cell holding whichever sliver was written last — a wrong number,
on every tile edge in the country, with nothing to notice it by. At an 11x14
grid that is roughly 3,000 km of internal boundary.

Cell rows now carry `n_valid`, `n_total` and `m2` (the sum of squared
deviations), so partial aggregations combine exactly by Chan's parallel
variance algorithm rather than approximately by averaging averages. A merged
row is indistinguishable from one produced by a single pass, which is checked
three ways:

- in Python, merging two halves of a raster against one pass over the whole —
  4,363 cells, zero mismatches;
- in SQL against the Python implementation, since the merge exists twice and
  two copies of an algorithm drift;
- end to end through the runner and a real database, ingesting one extent both
  ways and comparing cell for cell.

The uneven case is the one worth stating: 900 pixels averaging 10 merged with
100 averaging 20 is 11, not 15. Averaging the averages is wrong by 36% and
looks entirely plausible.

## Three bugs found by running it

**1. `--synthetic` ignored the manifest's extent.** `fetch_raster` generated a
fixed 512 × 512 tile over a hard-coded 0.25° window regardless of what the
manifest declared, so a `--synthetic` run exercised the code path and measured
nothing — every cost in this pipeline scales with extent and resolution and
with nothing else. It now generates at the manifest's declared bbox and
resolution, which is what made this benchmark possible at all. Fixed in
`ingest/run.py`.

**2. Tiles drifted off the parent pixel grid.** `fetch_raster` recomputed a
tile's pixel dimensions from its bbox instead of using the dimensions the tiler
had already apportioned. Rounding independently put each tile's grid a fraction
of a pixel out, which moves which cell a pixel centre falls in, so cells near
tile edges got different pixel counts and different means from the same data.
Found by the tiled-versus-untiled comparison and fixed by passing the tile's
own shape; nothing else would have caught it, because each tile was internally
consistent and the totals looked right.

**3. The manifest's CRS is ignored.** Both manifests declare
`crs: EPSG:27700` — British National Grid, chosen deliberately because it is
equal-area enough for England and is what UK data ships in. The runner writes
every COG as `EPSG:4326` and aggregates in lat/lng. Nothing is wrong with the
output, but the manifest field is decoration: a manifest declaring a projected
CRS gets a geographic one and is not told. Either honour it or remove it. Not
fixed here — it is a real decision about whether the pipeline reprojects, and
reprojection belongs in the missing `mask → composite → reproject` stages.

## What this does not prove

- **Real pixels.** No Earth Engine credentials and no network egress in this
  environment, so the fetch stage is a generator. Values are meaningless; the
  *shape* of the work — pixel counts, tile counts, cell counts, row counts,
  compression behaviour of a smoothly varying field — is real.
- **The fetch stage at all.** 37% of measured time is a stand-in. A real
  Earth Engine export for one month of Surrey at 10 m could plausibly take
  minutes, dominate everything else, and make the parallelism advice above
  irrelevant. **This is the single most important unmeasured number in the
  pipeline.** Run it the day credentials exist.
- **Cloud masking and compositing.** `mask`, `composite` and `reproject` from
  the TECHNICAL_PLAN §3.3 stage list are declared in the manifest and not
  implemented; the runner goes fetch → COG → aggregate.
- **Concurrency.** Single process throughout. No contention measured, and the
  parallelism estimates above are arithmetic, not measurement.
- **Real compression ratios.** A smooth synthetic field compresses like a
  smooth real one, which is why Result 5's relative figures are trustworthy;
  the absolute megabytes could still move by a third either way on real
  imagery.

## What to do next, in order

1. ~~Store int16, not float32.~~ **Done** — the default for every continuous
   manifest, and Result 5 is the re-measurement.
2. ~~Build tiling, with a tile column in `ingest_progress`.~~ **Done** —
   Results 7 and 8, `ingest/tiling.py`, `ingest/migrations/002_tile_progress.sql`.
3. ~~Fix `synthetic_raster` to mask in blobs.~~ **Done**, and it made the
   surface window-independent as well, which is what let the tiled and untiled
   runs be compared at all.
4. **Measure a real Earth Engine fetch** the day credentials exist. Everything
   above is provisional until that number is known — it is now 22% of measured
   time and it is the one figure here that means nothing.
5. **Parallelise across tiles.** Tiling made this possible and nothing yet
   takes advantage: the runner is one process working through 27,720 units
   that share no state. This is the next real speedup and it is now a small
   change.
6. **Store bands, not indices.** Eleven Sentinel-2 indices are pure functions
   of a handful of bands. Storing all eleven at 10 m is eleven times the
   storage for no extra information — 1.35 TB against 246 GB for two int16
   bands. Compute indices when aggregating, or at read time from the COG.
   This has not been benchmarked and should be before it is adopted, but the
   arithmetic is stark enough to put on the list.
7. **Honour or remove `spatial.crs`.**
