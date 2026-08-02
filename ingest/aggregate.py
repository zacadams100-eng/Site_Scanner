"""
Raster -> H3 cell aggregates.

This is the stage that produces the fast tier `BENCHMARK.md` measured. It runs
once per (dataset, timestep, resolution) during ingest, and its output is what
makes a drawn shape answer in single-digit milliseconds at query time.

Two decisions here are load-bearing and both come from findings elsewhere:

  * **Overlap containment, always.** H3's default keeps only cells whose centre
    falls inside the polygon, which returns nothing at all for an AOI smaller
    than one cell. BENCHMARK.md §"Result 2" — a 20 ha field silently produced
    an empty report. The same reasoning applies in reverse here: a cell is
    included if the raster covers it, not if its centre happens to land on a
    valid pixel.

  * **Categorical data is never averaged.** The mean of two land-cover class
    codes is meaningless (TECHNICAL_PLAN.md §8.5). Categorical rasters produce
    a class histogram; continuous ones produce mean/min/max/stddev. The
    `kind` flag on the manifest decides, and there is no path where a class
    code reaches a mean().
"""

from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Tuple

import h3
import numpy as np


@dataclass
class CellStat:
    """One row of the fast tier."""
    h3: int
    dataset_id: str
    t: str
    mean: Optional[float]
    min: Optional[float]
    max: Optional[float]
    stddev: Optional[float]
    valid_fraction: float
    class_counts: Optional[Dict[int, int]] = None

    def as_row(self) -> tuple:
        return (self.dataset_id, self.h3, self.t, self.mean, self.min,
                self.max, self.stddev, self.valid_fraction)


def cells_for_bounds(bounds: Tuple[float, float, float, float], res: int) -> List[str]:
    """Every H3 cell touching a lng/lat bounding box.

    Overlap containment — see the module docstring. A cell that the box merely
    clips still holds data for that box.
    """
    west, south, east, north = bounds
    poly = h3.LatLngPoly([
        (south, west), (south, east), (north, east), (north, west), (south, west),
    ])
    try:
        return list(h3.polygon_to_cells_experimental(poly, res, contain="overlap"))
    except AttributeError:            # older h3 builds
        return list(h3.polygon_to_cells(poly, res))


def _cell_pixel_indices(cell: str, transform, width: int, height: int
                        ) -> Tuple[np.ndarray, np.ndarray]:
    """Row/col indices of the pixels whose centres fall inside one H3 cell.

    Uses the cell's bounding box to slice, then a point-in-polygon test on the
    boundary — cheap, because a res-8 cell over a 10 m raster is only a few
    thousand pixels.
    """
    boundary = h3.cell_to_boundary(cell)            # [(lat, lng), ...]
    lats = [p[0] for p in boundary]
    lngs = [p[1] for p in boundary]

    # Affine transform maps (col, row) -> (lng, lat); invert for the window.
    inv = ~transform
    cols, rows = [], []
    for lng, lat in zip(lngs, lats):
        c, r = inv * (lng, lat)
        cols.append(c)
        rows.append(r)

    c0 = max(0, int(np.floor(min(cols))))
    c1 = min(width, int(np.ceil(max(cols))) + 1)
    r0 = max(0, int(np.floor(min(rows))))
    r1 = min(height, int(np.ceil(max(rows))) + 1)
    if c1 <= c0 or r1 <= r0:
        return np.array([], dtype=int), np.array([], dtype=int)

    rr, cc = np.mgrid[r0:r1, c0:c1]
    # Pixel centres back to lng/lat.
    xs, ys = transform * (cc.ravel() + 0.5, rr.ravel() + 0.5)
    inside = _points_in_ring(xs, ys, np.array(lngs), np.array(lats))
    return rr.ravel()[inside], cc.ravel()[inside]


def _points_in_ring(xs: np.ndarray, ys: np.ndarray,
                    ring_x: np.ndarray, ring_y: np.ndarray) -> np.ndarray:
    """Vectorised ray casting. H3 cells are convex hexagons, so this is exact."""
    inside = np.zeros(xs.shape, dtype=bool)
    n = len(ring_x)
    j = n - 1
    for i in range(n):
        xi, yi, xj, yj = ring_x[i], ring_y[i], ring_x[j], ring_y[j]
        straddles = (yi > ys) != (yj > ys)
        with np.errstate(divide="ignore", invalid="ignore"):
            xint = (xj - xi) * (ys - yi) / (yj - yi) + xi
        inside ^= straddles & (xs < xint)
        j = i
    return inside


def aggregate_array(data: np.ndarray, transform, bounds, *, dataset_id: str,
                    t: str, res: int, kind: str = "continuous",
                    nodata: Optional[float] = None) -> Iterator[CellStat]:
    """Aggregate an in-memory raster to H3 cells.

    Kept separate from any file I/O so it can be tested against synthetic
    arrays with no GeoTIFF on disk — which is what `tests/test_ingest.py` does.
    """
    height, width = data.shape
    if nodata is not None:
        valid_mask = data != nodata
    else:
        valid_mask = ~np.isnan(data) if np.issubdtype(data.dtype, np.floating) \
            else np.ones_like(data, dtype=bool)

    for cell in cells_for_bounds(bounds, res):
        rows, cols = _cell_pixel_indices(cell, transform, width, height)
        if rows.size == 0:
            continue

        values = data[rows, cols]
        valid = valid_mask[rows, cols]
        n_valid = int(valid.sum())
        valid_fraction = n_valid / values.size

        if n_valid == 0:
            # A cell with no usable pixels is still a fact worth recording —
            # it is how the UI knows to show a gap rather than nothing.
            yield CellStat(h3.str_to_int(cell), dataset_id, t,
                           None, None, None, None, 0.0)
            continue

        good = values[valid]
        if kind == "categorical":
            codes, counts = np.unique(good.astype(np.int64), return_counts=True)
            yield CellStat(
                h3.str_to_int(cell), dataset_id, t,
                None, None, None, None, valid_fraction,
                class_counts={int(c): int(n) for c, n in zip(codes, counts)},
            )
        else:
            good = good.astype(np.float64)
            yield CellStat(
                h3.str_to_int(cell), dataset_id, t,
                float(good.mean()), float(good.min()), float(good.max()),
                float(good.std()), valid_fraction,
            )


def aggregate_cog(path: str, *, dataset_id: str, t: str, res: int,
                  kind: str = "continuous") -> Iterator[CellStat]:
    """Aggregate a COG on disk or in object storage.

    Reads through rasterio, so an `s3://` or `https://` path streams via HTTP
    range requests rather than downloading the file — the property that makes
    the whole no-downloads architecture work.
    """
    import rasterio
    from rasterio.warp import transform_bounds

    with rasterio.open(path) as src:
        data = src.read(1)
        bounds = transform_bounds(src.crs, "EPSG:4326", *src.bounds) \
            if src.crs and src.crs.to_epsg() != 4326 else tuple(src.bounds)
        yield from aggregate_array(
            data, src.transform, bounds,
            dataset_id=dataset_id, t=t, res=res, kind=kind, nodata=src.nodata,
        )
