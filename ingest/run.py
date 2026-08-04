"""
The ingest runner.

One command executes any manifest. Stages are idempotent and keyed by
(dataset, timestep, resolution), so a backfill that dies at month 140 of 180
resumes rather than restarts — which matters when a full backfill is 180 jobs
that each take minutes.

    python3 -m ingest.run ingest/manifests/ndvi_s2.yaml --dry-run
    python3 -m ingest.run ingest/manifests/ndvi_s2.yaml --synthetic --limit 3

`--synthetic` runs the entire pipeline against generated rasters instead of a
real source. That is how this was developed and tested without cloud access,
and it stays useful afterwards as a fast end-to-end check that does not burn
Earth Engine quota.
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Iterable, List, Optional

from ingest.aggregate import CellStat, aggregate_array, aggregate_cog
from ingest.cog import synthetic_raster, write_categorical_cog, write_cog
from ingest.manifest import Manifest

DDL = """
CREATE TABLE IF NOT EXISTS cell_stats_r{res} (
  dataset_id     text     NOT NULL,
  h3             bigint   NOT NULL,
  t              text     NOT NULL,
  mean           real,
  min            real,
  max            real,
  stddev         real,
  valid_fraction real     NOT NULL,
  PRIMARY KEY (dataset_id, h3, t)
);

