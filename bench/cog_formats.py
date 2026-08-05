#!/usr/bin/env python3
"""
How much of a COG's size is the data, and how much is the storage format?

Written for docs/INGEST-BENCHMARK.md Result 5, which found the pipeline is
storing NDVI at six times the size it needs and that its own synthetic test
data overstates storage by 79%. Both were invisible until the same raster was
written four ways and the files compared.

    python3 -m bench.cog_formats                       # Surrey at 10 m
    python3 -m bench.cog_formats --bbox -0.85 51.07 -0.6 51.2 --res 10

Values are synthetic, which is fine for this question: the field varies
smoothly the way real NDVI does, and compression cares about that and not
about whether the numbers mean anything.
"""

import argparse
import pathlib
import tempfile
import time

import numpy as np

from ingest.cog import synthetic_raster, write_cog
from ingest.run import raster_shape

SURREY = (-0.85, 51.07, 0.06, 51.47)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbox", type=float, nargs=4, default=list(SURREY),
                    metavar=("W", "S", "E", "N"))
    ap.add_argument("--res", type=float, default=10.0, help="metres per pixel")
    args = ap.parse_args(argv)

    bbox = tuple(args.bbox)
    width, height = raster_shape(bbox, args.res)
    print(f"{width:,}×{height:,} = {width * height / 1e6:.1f} M px, "
          f"raw float32 = {width * height * 4 / 1e6:,.0f} MB\n")

    out = pathlib.Path(tempfile.mkdtemp(prefix="cog-formats-"))
    rows = []

    def write(name, data, nodata):
        t0 = time.perf_counter()
        path = write_cog(out / f"{len(rows)}.tif", data, transform,
                         "EPSG:4326", nodata=nodata)
        rows.append((name, path.stat().st_size / 1e6, time.perf_counter() - t0))

    # 1. Exactly what the pipeline writes today: float32, and nodata scattered
    #    as independent per-pixel holes.
    noisy, transform = synthetic_raster(bbox, width, height, seed=1,
                                        lo=-0.2, hi=0.9, nodata=-9999,
                                        nodata_fraction=0.15)
    write("float32, 15% per-pixel nodata (current)", noisy, -9999)

    # 2. The same fraction of nodata, but contiguous — which is what a cloud
    #    mask actually looks like. A second smooth field thresholded low makes
    #    blobs of roughly the right size.
    clean, _ = synthetic_raster(bbox, width, height, seed=1, lo=-0.2, hi=0.9)
    mask, _ = synthetic_raster(bbox, width, height, seed=99, lo=0.0, hi=1.0)
    blobs = np.where(mask < 0.15, np.float32(-9999), clean)
    write("float32, ~15% cloud as blobs", blobs, -9999)

    # 3. int16 scaled by 10,000 — NDVI to four decimal places, which is three
    #    more than anyone reads.
    scaled = np.where(blobs == -9999, np.int16(-32768),
                      (blobs * 10000).astype(np.int16))
    write("int16 ×10000, blobs", scaled, -32768)

    # 4. No nodata at all, as the floor for comparison.
    write("float32, no nodata", clean, None)

    base = rows[0][1]
    for name, size, secs in rows:
        print(f"  {name:<42} {size:7.1f} MB  {size / base:5.2f}×  "
              f"{secs:5.1f}s write")
    print(f"\nWritten to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
