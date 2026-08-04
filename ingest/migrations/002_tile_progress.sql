-- Tiling.
--
-- England at 10 m is 4.2 billion pixels in one raster — 16.7 GB before the
-- COG writer takes its copy (docs/INGEST-BENCHMARK.md Result 7). A national
-- run has to be tiled, and a tiled run has to be resumable per tile, or a
-- backfill that dies at tile 300 of 400 restarts from zero.
--
-- Two changes, and the second is the one that is easy to get wrong.

-- 1. Progress is per tile, not per timestep.
--
-- Without this a timestep is marked done after its first tile finishes, and a
-- resumed run skips 399 tiles it never processed — silently, with no error
-- and a partially populated table that looks complete.
--
-- Existing rows predate tiling and covered a whole extent in one pass, so they
-- get the sentinel '-'. That is a real tile id meaning "untiled", not a null:
-- it has to be part of the primary key, and a nullable key column would let
-- duplicates in.
ALTER TABLE ingest_progress ADD COLUMN IF NOT EXISTS tile text NOT NULL DEFAULT '-';

ALTER TABLE ingest_progress DROP CONSTRAINT IF EXISTS ingest_progress_pkey;
ALTER TABLE ingest_progress ADD PRIMARY KEY (dataset_id, t, h3_res, tile);

-- Which tiling a row was produced under. A run with a different tile grid is
-- not resumable against progress from the old one — the tile ids mean
-- different areas — so the grid is recorded and the runner refuses to mix
-- them rather than producing a plausible, wrong result.
ALTER TABLE ingest_progress ADD COLUMN IF NOT EXISTS grid text NOT NULL DEFAULT '1x1';


-- 2. Cell statistics have to be mergeable, not overwritable.
--
-- An H3 cell on a tile boundary is aggregated once per tile it touches, over
-- only that tile's pixels. The old ON CONFLICT DO UPDATE overwrote, so such a
-- cell ended up holding whichever sliver happened to be written last.
--
-- Storing the valid and total pixel counts plus the sum of squared deviations
-- makes the merge exact (Chan's parallel variance algorithm), so a merged row
-- is indistinguishable from one produced by aggregating the whole raster in
-- one pass. ingest/run.py's UPSERT does the merge; ingest/aggregate.py's
-- merge_stats() is the same arithmetic in Python, and the tests assert the
-- two agree with each other and with a single-pass aggregation.
--
-- Pre-existing rows have no counts. They are left at 0, which the merge treats
-- as "contributes nothing" — safe, and correct for a table that was never
-- tiled anyway.
ALTER TABLE cell_stats_r{res} ADD COLUMN IF NOT EXISTS n_valid bigint NOT NULL DEFAULT 0;
ALTER TABLE cell_stats_r{res} ADD COLUMN IF NOT EXISTS n_total bigint NOT NULL DEFAULT 0;
ALTER TABLE cell_stats_r{res} ADD COLUMN IF NOT EXISTS m2 double precision NOT NULL DEFAULT 0;
