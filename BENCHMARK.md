# Phase 0 — benchmark results

**Verdict: the instant timeline is achievable. Build it.**

`TECHNICAL_PLAN.md` §1 said to prove this before building anything on top of
it, because if a 15-year series could not be returned in roughly 100 ms the
whole product premise needed rethinking. It can, comfortably — but the
benchmark surfaced one bug that would have shipped and one design change worth
making now rather than later.

Reproduce with:

```bash
pg_ctlcluster 16 main start
python3 -m bench.benchmark_fastpath --build     # ~4 minutes
python3 -m bench.benchmark_fastpath
```

## What was measured

| | |
| --- | --- |
| Cell set | A real England outline tiled at H3 res 7 (28,082 cells) and res 8 (196,554 cells) |
| Time span | 180 monthly steps, 2011-01 to 2025-12 |
| Rows | 70.8 M at res 8, 10.1 M at res 7 (2 datasets each) |
| On disk | 6.8 GB at res 8, 973 MB at res 7 |
| Query | `WHERE dataset_id = ANY(…) AND h3 = ANY(…) GROUP BY t, dataset_id` — the whole 15-year series for every selected factor, in one round trip |
| Runs | 25 per case, cache-warm, p50 and p95 reported |

The values are synthetic. Nothing that determines query cost is: row counts,
index shape, query plan, and on-disk volume are all real.

Two deliberate departures from production, both of which make this a
**conservative** test:

- **Plain PostgreSQL 16, not TimescaleDB.** No chunk exclusion, no compression,
  no continuous aggregates. Timescale can only improve these numbers.
- **No PostGIS.** It isn't involved. The AOI is resolved to H3 cells in the
  application layer — which is exactly how production works — and the database
  only sees a list of integers. PostGIS stores AOI geometry; it plays no part
  in this query.

## Result 1 — it is fast enough, with room to spare

Using overlap containment and the right resolution per AOI size:

| AOI | What that is | Res | Cells | Rows read | p50 | p95 |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 5 ha | A smallholding | 8 | 2 | 720 | 0.8 ms | **1.0 ms** |
| 20 ha | A typical field | 8 | 3 | 1,080 | 0.8 ms | **1.0 ms** |
| 100 ha | A small farm | 8 | 4 | 1,440 | 0.9 ms | **0.9 ms** |
| 1,600 ha | A large estate | 8 | 38 | 13,680 | 4.1 ms | **4.3 ms** |
| 250 km² | A district | 8 | 416 | 149,760 | 35.6 ms | **40.7 ms** |
| 2,500 km² | The interactive cap | 7 | 583 | 209,880 | 46.2 ms | **50.7 ms** |

Every realistic area returns its entire 15-year monthly series in under 51 ms
at p95, and everything up to a large estate is under 5 ms. The 100 ms budget
is met with an order of magnitude to spare at the sizes people actually draw.

The plan confirms the index is doing the work — a bitmap index scan on the
primary key touching 110 buffers for a 1,600 ha AOI, then a hash aggregate:

```
Sort  (actual time=8.564..8.580 rows=360)
  -> HashAggregate  (actual time=8.455..8.496 rows=360)
       -> Bitmap Heap Scan on cell_stats_r8  (actual time=0.402..1.166 rows=8640)
            Heap Blocks: exact=82
            -> Bitmap Index Scan on cell_stats_pkey  (actual time=0.384 rows=8640)
```

Cost scales linearly with cells touched (377 cells → 29 ms, 3,770 cells →
374 ms), which is the behaviour you want: predictable, and controllable by
choosing resolution.

## Result 2 — a bug that would have shipped

**H3's default containment returns zero cells for any AOI smaller than one
cell.** At res 8 a cell is 0.74 km² (74 ha), and `polygon_to_cells` keeps only
cells whose *centre* falls inside the polygon:

| AOI | Cells at res 8, default | Cells at res 8, overlap |
| ---: | ---: | ---: |
| 2 ha | **0** | 2 |
| 5 ha | **0** | 2 |
| 10 ha | **0** | 2 |
| 25 ha | **0** | 3 |
| 50 ha | 1 | 4 |
| 100 ha | 2 | 4 |

A user drawing a single field — 5 to 20 hectares, and plausibly the most
common thing anyone will do with this tool — would have got an empty report
with no error and no explanation. The query would have succeeded and returned
nothing.

**Fix:** use overlap containment (`polygon_to_cells_experimental(...,
contain='overlap')`), which keeps every cell the shape touches. It is also the
semantically correct choice: the question is "what is under this shape", not
"which cell centres are inside it".

The accuracy caveat is real and belongs in the UI: a 5 ha field answered from
two 74 ha cells is a coarse approximation. That is precisely what the
`precision: "approx"` badge and the exact-COG refine pass exist for. The
important thing is that the user gets a fast approximate answer plus an honest
label, rather than silence.

## Result 3 — two resolution tiers, one simple rule

Res 8 alone degrades badly on large areas (2,500 km² takes 411 ms, over
budget). Res 7 handles that case in 51 ms — 6.7× fewer cells for the same
area. But res 7 is too coarse for small AOIs, where res 8 gives four times the
spatial detail at identical cost.

The rule that falls out:

```
AOI ≤ 250 km²  ->  res 8
AOI  > 250 km²  ->  res 7
```

Storing both tiers costs very little, because the coarse tier is 7× smaller.
Res 9 was not built: England at res 9 is 1.37 M cells, and at 20 datasets that
is ~4.9 billion rows. If sub-field precision is ever needed, it belongs in the
exact COG path, not in a third pre-aggregated tier.

## Storage, extrapolated from measured figures

Measured: 3.4 GB per monthly dataset at res 8, 486 MB at res 7, uncompressed.
Applying the real catalogue's cadences (7 monthly bases, ~4 annual, ~9 static):

| Tier | Uncompressed | With Timescale compression (10–20×) |
| --- | ---: | ---: |
| Res 8 | ~25 GB | ~1.5–2.5 GB |
| Res 7 | ~3.5 GB | ~0.2–0.4 GB |
| **Total** | **~29 GB** | **~2–3 GB** |

That is a rounding error next to the COG tier, and it comfortably fits on a
single modest Postgres instance. The fast tier is cheap; the expensive part of
this system remains the imagery, exactly as `TECHNICAL_PLAN.md` §8.2 predicted.

## What this changes

1. **Build the hybrid architecture as planned.** The instant tier delivers.
2. **Use overlap containment everywhere.** Non-negotiable — the default
   silently breaks the most common use case.
3. **Store two resolution tiers**, selected by AOI area at query time.
4. **Keep the `precision` badge.** Small AOIs are genuinely approximate on the
   fast tier, and the UI already has the field to say so.

## What this does not prove

- Cold-cache behaviour. Every figure is cache-warm, which is realistic for a
  service under load but not for the first query after a deploy.
- Concurrency. Single-client throughout; no contention measured.
- Ingest cost. This measures reads. Populating the aggregates from real
  rasters is the other half, and it is what `ingest/` addresses. **Now
  measured** — NDVI over Surrey, 12 months, end to end, in
  `docs/INGEST-BENCHMARK.md`. It confirms the national backfill is a weekend
  of compute, and it qualifies Result 3 below: two tiers are nearly free to
  store and query, but cost +85% CPU to ingest, because each tier is a full
  pass over the raster.
- Real spatial autocorrelation. Synthetic values are uniform random, so
  aggregate *values* are meaningless here — only timings are meaningful.
