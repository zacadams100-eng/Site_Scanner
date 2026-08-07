"""
The ingest runner.

One command executes any manifest. Stages are idempotent and keyed by
(dataset, timestep, tile, resolution), so a backfill that dies at tile 300 of
400 resumes rather than restarts — which matters when a national run at 10 m
is 180 timesteps x 48 tiles x 2 resolutions and takes hours.

    python3 -m ingest.migrate --dsn postgresql://…        # once, first
    python3 -m ingest.run ingest/manifests/ndvi_s2.yaml --dry-run
    python3 -m ingest.run ingest/manifests/ndvi_s2.yaml --synthetic --limit 3

Tiling is automatic: an extent larger than the pixel budget is cut into a grid
(see ingest/tiling.py) and each tile is fetched, written and aggregated on its
own. An extent that already fits runs in one pass exactly as it did before,
and records itself as the untiled tile '-'.

Resuming is per tile and it is the default. `--restart` ignores existing
progress; nothing else does.

`--synthetic` runs the entire pipeline against generated rasters instead of a
real source. That is how this was developed and tested without cloud access,
and it stays useful afterwards as a fast end-to-end check that does not burn
Earth Engine quota.
"""

import argparse
import sys
import time
import zlib
from pathlib import Path
from typing import Iterable, List, Optional

from ingest import tiling
from ingest.aggregate import CellStat, aggregate_array, aggregate_cog
from ingest.cog import synthetic_raster, write_categorical_cog, write_cog
from ingest.manifest import Manifest
from ingest.progress import FileProgress, PostgresProgress, Progress

# The schema lives in ingest/migrations/, applied by ingest/migrate.py. It used
# to be inline CREATE TABLE IF NOT EXISTS here, which works exactly once and
# cannot add a column — and adding a column is what tiling needed.


DEFAULT_BBOX = [-6.42, 49.86, 1.77, 55.81]          # England

# Above this, a single timestep will not fit in a modest machine's memory:
# 100 M float32 pixels is 400 MB for the array alone, before the COG writer
# takes its copy. Refusing loudly beats being killed by the OOM reaper halfway
# through month nine of a backfill.
MAX_PIXELS = 100_000_000


def raster_shape(bbox, resolution_m: float) -> tuple:
    """Pixel dimensions of `bbox` at `resolution_m`, in EPSG:4326.

    Longitude degrees shrink with latitude, so a metre resolution over England
    is about 1.6× more longitude degrees per pixel than latitude degrees. Using
    one number for both — which is the easy mistake — produces a raster
    stretched by 60% and cell statistics that are quietly wrong.
    """
    import math

    west, south, east, north = bbox
    mid = math.radians((south + north) / 2)
    deg_lat = resolution_m / 111_320.0
    deg_lon = resolution_m / (111_320.0 * max(0.1, math.cos(mid)))
    width = max(1, int(round((east - west) / deg_lon)))
    height = max(1, int(round((north - south) / deg_lat)))
    return width, height


