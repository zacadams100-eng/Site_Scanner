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


def fetch_raster(manifest: Manifest, timestep: str, synthetic: bool,
                 out_dir: Path):
    """Produce a raster for one timestep.

    With `--synthetic` this generates one. In production this is where the
    Earth Engine export, or the HTTP fetch, or the S3 copy goes — the rest of
    the pipeline does not care which, because it only ever sees an array plus
    a transform.
    """
    if not synthetic:
        raise NotImplementedError(
            f"source driver {manifest.source.get('driver')!r} needs cloud "
            "credentials; run with --synthetic until those exist"
        )

    bbox = manifest.spatial.bbox or [-6.42, 49.86, 1.77, 55.81]
    # A small window, not all of England — the point is to exercise the code
    # path, and a 10 m national raster will not fit in this sandbox.
    window = (bbox[0], bbox[1], bbox[0] + 0.25, bbox[1] + 0.25)
    seed = abs(hash((manifest.id, timestep))) % (2 ** 31)
    data, transform = synthetic_raster(
        window, 512, 512, seed=seed, kind=manifest.kind,
        lo=-0.2, hi=0.9, nodata=manifest.nodata,
        nodata_fraction=0.15 if manifest.nodata is not None else 0.0,
    )
    return data, transform, window


def run_manifest(manifest: Manifest, *, synthetic: bool, limit: Optional[int],
                 out_dir: Path, dsn: Optional[str], dry_run: bool) -> int:
    steps = manifest.timesteps()
    if limit:
        steps = steps[:limit]

    print(f"{manifest.id}: {len(steps)} timestep(s), "
          f"H3 res {manifest.h3_resolutions}, kind={manifest.kind}")
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

    for step in steps:
        if conn and _already_done(conn, manifest, step):
            print(f"  {step}: already ingested, skipping")
            continue

        t0 = time.perf_counter()
        data, transform, bounds = fetch_raster(manifest, step, synthetic, out_dir)

        # 1. COG to object storage (local dir stands in for it here).
        cog_path = out_dir / manifest.asset_key(step)
        writer = write_categorical_cog if manifest.kind == "categorical" else write_cog
        writer(cog_path, data, transform, "EPSG:4326", nodata=manifest.nodata)

        # 2. Aggregate to every declared H3 tier.
        for res in manifest.h3_resolutions:
            stats = list(aggregate_array(
                data, transform, bounds, dataset_id=manifest.id, t=step,
                res=res, kind=manifest.kind, nodata=manifest.nodata,
            ))
            total_cells += len(stats)
            if conn:
                _load(conn, res, stats)
                _mark_done(conn, manifest, step, res, len(stats))

        print(f"  {step}: {cog_path.stat().st_size // 1024} KiB COG, "
              f"{total_cells:,} cells cumulative, {time.perf_counter() - t0:.2f}s")

    if conn:
        conn.commit()
        conn.close()

    print(f"{manifest.id}: done in {time.perf_counter() - t_start:.1f}s, "
          f"{total_cells:,} cell-rows")
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
    args = ap.parse_args(argv)

    manifest = Manifest.load(args.manifest)
    return run_manifest(manifest, synthetic=args.synthetic, limit=args.limit,
                        out_dir=args.out, dsn=args.dsn, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