-- Which (dataset, timestep, resolution) triples are already done. This is what
-- makes a resumed backfill skip work rather than redo it.
CREATE TABLE IF NOT EXISTS ingest_progress (
  dataset_id text NOT NULL,
  t          text NOT NULL,
  h3_res     int  NOT NULL,
  n_cells    int  NOT NULL,
  done_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (dataset_id, t, h3_res)
);
"""


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
                 out_dir: Path, window: Optional[tuple] = None):
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
    width, height = raster_shape(window, manifest.spatial.resolution_m)
    if width * height > MAX_PIXELS:
        raise SystemExit(
            f"{width:,}×{height:,} = {width * height / 1e6:,.0f} M pixels for one "
            f"timestep of {manifest.id} at {manifest.spatial.resolution_m} m.\n"
            f"That will not fit in memory. Use --window to ingest a sub-extent, "
            f"or tile the manifest — which is what a national run at 10 m needs "
            f"regardless (see docs/INGEST-BENCHMARK.md)."
        )

    seed = abs(hash((manifest.id, timestep))) % (2 ** 31)
    data, transform = synthetic_raster(
        window, width, height, seed=seed, kind=manifest.kind,
        lo=-0.2, hi=0.9, nodata=manifest.nodata,
        nodata_fraction=0.15 if manifest.nodata is not None else 0.0,
    )
    return data, transform, window


def run_manifest(manifest: Manifest, *, synthetic: bool, limit: Optional[int],
                 out_dir: Path, dsn: Optional[str], dry_run: bool,
                 window: Optional[tuple] = None,
                 stats_out: Optional[dict] = None) -> int:
    steps = manifest.timesteps()
    if limit:
        steps = steps[:limit]

    extent = tuple(window or manifest.spatial.bbox or DEFAULT_BBOX)
    px_w, px_h = raster_shape(extent, manifest.spatial.resolution_m)
    print(f"{manifest.id}: {len(steps)} timestep(s), "
          f"H3 res {manifest.h3_resolutions}, kind={manifest.kind}")
    print(f"  extent {extent}  →  {px_w:,}×{px_h:,} px at "
          f"{manifest.spatial.resolution_m} m ({px_w * px_h / 1e6:.1f} M/timestep)")
    if dry_run:
        for s in steps[:5]:
            print(f"  would write {manifest.asset_key(s)}")
        if len(steps) > 5:
            print(f"  … and {len(steps) - 5} more")
        return 0

    conn = None
    if dsn:
        import psycopg
        conn = psycopg.connect(dsn, autocommit=False)
        with conn.cursor() as cur:
            for res in manifest.h3_resolutions:
                cur.execute(DDL.format(res=res))
        conn.commit()

    total_cells = 0
    t_start = time.perf_counter()
    # Per-stage seconds, so a slow run says *which* stage is slow. Ingest that
    # only reports a total tells you it is too slow and nothing about why.
    stage = {"fetch": 0.0, "cog": 0.0, "aggregate": 0.0, "load": 0.0}
    cog_bytes = 0
    done = 0

    for step in steps:
        if conn and _already_done(conn, manifest, step):
            print(f"  {step}: already ingested, skipping")
            continue

        t0 = time.perf_counter()
        data, transform, bounds = fetch_raster(manifest, step, synthetic,
                                               out_dir, window=extent)
        stage["fetch"] += time.perf_counter() - t0

        # 1. COG to object storage (local dir stands in for it here).
        t1 = time.perf_counter()
        cog_path = out_dir / manifest.asset_key(step)
        if manifest.kind == "categorical":
            # Class codes are already integers and must never be scaled — a
            # scaled land-cover code is not a land-cover code.
            write_categorical_cog(cog_path, data, transform, "EPSG:4326",
                                  nodata=manifest.nodata)
        else:
            write_cog(cog_path, data, transform, "EPSG:4326",
                      nodata=manifest.nodata,
                      scale=manifest.storage.write_scale,
                      offset=manifest.storage.offset)
        stage["cog"] += time.perf_counter() - t1
        cog_bytes += cog_path.stat().st_size

        # 2. Aggregate to every declared H3 tier.
        for res in manifest.h3_resolutions:
            t2 = time.perf_counter()
            stats = list(aggregate_array(
                data, transform, bounds, dataset_id=manifest.id, t=step,
                res=res, kind=manifest.kind, nodata=manifest.nodata,
            ))
            stage["aggregate"] += time.perf_counter() - t2
            total_cells += len(stats)
            if conn:
                t3 = time.perf_counter()
                _load(conn, res, stats)
                _mark_done(conn, manifest, step, res, len(stats))
                stage["load"] += time.perf_counter() - t3

        done += 1
        print(f"  {step}: {cog_path.stat().st_size // 1024} KiB COG, "
              f"{total_cells:,} cells cumulative, {time.perf_counter() - t0:.2f}s")

    if conn:
        conn.commit()
        conn.close()

    elapsed = time.perf_counter() - t_start
    print(f"{manifest.id}: done in {elapsed:.1f}s, {total_cells:,} cell-rows")
    if done:
        print("  per timestep: " + "  ".join(
            f"{k} {v / done:.2f}s" for k, v in stage.items() if v))
        print(f"  {elapsed / done:.2f}s/timestep, "
              f"{cog_bytes / done / 1e6:.1f} MB COG/timestep, "
              f"{total_cells / done:,.0f} cells/timestep")
    if stats_out is not None:
        stats_out.update(steps=done, seconds=elapsed, cells=total_cells,
                         cog_bytes=cog_bytes, stage=stage,
                         pixels=px_w * px_h, extent=extent)
    return 0


def _already_done(conn, manifest: Manifest, step: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM ingest_progress "
            "WHERE dataset_id = %s AND t = %s AND h3_res = ANY(%s)",
            (manifest.id, step, manifest.h3_resolutions),
        )
        return cur.fetchone()[0] == len(manifest.h3_resolutions)


def _load(conn, res: int, stats: Iterable[CellStat]) -> None:
    rows = [s.as_row() for s in stats]
    if not rows:
        return
    with conn.cursor() as cur:
        # ON CONFLICT rather than plain INSERT so a partial rerun overwrites
        # cleanly instead of failing on the primary key.
        cur.executemany(
            f"""INSERT INTO cell_stats_r{res}
                  (dataset_id, h3, t, mean, min, max, stddev, valid_fraction)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (dataset_id, h3, t) DO UPDATE SET
                  mean = EXCLUDED.mean, min = EXCLUDED.min, max = EXCLUDED.max,
                  stddev = EXCLUDED.stddev,
                  valid_fraction = EXCLUDED.valid_fraction""",
            rows,
        )


def _mark_done(conn, manifest: Manifest, step: str, res: int, n: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO ingest_progress (dataset_id, t, h3_res, n_cells)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (dataset_id, t, h3_res)
               DO UPDATE SET n_cells = EXCLUDED.n_cells, done_at = now()""",
            (manifest.id, step, res, n),
        )
    conn.commit()


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
                    help="ingest a sub-extent of the manifest's bbox; the way "
                         "a national run at 10 m is tiled")
    args = ap.parse_args(argv)

    manifest = Manifest.load(args.manifest)
    return run_manifest(manifest, synthetic=args.synthetic, limit=args.limit,
                        out_dir=args.out, dsn=args.dsn, dry_run=args.dry_run,
                        window=tuple(args.window) if args.window else None)


if __name__ == "__main__":
    sys.exit(main())
