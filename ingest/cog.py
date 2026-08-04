"""
COG writing, and synthetic rasters for testing without network access.

A Cloud-Optimised GeoTIFF is what makes "the user downloads nothing" true in
practice: internal tiling plus overviews means a client can HTTP range-read the
200 KB covering one field out of a 2 GB national raster. Writing them correctly
is not optional — a plain GeoTIFF on object storage has to be fetched whole.
"""

from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Tuple

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


# One coarse node every 0.005 degrees — roughly 350 m across England, which
# gives a field about as smooth as real vegetation at 10 m and a few hundred
# nodes across a county.
_LATTICE_DEG = 0.005


def _lattice(seed: int, gj: np.ndarray, gi: np.ndarray) -> np.ndarray:
    """Deterministic pseudo-random value in [0, 1) for absolute lattice nodes.

    A hash rather than an RNG, because the value at a given place on Earth has
    to be the same regardless of which window asked for it. This is what makes
    a tiled run produce exactly the same pixels as an untiled one.
    """
    h = (gi.astype(np.int64) * np.int64(73856093)) ^ \
        (gj.astype(np.int64) * np.int64(19349663)) ^ np.int64(seed * 83492791)
    h = h.astype(np.uint64)
    # xorshift-style avalanche; the constants are the usual splitmix64 ones.
    h ^= h >> np.uint64(30)
    h = h * np.uint64(0xBF58476D1CE4E5B9)
    h ^= h >> np.uint64(27)
    h = h * np.uint64(0x94D049BB133111EB)
    h ^= h >> np.uint64(31)
    return (h >> np.uint64(11)).astype(np.float64) / float(1 << 53)


def _smooth_fields(bounds, width: int, height: int,
                   seeds: Tuple[int, ...]) -> List[np.ndarray]:
    """One or more smooth surfaces sampled from a global lattice.

    Bilinear interpolation between lattice nodes at absolute coordinates, so
    the surface exists independently of the window looking at it. Ask for
    Surrey in one pass or in six tiles and every pixel matches.

    Several seeds are done together because the expensive part is neither the
    hashing nor the arithmetic but moving 28 million pixels through memory
    four times per surface. The pixel indices and interpolation weights are
    identical for every seed, so they are computed once.
    """
    west, south, east, north = bounds
    # Pixel centres, in lattice units.
    xs = (west + (np.arange(width) + 0.5) * (east - west) / width) / _LATTICE_DEG
    ys = (north - (np.arange(height) + 0.5) * (north - south) / height) / _LATTICE_DEG

    x0 = np.floor(xs).astype(np.int64)
    y0 = np.floor(ys).astype(np.int64)
    # Smoothstep the interpolation weights so the surface has no visible
    # lattice creases, which would otherwise read as tile seams.
    fx = (xs - x0).astype(np.float32)
    fy = (ys - y0).astype(np.float32)
    wx = (fx * fx * (3 - 2 * fx))[None, :]
    wy = (fy * fy * (3 - 2 * fy))[:, None]

    # Hash the lattice nodes, not the pixels. A 10 m raster has roughly 5,000
    # pixels per node, so hashing per pixel does thousands of times the work
    # and allocates several full-size int64 arrays to do it. The node grid is
    # a few hundred across.
    jn = np.arange(int(x0.min()), int(x0.max()) + 2)
    inn = np.arange(int(y0.min()), int(y0.max()) + 2)
    ci, ri = x0 - jn[0], y0 - inn[0]

    out = []
    for seed in seeds:
        nodes = _lattice(seed, jn[None, :], inn[:, None]).astype(np.float32)
        # float32 throughout: half the memory traffic of float64, and the
        # values are test data feeding a raster that will be quantised to
        # int16 anyway.
        field = nodes[np.ix_(ri, ci)] * ((1 - wy) * (1 - wx))
        field += nodes[np.ix_(ri, ci + 1)] * ((1 - wy) * wx)
        field += nodes[np.ix_(ri + 1, ci)] * (wy * (1 - wx))
        field += nodes[np.ix_(ri + 1, ci + 1)] * (wy * wx)
        out.append(field)
    return out


def _smooth_field(bounds, width: int, height: int, seed: int) -> np.ndarray:
    return _smooth_fields(bounds, width, height, (seed,))[0]


@lru_cache(maxsize=64)
def _cloud_threshold(seed: int, fraction: float) -> float:
    """The cloud-field level that masks `fraction` of the surface.

    Measured once per seed against a fixed reference patch rather than against
    the window being generated, so every tile cuts at the same level. The
    field is statistically homogeneous, so a sample anywhere describes it
    everywhere; an individual small window will come out a little above or
    below the nominal fraction, which is also true of real cloud cover.
    """
    reference = _smooth_field((-2.0, 51.0, -1.0, 52.0), 256, 256, seed)
    return float(np.quantile(reference, fraction))


def synthetic_raster(bounds: Tuple[float, float, float, float], width: int,
                     height: int, *, seed: int = 0, kind: str = "continuous",
                     lo: float = 0.0, hi: float = 1.0,
                     nodata: Optional[float] = None,
                     nodata_fraction: float = 0.0):
    """A smoothly varying test raster with optional nodata holes.

    Exists so the whole pipeline — aggregation, COG writing, loading — can be
    exercised with no network and no credentials. Two properties are
    load-bearing and neither is cosmetic:

    **The surface is global and window-independent.** Values come from a
    lattice indexed by absolute coordinates, so the same place gets the same
    value whether it was asked for as part of a whole county or as one tile of
    forty. Without that, a tiled run and an untiled run produce different
    pixels and the merge cannot be checked against anything.

    **Nodata comes in blobs, not salt and pepper.** A real cloud mask is
    contiguous. Scattering independent per-pixel holes produces incompressible
    noise, which is why docs/INGEST-BENCHMARK.md Result 5 found the pipeline's
    own test data overstating storage by 79% — 91 MB against the 51 MB the
    same data costs with realistic gaps. Holes are now a second smooth field
    thresholded, which is both more honest and more like the thing it stands
    in for.
    """
    from rasterio.transform import from_bounds

    if nodata is not None and nodata_fraction > 0:
        field, cloud = _smooth_fields(bounds, width, height,
                                      (seed, seed ^ 0x5EED))
    else:
        field, cloud = _smooth_field(bounds, width, height, seed), None

    if kind == "categorical":
        data = (field * 7).astype(np.int16) * 10 + 10
    else:
        data = (lo + field * (hi - lo)).astype(np.float32)

    if cloud is not None:
        # An independent surface, thresholded to give blobs covering roughly
        # the requested share. The threshold comes from a fixed reference
        # sample, never from a quantile of this window — a per-window quantile
        # masks exactly `nodata_fraction` of *whatever was asked for*, so two
        # tiles of one month would cut their clouds at different levels and
        # stop being views of the same surface.
        data = np.where(cloud < _cloud_threshold(seed ^ 0x5EED, nodata_fraction),
                        nodata, data)

    transform = from_bounds(*bounds, width, height)
    return data, transform
