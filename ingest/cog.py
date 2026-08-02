"""
COG writing, and synthetic rasters for testing without network access.

A Cloud-Optimised GeoTIFF is what makes "the user downloads nothing" true in
practice: internal tiling plus overviews means a client can HTTP range-read the
200 KB covering one field out of a 2 GB national raster. Writing them correctly
is not optional — a plain GeoTIFF on object storage has to be fetched whole.
"""

from pathlib import Path
from typing import Optional, Tuple

import numpy as np

COG_PROFILE = {
    "driver": "GTiff",
    "tiled": True,
    "blockxsize": 512,
    "blockysize": 512,
    # zstd beats deflate on both ratio and speed for continuous rasters, and
    # GDAL has shipped it since 2.3.
    "compress": "zstd",
    "zstd_level": 9,
    "predictor": 2,
    "interleave": "band",
    "BIGTIFF": "IF_SAFER",
}

# Powers of two down to roughly one screen's worth. Without these, low zoom
# levels force a full-resolution read of the whole country.
OVERVIEW_LEVELS = [2, 4, 8, 16, 32, 64]


def write_cog(path: Path, data: np.ndarray, transform, crs: str,
              nodata: Optional[float] = None) -> Path:
    """Write an array as a tiled, overviewed, compressed GeoTIFF."""
    import rasterio
    from rasterio.enums import Resampling

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    profile = dict(COG_PROFILE)
    profile.update(
        height=data.shape[0], width=data.shape[1], count=1,
        dtype=data.dtype.name, crs=crs, transform=transform,
    )
    if nodata is not None:
        profile["nodata"] = nodata

    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)
        # Averaging is right for continuous data. Categorical rasters need
        # mode/nearest instead, or a land-cover overview invents classes that
        # do not exist.
        dst.build_overviews(OVERVIEW_LEVELS, Resampling.average)
        dst.update_tags(ns="rio_overview", resampling="average")
    return path


def write_categorical_cog(path: Path, data: np.ndarray, transform, crs: str,
                          nodata: Optional[float] = None) -> Path:
    """As write_cog, but overviews use nearest-neighbour.

    Averaging class codes produces codes that mean nothing — the halfway point
    between 'tree cover' (10) and 'water' (80) is not 'shrubland' (45).
    """
    import rasterio
    from rasterio.enums import Resampling

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = dict(COG_PROFILE)
    profile.update(
        height=data.shape[0], width=data.shape[1], count=1,
        dtype=data.dtype.name, crs=crs, transform=transform,
    )
    if nodata is not None:
        profile["nodata"] = nodata
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)
        dst.build_overviews(OVERVIEW_LEVELS, Resampling.nearest)
        dst.update_tags(ns="rio_overview", resampling="nearest")
    return path


def synthetic_raster(bounds: Tuple[float, float, float, float], width: int,
                     height: int, *, seed: int = 0, kind: str = "continuous",
                     lo: float = 0.0, hi: float = 1.0,
                     nodata: Optional[float] = None,
                     nodata_fraction: float = 0.0):
    """A smoothly varying test raster with optional nodata holes.

    Exists so the whole pipeline — aggregation, COG writing, loading — can be
    exercised with no network and no credentials. Smooth rather than random on
    purpose: neighbouring H3 cells should relate to each other, otherwise the
    aggregation looks correct even when the pixel indexing is wrong.
    """
    from rasterio.transform import from_bounds

    rng = np.random.default_rng(seed)
    coarse = rng.random((max(2, height // 32), max(2, width // 32)))
    # Bilinear-ish upsample by repeating then box blurring.
    ys = np.linspace(0, coarse.shape[0] - 1, height)
    xs = np.linspace(0, coarse.shape[1] - 1, width)
    y0 = np.clip(ys.astype(int), 0, coarse.shape[0] - 2)
    x0 = np.clip(xs.astype(int), 0, coarse.shape[1] - 2)
    fy = (ys - y0)[:, None]
    fx = (xs - x0)[None, :]
    c = coarse
    field = (c[np.ix_(y0, x0)] * (1 - fy) * (1 - fx)
             + c[np.ix_(y0 + 1, x0)] * fy * (1 - fx)
             + c[np.ix_(y0, x0 + 1)] * (1 - fy) * fx
             + c[np.ix_(y0 + 1, x0 + 1)] * fy * fx)

    if kind == "categorical":
        data = (field * 7).astype(np.int16) * 10 + 10
    else:
        data = (lo + field * (hi - lo)).astype(np.float32)

    if nodata is not None and nodata_fraction > 0:
        holes = rng.random(data.shape) < nodata_fraction
        data = np.where(holes, nodata, data)

    transform = from_bounds(*bounds, width, height)
    return data, transform
