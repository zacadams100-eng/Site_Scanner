#!/usr/bin/env python3
"""
Query what the ingest run just wrote, from real AOIs inside Surrey.

An ingest pipeline that writes rows nobody can read is not an ingest pipeline,
so docs/INGEST-BENCHMARK.md does not stop at "151.7s, 60,828 rows". This takes
three shapes people would actually draw in Surrey, resolves each to H3 cells
the way the application does, and asks for its series.

    python3 -m ingest.run ingest/manifests/ndvi_s2_surrey.yaml \
        --synthetic --dsn postgresql://postgres@127.0.0.1/ingest_bench
    python3 -m bench.ingest_readback --dsn postgresql://postgres@127.0.0.1/ingest_bench

Exit status is non-zero if any AOI comes back short — which is the failure the
overlap-containment fix exists to prevent, and the one that would otherwise
look like an empty chart rather than an error.

The timings it prints are **not** comparable to BENCHMARK.md's. That table held
70.8 M rows; a twelve-month Surrey ingest holds 53 thousand, which fits
entirely in shared_buffers. Sub-millisecond here means the table is small, not
that anything got faster.
"""

import argparse
import statistics
import sys
import time

import h3

from ingest.aggregate import cells_for_bounds

# Real places, and the range of sizes the tool has to cover: a field, a town
# centre, and a landscape designation.
AOIS = [
    ("A field near Shere", (-0.435, 51.208, -0.425, 51.214)),
    ("Guildford town centre", (-0.585, 51.230, -0.555, 51.245)),
    ("Surrey Hills AONB core", (-0.62, 51.16, -0.30, 51.28)),
]


def area_km2(bbox) -> float:
    import math

    west, south, east, north = bbox
    mid = math.radians((south + north) / 2)
    return (east - west) * 111.32 * math.cos(mid) * (north - south) * 111.32


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--dataset", default="ndvi_s2_surrey")
    ap.add_argument("--runs", type=int, default=25)
    args = ap.parse_args(argv)

    import psycopg

    failures = []
    with psycopg.connect(args.dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*), count(distinct t) FROM cell_stats_r8 "
                    "WHERE dataset_id = %s", (args.dataset,))
        rows, months = cur.fetchone()
        if not rows:
            print(f"No rows for {args.dataset!r} — run the ingest first.",
                  file=sys.stderr)
            return 1
        print(f"{args.dataset}: {rows:,} res-8 rows over {months} timesteps\n")

        for name, bbox in AOIS:
            km2 = area_km2(bbox)
            res = 8 if km2 <= 250 else 7          # BENCHMARK.md Result 3
            cells = [h3.str_to_int(c) for c in cells_for_bounds(bbox, res)]
            sql = (f"SELECT t, avg(mean) FROM cell_stats_r{res} "
                   "WHERE dataset_id = %s AND h3 = ANY(%s) "
                   "GROUP BY t ORDER BY t")

            cur.execute(sql, (args.dataset, cells))       # warm
            got = cur.fetchall()

            times = []
            for _ in range(args.runs):
                t0 = time.perf_counter()
                cur.execute(sql, (args.dataset, cells))
                cur.fetchall()
                times.append((time.perf_counter() - t0) * 1000)
            times.sort()

            print(f"{name:<26} {km2:7.1f} km²  res {res}  {len(cells):5d} cells  "
                  f"{len(got):2d} months  p50 {statistics.median(times):5.2f} ms  "
                  f"p95 {times[int(0.95 * len(times))]:5.2f} ms")

            if len(got) != months:
                failures.append(f"{name}: {len(got)} months, expected {months}")
            elif any(v is None for _, v in got):
                failures.append(f"{name}: a month aggregated to NULL")

    if failures:
        print("\n" + "\n".join("FAIL  " + f for f in failures), file=sys.stderr)
        return 1
    print(f"\nEvery AOI returned all {months} ingested months.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