def fetch_raster(manifest: Manifest, timestep: str, synthetic: bool,
                 out_dir: Path, window: Optional[tuple] = None,
                 shape: Optional[tuple] = None):
    """Produce a raster for one timestep.

    With `--synthetic` this generates one **at the manifest's declared extent
    and resolution**. That distinction matters: a synthetic run that quietly
    substituted a fixed 512×512 tile would exercise the code path but measure
    nothing, because every cost in this pipeline — pixels, COG size, H3 cells,
    rows — scales with extent and resolution and with nothing else. The
    generated *values* are meaningless; the shape of the work is not.

    In production this is where the Earth Engine export, or the HTTP fetch, or
    the S3 copy goes — the rest of the pipeline does not care which, because it
    only ever sees an array plus a transform.
    """
    if not synthetic:
        raise NotImplementedError(
            f"source driver {manifest.source.get('driver')!r} needs cloud "
            "credentials; run with --synthetic until those exist"
        )

    window = tuple(window or manifest.spatial.bbox or DEFAULT_BBOX)
    # A tile passes its own pixel dimensions rather than letting them be
    # recomputed from its bbox. Recomputing rounds independently, which puts a
    # tile's pixel grid a fraction of a pixel off the grid its neighbours and
    # the untiled run use — and a shifted grid moves which cell each pixel
    # centre falls in, so cells near tile edges end up with different pixel
    # counts and different means. Caught by
    # test_a_tiled_run_and_an_untiled_run_reach_the_same_table.
    width, height = shape or raster_shape(window, manifest.spatial.resolution_m)
    if width * height > MAX_PIXELS:
        # A backstop, not the tiling boundary: run_manifest cuts the extent to
        # ingest.tiling.TILE_PIXEL_BUDGET, which is well under this. Reaching
        # here means something asked for an untiled window directly.
        raise SystemExit(
            f"{width:,}×{height:,} = {width * height / 1e6:,.0f} M pixels for one "
            f"timestep of {manifest.id} at {manifest.spatial.resolution_m} m.\n"
            f"That will not fit in memory. Run it through run_manifest, which "
            f"tiles anything this large, or pass a smaller --window."
        )

    # Seeded on the dataset and timestep only — deliberately not on the
    # window. `synthetic_raster` samples a global surface, so one month is one
    # surface and a tile is a view of it. Seeding per tile would make every
    # tile an unrelated random field, which looks fine and makes it impossible
    # to check a tiled run against an untiled one.
    #
    # `source.seed` lets two manifests share a surface, which is how a tiled
    # run is compared against an untiled one: they need different dataset ids
    # to sit in the table together, and identical pixels to be comparable.
    surface = manifest.source.get("seed", manifest.id)
    seed = zlib.crc32(f"{surface}:{timestep}".encode()) % (2 ** 31)
    data, transform = synthetic_raster(
        window, width, height, seed=seed, kind=manifest.kind,
        lo=-0.2, hi=0.9, nodata=manifest.nodata,
        nodata_fraction=0.15 if manifest.nodata is not None else 0.0,
    )
    return data, transform, window


