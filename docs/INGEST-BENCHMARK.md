# Ingest benchmark — NDVI over Surrey, end to end

`BENCHMARK.md` measured the read side and closed with a list of what it did not
prove. Top of that list: *"Ingest cost. This measures reads. Populating the
aggregates from real rasters is the other half, and it is what `ingest/`
addresses."* This is that other half.

**Verdict: the pipeline works end to end and a national backfill is a weekend
of batch compute, as TECHNICAL_PLAN.md §3.3 claimed — but the storage figure in
the current format is 6× larger than it needs to be, and the aggregation stage
costs one full pass over the raster per resolution tier, which is not how the
plan describes it.**

## What was run

```bash
pg_ctlcluster 16 main start
createdb ingest_bench
DSN=postgresql://postgres@127.0.0.1:5432/ingest_bench

# The run itself — 2.5 minutes, ~1.1 GB of COGs.
python3 -m ingest.run ingest/manifests/ndvi_s2_surrey.yaml \
  --synthetic --out /tmp/cogs --dsn "$DSN"

# Result 2 — query what it wrote, from real Surrey AOIs.
python3 -m bench.ingest_readback --dsn "$DSN"

# Result 5 — the same raster written four ways.
python3 -m bench.cog_formats
```

Everything below reproduces from those four commands. Timings will differ by
machine; the ratios should not.

| | |
| --- | --- |
| Dataset | `ndvi_s2_surrey` — Sentinel-2 NDVI, 10 m, monthly |
| Extent | Surrey's administrative bbox, `[-0.85, 51.07, 0.06, 51.47]` — 63.4 × 44.5 km, **2,822 km²** |
| Raster | 6,338 × 4,453 = **28.2 M pixels** per timestep |
| Time span | 12 months, 2024-01 to 2024-12 |
| Tiers | H3 res 7 and res 8, both written |
| Machine | 4 cores, 16 GB, PostgreSQL 16 with stock settings (128 MB shared_buffers) |
| Pixels | **Synthetic.** See "What this does not prove". |

## Result 1 — it completes, and every stage is measured

```
ndvi_s2_surrey: done in 151.7s, 60,828 cell-rows
  per timestep: fetch 4.66s  cog 3.36s  aggregate 4.47s  load 0.14s
  12.64s/timestep, 91.1 MB COG/timestep, 5,069 cells/timestep
```

| Stage | s/timestep | Share | What it is |
| --- | ---: | ---: | --- |
| fetch | 4.66 | 37% | **Synthetic generation — not a real fetch.** In production this is an Earth Engine export or an HTTP range read, and it is the one number here that means nothing. |
| COG write | 3.36 | 27% | zstd-9, 512 px tiles, 6 overview levels |
| aggregate | 4.47 | 35% | 28.2 M pixels → 5,069 H3 cells, twice (once per tier) |
| DB load | 0.14 | 1% | 5,069 rows via `executemany` with `ON CONFLICT` |

The load stage being 1% is worth stating plainly: **the database is not the
bottleneck and pre-aggregation is close to free.** Everything expensive happens
before Postgres is involved. That is the opposite of the usual intuition about
an ingest pipeline and it means effort spent tuning the write path would be
wasted.

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
| Wall time, all stages | 9.4 min | **28.2 h** |
| Wall time, excluding the synthetic fetch | 5.9 min | **17.8 h** |
| Cell rows (both tiers) | 226,000 | 40.7 M |
| COG storage, current format | 4.07 GB | **732 GB** |
| COG storage, int16 (see Result 5) | 0.68 GB | **123 GB** |

Single-threaded. The aggregation stage is embarrassingly parallel across cells
and the COG writer across tiles, so four cores should bring 28 hours to
roughly eight, and a cloud batch job with sixteen to about two.

**TECHNICAL_PLAN.md §3.3 said a full backfill is "a weekend of batch compute,
not a research project". That holds** — for one dataset, at England's land
extent, ignoring the fetch. It does not hold for eleven Sentinel-2 indices
stored separately; see Result 6.

