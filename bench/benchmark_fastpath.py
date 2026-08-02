"""
Phase 0 — does the "instant" timeline actually hold up?

TECHNICAL_PLAN.md §1 stakes the whole product on one claim: that a drawn shape
can return its entire 15-year monthly series fast enough to feel instant. That
claim rests on pre-aggregated H3 cells, and it is the assumption everything
else is built on. This measures it before more is built on top.

The data is synthetic, but nothing that governs query cost is:

  * the cell set is a real England outline tiled at H3 resolutions 7 and 8
  * 180 real monthly timesteps, 2011-01 to 2025-12
  * the row count, index shape, query plan and on-disk volume are all real

What is *not* production-identical, and why that makes this conservative:

  * Plain PostgreSQL rather than TimescaleDB — no chunk exclusion, no
    compression, no continuous aggregates. Timescale would be faster, so a
    pass here is a pass there.
  * No PostGIS. It is not needed: the AOI is resolved to H3 cells in the
    application layer, which is exactly how production works. PostGIS stores
    the AOI geometry; it takes no part in this query.

Two findings came out of this that change the design — see BENCHMARK.md.

Run:
    pg_ctlcluster 16 main start
    python3 -m bench.benchmark_fastpath --build
    python3 -m bench.benchmark_fastpath
"""

import argparse
import math
import os
import statistics
import sys
import time
from typing import Dict, List, Sequence, Tuple

import h3
import psycopg

from bench.england import ENGLAND_OUTLINE

DSN = os.environ.get(
    "BENCH_DSN", "postgresql://postgres:bench@127.0.0.1:5432/sitescanner"
)
MONTHS = 180                       # 2011-01 .. 2025-12
RESOLUTIONS = (7, 8)
N_DATASETS = 2

# AOI sizes worth testing, in hectares. A small field, a large field, a farm,
# an estate, a district, and the interactive cap in routes_catalog.py.
AOI_SIZES_HA = [5, 20, 100, 1_600, 25_000, 250_000]

CENTRE = (-1.5, 52.5)              # roughly the middle of England


def table_for(res: int) -> str:
    return f"cell_stats_r{res}"


def england_cells(res: int) -> List[int]:
    poly = h3.LatLngPoly([(lat, lng) for lng, lat in ENGLAND_OUTLINE])
    return [h3.str_to_int(c) for c in h3.polygon_to_cells(poly, res)]


def circle_poly(area_ha: float, n: int = 64) -> h3.LatLngPoly:
    radius_km = ((area_ha / 100.0) / math.pi) ** 0.5
    lng0, lat0 = CENTRE
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        pts.append((
            lat0 + (radius_km / 111.32) * math.sin(a),
            lng0 + (radius_km / (111.32 * math.cos(math.radians(lat0)))) * math.cos(a),
        ))
    pts.append(pts[0])
    return h3.LatLngPoly(pts)


def aoi_cells(area_ha: float, res: int, overlap: bool) -> List[int]:
    """Resolve an AOI to cells, the way the API layer will.

    `overlap` is the finding that matters. H3's default containment keeps only
    cells whose *centre* falls inside the polygon, so an AOI smaller than one
    cell selects nothing at all — a 20 ha field against 74 ha res-8 cells
    returns an empty set and the user sees a blank report. Overlap containment
    keeps every cell the polygon touches, which is the correct semantics for
    ""what is under this shape".
    """
    poly = circle_poly(area_ha)
    if overlap:
        return [h3.str_to_int(c)
                for c in h3.polygon_to_cells_experimental(poly, res, contain="overlap")]
    return [h3.str_to_int(c) for c in h3.polygon_to_cells(poly, res)]


def build(conn: psycopg.Connection, resolutions: Sequence[int]) -> None:
    for res in resolutions:
        table = table_for(res)
        cells = england_cells(res)
        print(f"Building {table}: {len(cells):,} cells x {MONTHS} months x {N_DATASETS} datasets")

        with conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {table}, cells_r{res} CASCADE")
            cur.execute(f"CREATE TABLE cells_r{res} (h3 bigint PRIMARY KEY)")
            with cur.copy(f"COPY cells_r{res} (h3) FROM STDIN") as cp:
                for c in cells:
                    cp.write_row((c,))

            # dataset_id leads the key deliberately. A query asks for a handful
            # of datasets over many cells and every timestep, so leading with
            # the dataset keeps each one's rows physically contiguous. Leading
            # with h3 would scatter every dataset across the whole index.
            cur.execute(f"""
                CREATE TABLE {table} (
                  dataset_id     smallint NOT NULL,
                  h3             bigint   NOT NULL,
                  t              date     NOT NULL,
                  mean           real,
                  valid_fraction real     NOT NULL
                )
            """)
            conn.commit()

            t0 = time.perf_counter()
            cur.execute(f"""
                INSERT INTO {table} (dataset_id, h3, t, mean, valid_fraction)
                SELECT d.id, c.h3,
                       (DATE '2011-01-01' + (m.n || ' month')::interval)::date,
                       (random() * 100)::real,
                       (0.2 + random() * 0.8)::real
                FROM cells_r{res} c
                CROSS JOIN generate_series(0, %s) AS m(n)
                CROSS JOIN generate_series(1, %s) AS d(id)
            """, (MONTHS - 1, N_DATASETS))
            conn.commit()
            cur.execute(f"ALTER TABLE {table} ADD PRIMARY KEY (dataset_id, h3, t)")
            conn.commit()

            # VACUUM cannot run inside a transaction block, and psycopg opens
            # one implicitly for every statement.
            conn.autocommit = True
            cur.execute(f"VACUUM ANALYZE {table}")
            conn.autocommit = False

            cur.execute(f"SELECT count(*), pg_size_pretty(pg_total_relation_size('{table}'))")
            rows, size = cur.fetchone()
            print(f"  {rows:,} rows, {size}, built in {time.perf_counter() - t0:.0f}s\n")


