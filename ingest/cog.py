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
    # Horizontal differencing. Correct for integers, and only for integers —
    # floating-point data needs predictor 3, which is part of why storing
    # float32 here was costing more than it looked.
    "predictor": 2,
    "interleave": "band",
    "BIGTIFF": "IF_SAFER",
}

# Powers of two down to roughly one screen's worth. Without these, low zoom
# levels force a full-resolution read of the whole country.
OVERVIEW_LEVELS = [2, 4, 8, 16, 32, 64]

# ---------------------------------------------------------------------------
# Quantisation
#
# Continuous rasters are stored as scaled int16, not float32. Measured on the
# Surrey benchmark raster — 6,338 x 4,453 px at 10 m, same compression
# settings both ways:
#
#     float32, cloud gaps as blobs    50.9 MB
#     int16 x10000, same gaps         15.3 MB      0.30x
#     float32, per-pixel nodata       91.0 MB      (what this used to write)
#
# Across a national 15-year NDVI backfill that is 732 GB against 123 GB, which
# is the single largest cost lever in the pipeline (docs/INGEST-BENCHMARK.md
# Result 5). NDVI is bounded to [-1, 1] and nobody reads it past three
# decimals; int16 at a scale of 0.0001 carries four.
#
# The scale is written into the file as GDAL's band scale/offset, so anything
# opening the COG — QGIS, GDAL, rasterio, TiTiler — unscales it without being
# told. `read_band` below does the same for our own readers.
# ---------------------------------------------------------------------------
INT16_NODATA = -32768
_INT16_MIN, _INT16_MAX = -32767, 32767


class QuantisationError(ValueError):
    """Values do not fit the declared scale.

    Raised rather than clipped. Silently flattening the top of an elevation
    model to 1,638 m would be a plausible-looking raster that is wrong, and it
    would be discovered years later by someone wondering why every mountain is
    the same height.
    """


def quantise(data: np.ndarray, scale: float, offset: float = 0.0,
             nodata: Optional[float] = None) -> np.ndarray:
    """Float raster -> int16, following GDAL's convention.

    GDAL defines the relationship as `value = raw * scale + offset`, so a
    scale of 0.0001 means one raw unit is one ten-thousandth. Storing is the
    inverse. Nodata becomes INT16_NODATA regardless of what it was, because a
    float sentinel like -9999 does not survive scaling: at a scale of 0.05 it
    would need to be stored as -199,980, which int16 cannot hold.
    """
    if scale <= 0:
        raise QuantisationError(f"scale must be positive, got {scale!r}")

    values = np.asarray(data, dtype=np.float64)
    holes = np.zeros(values.shape, dtype=bool)
    if nodata is not None:
        holes = values == nodata
    holes |= ~np.isfinite(values)

    raw = np.where(holes, 0.0, (values - offset) / scale)
    real = raw[~holes]
    if real.size:
        lo, hi = float(real.min()), float(real.max())
        if lo < _INT16_MIN or hi > _INT16_MAX:
            span_lo = _INT16_MIN * scale + offset
            span_hi = _INT16_MAX * scale + offset
            raise QuantisationError(
                f"values span [{lo * scale + offset:.4g}, {hi * scale + offset:.4g}] "
                f"but scale={scale:g} offset={offset:g} can only store "
                f"[{span_lo:.4g}, {span_hi:.4g}]. Widen the scale, set an "
                f"offset, or declare a wider dtype in the manifest."
            )

    out = np.rint(raw).astype(np.int16)
    out[holes] = INT16_NODATA
    return out


def read_band(src) -> Tuple[np.ndarray, Optional[float]]:
    """Band 1 of an open rasterio dataset in real units, plus its nodata.

    Returns `(data, nodata)`. For a quantised raster the values come back as
    float32 with holes as NaN and `nodata` as None, because after scaling
    there is no integer sentinel left to compare against — -32768 x 0.0001 is
    -3.2768, a perfectly plausible NDVI. For an unquantised raster the array
    and its sentinel are returned unchanged.

    Every reader in this project goes through here. A reader that calls
    `src.read(1)` directly on a quantised COG gets values 10,000x too large
    and no error, which is the failure mode this function exists to make
    unreachable by accident.
    """
    raw = src.read(1)
    scale = (src.scales or [1.0])[0]
    offset = (src.offsets or [0.0])[0]
    if scale == 1.0 and offset == 0.0:
        return raw, src.nodata

    data = raw.astype(np.float32) * scale + offset
    if src.nodata is not None:
        data[raw == src.nodata] = np.nan
    return data, None


def write_cog(path: Path, data: np.ndarray, transform, crs: str,
              nodata: Optional[float] = None, scale: Optional[float] = None,
              offset: float = 0.0) -> Path:
    """Write an array as a tiled, overviewed, compressed GeoTIFF.

    Pass `scale` to store a float raster as int16 — see the quantisation notes
    above for why that is the default for every continuous manifest. Without
    it the array is written in whatever dtype it arrives in, which is what the
    categorical path and the tests want.
    """
    import rasterio
    from rasterio.enums import Resampling

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if scale is not None and np.issubdtype(data.dtype, np.floating):
        data = quantise(data, scale, offset, nodata)
        nodata = INT16_NODATA

    profile = dict(COG_PROFILE)
    profile.update(
        height=data.shape[0], width=data.shape[1], count=1,
        dtype=data.dtype.name, crs=crs, transform=transform,
    )
    if nodata is not None:
        profile["nodata"] = nodata

    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)
        if scale is not None:
            # The one thing that makes the file self-describing. Without these
            # tags a quantised NDVI raster opens in QGIS as values around
            # 7,000 and looks like a bug in our pipeline.
            dst.scales = (scale,)
            dst.offsets = (offset,)
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