## Result 5 — the storage format is costing 6×

`write_cog` stores NDVI as float32 with a float nodata sentinel. Four variants
of the same Surrey raster, same compression settings:

| Format | COG size | vs current |
| --- | ---: | ---: |
| float32, 15% per-pixel nodata — **what the pipeline writes today** | 91.0 MB | — |
| float32, ~15% nodata as contiguous blobs | 50.9 MB | 0.56× |
| float32, no nodata at all | 51.0 MB | 0.56× |
| **int16 scaled ×10,000, blob nodata** | **15.3 MB** | **0.17×** |

Two separate findings sit in that table.

**The pipeline's own test data overstates its storage cost by 79%.**
`synthetic_raster` scatters nodata as independent per-pixel holes, which is
incompressible noise. A real cloud mask is contiguous blobs, and blob nodata
costs nothing at all over no nodata (50.9 vs 51.0 MB). Any storage figure
previously derived from a `--synthetic` run is 1.8× too pessimistic. The
generator should mask in blobs; the fix is small and it is noted below rather
than made here, because changing the generator invalidates comparison with this
run.

**NDVI does not need float32.** It is bounded to [-1, 1] and nobody reads it
past three decimals. `int16 × 10,000` gives four, and costs a sixth of the
storage — 732 GB down to 123 GB for the national backfill. This is the single
largest cost lever in the pipeline and it is a change to `COG_PROFILE` plus a
scale factor in the manifest, not an architectural one.

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

## Result 7 — a national run at 10 m cannot be one raster

England's bbox at 10 m is 63,000 × 66,200 = **4.2 billion pixels**, 16.7 GB as
float32 before the COG writer takes its copy. The runner now refuses this with
an explicit message rather than being killed by the OOM reaper at month nine of
a backfill:

```
63,000×66,200 = 4,171 M pixels for one timestep of ndvi_s2 at 10 m.
That will not fit in memory. Use --window to ingest a sub-extent, or tile the
manifest — which is what a national run at 10 m needs regardless.
```

**Tiling is mandatory at national scale, and it is not built.** `--window`
makes a tiled run possible by hand; nothing schedules the tiles, tracks which
tiles are done, or stitches the COGs. `ingest_progress` is keyed by
`(dataset, timestep, h3_res)` with no tile column, so a tiled backfill cannot
currently resume correctly — it would mark a timestep done after the first
tile. That is the largest gap this benchmark found and it is recorded in "What
to do next".

## Two bugs this run found

**1. `--synthetic` ignored the manifest's extent.** `fetch_raster` generated a
fixed 512 × 512 tile over a hard-coded 0.25° window regardless of what the
manifest declared, so a `--synthetic` run exercised the code path and measured
nothing — every cost in this pipeline scales with extent and resolution and
with nothing else. It now generates at the manifest's declared bbox and
resolution, which is what made this benchmark possible at all. Fixed in
`ingest/run.py`.

**2. The manifest's CRS is ignored.** Both manifests declare
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

1. **Store int16, not float32.** 6× storage, one profile change. Do this before
   the first real backfill, because redoing 123 GB is cheap and redoing 732 GB
   is not.
2. **Build tiling, with a tile column in `ingest_progress`.** Without it there
   is no national run at 10 m, resumable or otherwise.
3. **Measure a real Earth Engine fetch** the day credentials exist. Everything
   above is provisional until that number is known.
4. **Fix `synthetic_raster` to mask in blobs**, so the pipeline's own test data
   stops overstating storage by 79%.
5. **Store bands, not indices.** Eleven Sentinel-2 indices are pure functions
   of a handful of bands. Storing all eleven at 10 m is eleven times the
   storage for no extra information — 1.35 TB against 246 GB for two int16
   bands. Compute indices when aggregating, or at read time from the COG.
   This has not been benchmarked and should be before it is adopted, but the
   arithmetic is stark enough to put on the list.
6. **Honour or remove `spatial.crs`.**