QUERY = """
SELECT t, dataset_id,
       sum(mean * valid_fraction) / nullif(sum(valid_fraction), 0) AS mean,
       avg(valid_fraction) AS confidence
FROM {table}
WHERE dataset_id = ANY(%s) AND h3 = ANY(%s)
GROUP BY t, dataset_id
ORDER BY t
"""


def timed(conn: psycopg.Connection, res: int, cells: List[int],
          runs: int) -> Tuple[float, float, int]:
    sql = QUERY.format(table=table_for(res))
    datasets = list(range(1, N_DATASETS + 1))
    samples: List[float] = []
    out_rows = 0
    for _ in range(runs):
        with conn.cursor() as cur:
            t0 = time.perf_counter()
            cur.execute(sql, (datasets, cells))
            out_rows = len(cur.fetchall())
            samples.append((time.perf_counter() - t0) * 1000.0)
    return statistics.median(samples), sorted(samples)[int(len(samples) * 0.95) - 1], out_rows


def verdict(p95: float, empty: bool) -> str:
    if empty:
        return "NO DATA"
    if p95 < 100:
        return "instant"
    if p95 < 400:
        return "usable"
    return "TOO SLOW"


def run(conn: psycopg.Connection, runs: int) -> None:
    print("=" * 96)
    print("A. Default centre-containment — H3's out-of-the-box behaviour")
    print("=" * 96)
    print(f"{'AOI':>12} {'res':>4} {'cells':>7} {'rows read':>11} "
          f"{'p50 ms':>8} {'p95 ms':>8}   verdict")
    print("-" * 96)
    for area_ha in AOI_SIZES_HA:
        cells = aoi_cells(area_ha, 8, overlap=False)
        label = f"{area_ha:,} ha" if area_ha < 10000 else f"{area_ha / 100:,.0f} km²"
        if not cells:
            print(f"{label:>12} {8:>4} {0:>7} {0:>11} {'—':>8} {'—':>8}   "
                  f"NO DATA  <-- AOI smaller than one cell")
            continue
        p50, p95, _ = timed(conn, 8, cells, runs)
        print(f"{label:>12} {8:>4} {len(cells):>7,} {len(cells) * MONTHS * N_DATASETS:>11,} "
              f"{p50:>8.1f} {p95:>8.1f}   {verdict(p95, False)}")

    print()
    print("=" * 96)
    print("B. Overlap containment, per resolution — every cell the shape touches")
    print("=" * 96)
    print(f"{'AOI':>12} {'res':>4} {'cells':>7} {'rows read':>11} "
          f"{'p50 ms':>8} {'p95 ms':>8}   verdict")
    print("-" * 96)
    best: Dict[float, Tuple[int, float]] = {}
    for area_ha in AOI_SIZES_HA:
        label = f"{area_ha:,} ha" if area_ha < 10000 else f"{area_ha / 100:,.0f} km²"
        for res in RESOLUTIONS:
            cells = aoi_cells(area_ha, res, overlap=True)
            if not cells:
                print(f"{label:>12} {res:>4} {0:>7} {0:>11} {'—':>8} {'—':>8}   NO DATA")
                continue
            p50, p95, _ = timed(conn, res, cells, runs)
            v = verdict(p95, False)
            print(f"{label:>12} {res:>4} {len(cells):>7,} "
                  f"{len(cells) * MONTHS * N_DATASETS:>11,} {p50:>8.1f} {p95:>8.1f}   {v}")
            if v == "instant" and (area_ha not in best or res > best[area_ha][0]):
                best[area_ha] = (res, p95)
        print()

    print("=" * 96)
    print("Finest resolution that still answers instantly, per AOI size")
    print("=" * 96)
    for area_ha in AOI_SIZES_HA:
        label = f"{area_ha:,} ha" if area_ha < 10000 else f"{area_ha / 100:,.0f} km²"
        if area_ha in best:
            res, p95 = best[area_ha]
            print(f"  {label:>12}  ->  res {res}  ({p95:.0f} ms p95)")
        else:
            print(f"  {label:>12}  ->  none instant at res {RESOLUTIONS} — needs a coarser tier")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true", help="(re)build the tables")
    ap.add_argument("--runs", type=int, default=25)
    args = ap.parse_args()

    with psycopg.connect(DSN, autocommit=False) as conn:
        if args.build:
            build(conn, RESOLUTIONS)
        run(conn, args.runs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