def run_manifest(manifest: Manifest, *, synthetic: bool, limit: Optional[int],
                 out_dir: Path, dsn: Optional[str], dry_run: bool,
                 window: Optional[tuple] = None,
                 stats_out: Optional[dict] = None,
                 tile_pixels: int = tiling.TILE_PIXEL_BUDGET,
                 restart: bool = False) -> int:
    steps = manifest.timesteps()
    if limit:
        steps = steps[:limit]

    extent = tuple(window or manifest.spatial.bbox or DEFAULT_BBOX)
    px_w, px_h = raster_shape(extent, manifest.spatial.resolution_m)
    tiles = tiling.plan(extent, px_w, px_h, tile_pixels)

    print(f"{manifest.id}: {len(steps)} timestep(s), "
          f"H3 res {manifest.h3_resolutions}, kind={manifest.kind}")
    print(f"  extent {extent}  ->  {px_w:,}x{px_h:,} px at "
          f"{manifest.spatial.resolution_m} m ({px_w * px_h / 1e6:.1f} M/timestep)")
    print(f"  {tiling.describe(tiles)}, "
          f"{len(steps) * len(tiles):,} tile-timesteps to do")

    if dry_run:
        for step in steps[:3]:
            for tile in tiles[:3]:
                print(f"  would write {manifest.asset_key(step, tile.id)}")
        remaining = len(steps) * len(tiles) - min(3, len(steps)) * min(3, len(tiles))
        if remaining > 0:
            print(f"  ... and {remaining:,} more")
        return 0

    conn = None
    progress: Progress
    if dsn:
        import psycopg
        conn = psycopg.connect(dsn, autocommit=False)
        # The schema is migrations' job, but a runner that fails with
        # "column tile does not exist" three hours into a backfill is a bad
        # trade against applying two idempotent files at startup.
        from ingest import migrate
        migrate.apply(conn, manifest.h3_resolutions, verbose=False)
        progress = PostgresProgress(conn)
    else:
        progress = FileProgress(out_dir / f".{manifest.id}.progress.json")

    # Tile ids are positions in a grid, so resuming a 8x6 run against 12x9
    # progress would skip work that was never done. Refuse instead.
    if not restart:
        tiling.check_grid(tiles, progress.grid_for(manifest.id))

    total_cells = 0
    t_start = time.perf_counter()
    # Per-stage seconds, so a slow run says *which* stage is slow. Ingest that
    # only reports a total tells you it is too slow and nothing about why.
    stage = {"fetch": 0.0, "cog": 0.0, "aggregate": 0.0, "load": 0.0}
    cog_bytes = 0
    done_units = 0
    skipped = 0

    for step in steps:
        for tile in tiles:
            pending = [r for r in manifest.h3_resolutions
                       if restart or not progress.done(manifest.id, step, tile.id, r)]
            if not pending:
                skipped += 1
                continue

            t0 = time.perf_counter()
            data, transform, bounds = fetch_raster(
                manifest, step, synthetic, out_dir, window=tile.bbox,
                shape=(tile.width, tile.height))
            stage["fetch"] += time.perf_counter() - t0

            # 1. COG to object storage (local dir stands in for it here).
            t1 = time.perf_counter()
            cog_path = out_dir / manifest.asset_key(step, tile.id)
            if manifest.kind == "categorical":
                # Class codes are already integers and must never be scaled —
                # a scaled land-cover code is not a land-cover code.
                write_categorical_cog(cog_path, data, transform, "EPSG:4326",
                                      nodata=manifest.nodata)
            else:
                write_cog(cog_path, data, transform, "EPSG:4326",
                          nodata=manifest.nodata,
                          scale=manifest.storage.write_scale,
                          offset=manifest.storage.offset)
            stage["cog"] += time.perf_counter() - t1
            cog_bytes += cog_path.stat().st_size

            # 2. Aggregate to every declared H3 tier that still needs it.
            for res in pending:
                t2 = time.perf_counter()
                stats = list(aggregate_array(
                    data, transform, bounds, dataset_id=manifest.id, t=step,
                    res=res, kind=manifest.kind, nodata=manifest.nodata,
                ))
                stage["aggregate"] += time.perf_counter() - t2
                total_cells += len(stats)
                if conn:
                    t3 = time.perf_counter()
                    # The rows and the progress mark commit together. A tile is
                    # either fully merged and recorded or neither — anything
                    # in between would let a retry double-count a cell that
                    # spans two tiles.
                    _load(conn, res, stats)
                    progress.mark(manifest.id, step, tile.id, res,
                                  len(stats), tile.grid)
                    conn.commit()
                    stage["load"] += time.perf_counter() - t3
                else:
                    progress.mark(manifest.id, step, tile.id, res,
                                  len(stats), tile.grid)

            done_units += 1
            label = step if tile.untiled else f"{step} {tile.id}"
            print(f"  {label}: {cog_path.stat().st_size // 1024} KiB COG, "
                  f"{total_cells:,} cells cumulative, "
                  f"{time.perf_counter() - t0:.2f}s")

    if conn:
        conn.commit()
        conn.close()

    elapsed = time.perf_counter() - t_start
    print(f"{manifest.id}: done in {elapsed:.1f}s, {total_cells:,} cell-rows")
    if skipped:
        print(f"  {skipped:,} tile-timestep(s) already ingested, skipped")
    if done_units:
        print("  per tile: " + "  ".join(
            f"{k} {v / done_units:.2f}s" for k, v in stage.items() if v))
        print(f"  {elapsed / done_units:.2f}s/tile, "
              f"{cog_bytes / done_units / 1e6:.1f} MB COG/tile, "
              f"{total_cells / done_units:,.0f} cells/tile")
    if stats_out is not None:
        stats_out.update(steps=done_units, seconds=elapsed, cells=total_cells,
                         cog_bytes=cog_bytes, stage=stage,
                         pixels=px_w * px_h, extent=extent,
                         tiles=len(tiles), grid=tiles[0].grid, skipped=skipped)
    return 0


