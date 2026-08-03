"""
Real Earth Engine time series.

This is the bridge between the working Earth Engine backend and the frontend's
`/api/series` contract. It returns exactly the shape `series.py` generates, so
the app cannot tell the difference except by reading the `source` field — which
is the point: one factor becomes real without touching the frontend.

Scope is deliberately narrow. NDVI only, for now. Land cover is the same
pattern and is stubbed at the bottom with what it needs.

**This module is only imported when Earth Engine is available.** `app.py`
registers it; `mock_ee_backend.py` does not, so the mock keeps working with no
credentials and the test suite stays offline.

### What to expect on timing

A 15-year monthly series is 180 `reduceRegion` calls. Earth Engine evaluates
them server-side in one request per chunk, but it is still real work over real
imagery: expect **tens of seconds**, not milliseconds, and expect it to get
worse with area. That is not a bug to fix here — it is the measurement that
decides whether the product needs the pre-aggregated tier (see BENCHMARK.md,
which measured the alternative at 1–50 ms). Every response carries
`elapsed_ms` so the cost is visible rather than guessed at.
"""

from typing import Any, Callable, Dict, List, Optional

# Sentinel-2 scene classification values that must not contribute to a
# statistic. Defined once and shared with app.py's tile composite so the map
# and the numbers cannot disagree about what counts as cloud.
#   0 no data · 1 saturated/defective · 3 cloud shadow
#   8 cloud medium probability · 9 cloud high probability · 10 thin cirrus
SCL_EXCLUDE = [0, 1, 3, 8, 9, 10]

# Native Sentinel-2 resolution. reduceRegion uses bestEffort, so Earth Engine
# coarsens this itself rather than failing when an area is large.
NDVI_SCALE_M = 10

# Months per Earth Engine request. One call for all 180 risks hitting the
# payload/time limit and losing everything; chunking degrades gracefully and
# makes a partial failure diagnosable.
CHUNK_MONTHS = 36


def _masked_ndvi_collection(geom, start, end):
    """Cloud-masked NDVI images for a window, as an ImageCollection."""
    import ee

    def mask(img):
        scl = img.select("SCL")
        keep = scl.neq(SCL_EXCLUDE[0])
        for v in SCL_EXCLUDE[1:]:
            keep = keep.And(scl.neq(v))
        return img.updateMask(keep)

    return (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(geom)
        .filterDate(start, end)
        .map(mask)
        .map(lambda img: img.normalizedDifference(["B8", "B4"]).rename("NDVI"))
    )


def ndvi_series(geometry: dict, steps: List[str],
                area_ha: float) -> List[Dict[str, Any]]:
    """Monthly mean NDVI over `geometry`, one point per step in `steps`.

    Returns the same point shape `series.generate_series` produces:
        {"t": "2024-07", "value": 0.62, "valid_fraction": 0.83,
         "interpolated": False}

    A month with no usable observation returns `value: None` — never an
    interpolated guess, matching the rule the rest of the system follows.
    """
    import ee

    geom = ee.Geometry(geometry)

    # How many pixels the area *could* contain, so the fraction Earth Engine
    # actually returned is meaningful. This is what drives the confidence
    # shading in the table and the availability strip in the timeline.
    expected_px = max(1.0, (area_ha * 10_000.0) / (NDVI_SCALE_M ** 2))

    points: List[Dict[str, Any]] = []
    for i in range(0, len(steps), CHUNK_MONTHS):
        chunk = steps[i:i + CHUNK_MONTHS]
        points.extend(_ndvi_chunk(ee, geom, chunk, expected_px))
    return points


def _ndvi_chunk(ee, geom, steps: List[str], expected_px: float) -> List[Dict[str, Any]]:
    """One Earth Engine round trip for a run of months."""
    first = ee.Date(steps[0] + "-01")

    def month_feature(i):
        i = ee.Number(i)
        m_start = first.advance(i, "month")
        m_end = m_start.advance(1, "month")
        coll = _masked_ndvi_collection(geom, m_start, m_end)

        # An empty collection has no bands, and reducing it errors server-side
        # rather than returning null. Substituting a fully-masked image keeps
        # the month in the series as an honest gap.
        empty = ee.Image.constant(0).rename("NDVI").updateMask(ee.Image.constant(0))
        ndvi = ee.Image(ee.Algorithms.If(coll.size().gt(0), coll.median(), empty))

        stats = ndvi.reduceRegion(
            reducer=ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True),
            geometry=geom,
            scale=NDVI_SCALE_M,
            maxPixels=1e9,
            # Coarsen rather than fail when the area is large. Without this a
            # big AOI raises instead of returning a slightly coarser number.
            bestEffort=True,
        )
        return ee.Feature(None, {
            "t": m_start.format("YYYY-MM"),
            "mean": stats.get("NDVI_mean"),
            "count": stats.get("NDVI_count"),
            "images": coll.size(),
        })

    fc = ee.FeatureCollection(ee.List.sequence(0, len(steps) - 1).map(month_feature))
    rows = fc.getInfo()["features"]

    out: List[Dict[str, Any]] = []
    for row in rows:
        p = row["properties"]
        mean = p.get("mean")
        count = p.get("count") or 0
        valid = min(1.0, float(count) / expected_px) if expected_px else 0.0

        # No imagery, or every pixel masked, is a gap — not a zero.
        if mean is None or count == 0:
            out.append({"t": p["t"], "value": None,
                        "valid_fraction": round(valid, 3), "interpolated": False})
            continue

        out.append({
            "t": p["t"],
            "value": round(float(mean), 4),
            "valid_fraction": round(valid, 3),
            "interpolated": False,
        })
    return out


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
# factor id -> callable(geometry, steps, area_ha) -> list of points.
#
# Adding land cover means adding one entry here and one function above,
# reducing ESA WorldCover with a frequencyHistogram rather than a mean — the
# same split `catalog.py` already encodes as kind='categorical', and the reason
# it must never be averaged.
REAL_SERIES: Dict[str, Callable[[dict, List[str], float], List[Dict[str, Any]]]] = {
    "ndvi": ndvi_series,
}


def install(registry: Dict[str, Any]) -> None:
    """Register the real implementations into routes_catalog's hook."""
    registry.update(REAL_SERIES)