def _load(conn, res: int, stats: Iterable[CellStat]) -> None:
    """Merge a tile's statistics into the fast tier.

    Not an overwrite. An H3 cell on a tile boundary arrives once per tile it
    touches, each time covering only that tile's pixels, so the old
    `DO UPDATE SET mean = EXCLUDED.mean` left such a cell holding whichever
    sliver happened to be written last — a wrong number, on every tile edge in
    the country, with nothing to notice it by.

    This is Chan's parallel variance merge in SQL, and it matches
    `aggregate.merge_stats` line for line. `m2` is the sum of squared
    deviations, so combining two partial aggregations is exact rather than
    approximate: the merged row is indistinguishable from one produced by
    aggregating the whole raster in a single pass, which is what
    `test_ingest.py` asserts.

    Re-running a tile that already committed would double-count. That is
    prevented upstream — a committed tile is a recorded tile, and a recorded
    tile is skipped — not here.
    """
    rows = [s.as_row() for s in stats]
    if not rows:
        return
    with conn.cursor() as cur:
        cur.executemany(
            f"""INSERT INTO cell_stats_r{res}
                  (dataset_id, h3, t, mean, min, max, stddev, valid_fraction,
                   n_valid, n_total, m2)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (dataset_id, h3, t) DO UPDATE SET
                  mean = CASE
                    WHEN cell_stats_r{res}.n_valid + EXCLUDED.n_valid = 0 THEN NULL
                    WHEN cell_stats_r{res}.n_valid = 0 THEN EXCLUDED.mean
                    WHEN EXCLUDED.n_valid = 0 THEN cell_stats_r{res}.mean
                    ELSE (cell_stats_r{res}.mean * cell_stats_r{res}.n_valid
                          + EXCLUDED.mean * EXCLUDED.n_valid)
                         / (cell_stats_r{res}.n_valid + EXCLUDED.n_valid)
                  END,
                  min = LEAST(cell_stats_r{res}.min, EXCLUDED.min),
                  max = GREATEST(cell_stats_r{res}.max, EXCLUDED.max),
                  m2 = CASE
                    WHEN cell_stats_r{res}.n_valid = 0 THEN EXCLUDED.m2
                    WHEN EXCLUDED.n_valid = 0 THEN cell_stats_r{res}.m2
                    ELSE cell_stats_r{res}.m2 + EXCLUDED.m2
                         + power(EXCLUDED.mean - cell_stats_r{res}.mean, 2)
                           * cell_stats_r{res}.n_valid * EXCLUDED.n_valid
                           / (cell_stats_r{res}.n_valid + EXCLUDED.n_valid)
                  END,
                  stddev = CASE
                    WHEN cell_stats_r{res}.n_valid + EXCLUDED.n_valid = 0 THEN NULL
                    ELSE sqrt(
                      (CASE
                        WHEN cell_stats_r{res}.n_valid = 0 THEN EXCLUDED.m2
                        WHEN EXCLUDED.n_valid = 0 THEN cell_stats_r{res}.m2
                        ELSE cell_stats_r{res}.m2 + EXCLUDED.m2
                             + power(EXCLUDED.mean - cell_stats_r{res}.mean, 2)
                               * cell_stats_r{res}.n_valid * EXCLUDED.n_valid
                               / (cell_stats_r{res}.n_valid + EXCLUDED.n_valid)
                       END)
                      / (cell_stats_r{res}.n_valid + EXCLUDED.n_valid))
                  END,
                  n_valid = cell_stats_r{res}.n_valid + EXCLUDED.n_valid,
                  n_total = cell_stats_r{res}.n_total + EXCLUDED.n_total,
                  valid_fraction = CASE
                    WHEN cell_stats_r{res}.n_total + EXCLUDED.n_total = 0 THEN 0
                    ELSE (cell_stats_r{res}.n_valid + EXCLUDED.n_valid)::real
                         / (cell_stats_r{res}.n_total + EXCLUDED.n_total)
                  END""",
            rows,
        )


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--synthetic", action="store_true",
                    help="generate rasters instead of fetching real ones")
    ap.add_argument("--limit", type=int, help="only the first N timesteps")
    ap.add_argument("--out", type=Path, default=Path("/tmp/site-scanner-cogs"))
    ap.add_argument("--dsn", help="Postgres DSN; omitted means COGs only")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--window", type=float, nargs=4,
                    metavar=("W", "S", "E", "N"),
                    help="ingest a sub-extent of the manifest's bbox")
    ap.add_argument("--tile-pixels", type=int, default=tiling.TILE_PIXEL_BUDGET,
                    help="pixels per tile; the extent is cut into a grid so no "
                         "tile exceeds this (default %(default)s)")
    ap.add_argument("--restart", action="store_true",
                    help="ignore recorded progress and redo every tile")
    args = ap.parse_args(argv)

    manifest = Manifest.load(args.manifest)
    return run_manifest(manifest, synthetic=args.synthetic, limit=args.limit,
                        out_dir=args.out, dsn=args.dsn, dry_run=args.dry_run,
                        window=tuple(args.window) if args.window else None,
                        tile_pixels=args.tile_pixels, restart=args.restart)


if __name__ == "__main__":
    sys.exit(main())
