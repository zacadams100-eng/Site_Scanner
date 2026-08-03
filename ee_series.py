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

# Sentinel-2 Level-2A surface reflectance begins in March 2017. The catalogue
# runs from 2011, so 74 of the 180 months an unfiltered request covers predate
# the satellite entirely.
#
# Those months are gaps either way — the rule is never to interpolate — but
# asking Earth Engine about them costs a round trip to be told nothing, which
# is roughly 40% of the wait on a full-range request. They are answered
# directly instead.
COVERAGE_START = "2017-03"


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

    # The area the AOI *could* cover, so the fraction actually observed is
    # meaningful. This drives the confidence shading in the table and the
    # availability strip in the timeline, so it has to be true square metres —
    # see the note on pixelArea in _ndvi_chunk for why counting pixels is not.
    total_m2 = max(1.0, area_ha * 10_000.0)

    # Months before the satellite existed are gaps we can state without asking.
    before = [s for s in steps if s < COVERAGE_START]
    covered = [s for s in steps if s >= COVERAGE_START]

    points: List[Dict[str, Any]] = [
        {"t": s, "value": None, "valid_fraction": 0.0, "interpolated": False}
        for s in before
    ]
    for i in range(0, len(covered), CHUNK_MONTHS):
        chunk = covered[i:i + CHUNK_MONTHS]
        points.extend(_ndvi_chunk(ee, geom, chunk, total_m2))
    return points


def _ndvi_chunk(ee, geom, steps: List[str], total_m2: float) -> List[Dict[str, Any]]:
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
            reducer=ee.Reducer.mean(),
            geometry=geom,
            scale=NDVI_SCALE_M,
            maxPixels=1e9,
            # Coarsen rather than fail when the area is large. Without this a
            # big AOI raises instead of returning a slightly coarser number.
            bestEffort=True,
        )

        # Coverage has to be measured as area, not as a pixel count.
        #
        # reduceRegion works in the image's projection, and a composite built
        # through ee.Algorithms.If has no native projection, so Earth Engine
        # falls back to EPSG:4326. There a "10 m" pixel is 10 m tall but
        # 10/cos(latitude) m wide, which over England inflates the count by
        # about 1.6x — measured at 1.617 near Guildford and 1.658 in the fens,
        # against 1.597 and 1.645 predicted. Every month therefore reported
        # more pixels than the AOI can hold and clamped to 100% coverage,
        # including cloudy midwinter ones.
        #
        # pixelArea() returns true square metres whatever the projection, so
        # summing it over the unmasked pixels gives a fraction that means what
        # it says.
        valid_area = (
            ee.Image.pixelArea().updateMask(ndvi.mask()).reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=geom,
                scale=NDVI_SCALE_M,
                maxPixels=1e9,
                bestEffort=True,
            )
        )

        return ee.Feature(None, {
            "t": m_start.format("YYYY-MM"),
            "mean": stats.get("NDVI"),
            "valid_m2": valid_area.get("area"),
            "images": coll.size(),
        })

    fc = ee.FeatureCollection(ee.List.sequence(0, len(steps) - 1).map(month_feature))
    rows = fc.getInfo()["features"]

    out: List[Dict[str, Any]] = []
    for row in rows:
        p = row["properties"]
        mean = p.get("mean")
        valid_m2 = p.get("valid_m2") or 0.0
        valid = min(1.0, float(valid_m2) / total_m2) if total_m2 else 0.0

        # No imagery, or every pixel masked, is a gap — not a zero.
        if mean is None or valid_m2 <= 0:
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
# ERA5-Land air temperature
# ---------------------------------------------------------------------------
# Already aggregated to months upstream, and running since 1950, so unlike
# NDVI this fills the whole 2011-2025 table rather than starting part way in.
ERA5_COLLECTION = "ECMWF/ERA5_LAND/MONTHLY_AGGR"
ERA5_BAND = "temperature_2m"
KELVIN = 273.15

# ERA5-Land is roughly 11 km, far coarser than any AOI someone will draw here,
# so "mean over the AOI" is really "the value of the grid cell containing it".
# Reducing at 100 m makes that explicit and, more practically, guarantees
# sample points land inside a small AOI — at native scale a 24 ha field can
# contain no pixel centre at all and come back empty.
ERA5_SCALE_M = 100


def air_temp_series(geometry: dict, steps: List[str],
                    area_ha: float) -> List[Dict[str, Any]]:
    """Monthly mean 2 m air temperature in °C, one point per step."""
    import ee

    geom = ee.Geometry(geometry)
    points: List[Dict[str, Any]] = []
    for i in range(0, len(steps), CHUNK_MONTHS):
        points.extend(_era5_chunk(ee, geom, steps[i:i + CHUNK_MONTHS]))
    return points


def _era5_chunk(ee, geom, steps: List[str]) -> List[Dict[str, Any]]:
    first = ee.Date(steps[0] + "-01")

    def month_feature(i):
        i = ee.Number(i)
        m_start = first.advance(i, "month")
        coll = (ee.ImageCollection(ERA5_COLLECTION)
                .select(ERA5_BAND)
                .filterDate(m_start, m_start.advance(1, "month")))

        blank = (ee.Image.constant(0).rename(ERA5_BAND)
                 .updateMask(ee.Image.constant(0)))
        img = ee.Image(ee.Algorithms.If(coll.size().gt(0), coll.first(), blank))

        stats = img.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=geom,
            scale=ERA5_SCALE_M, maxPixels=1e9, bestEffort=True)

        return ee.Feature(None, {
            "t": m_start.format("YYYY-MM"),
            "kelvin": stats.get(ERA5_BAND),
        })

    fc = ee.FeatureCollection(ee.List.sequence(0, len(steps) - 1).map(month_feature))
    rows = fc.getInfo()["features"]

    out: List[Dict[str, Any]] = []
    for row in rows:
        p = row["properties"]
        k = p.get("kelvin")
        if k is None:
            out.append({"t": p["t"], "value": None,
                        "valid_fraction": 0.0, "interpolated": False})
            continue
        # Reanalysis has no clouds and no gaps: a month either exists in full
        # or does not exist at all, so coverage is 1.0 rather than a fraction
        # of observed pixels.
        out.append({"t": p["t"], "value": round(float(k) - KELVIN, 3),
                    "valid_fraction": 1.0, "interpolated": False})
    return out


# ---------------------------------------------------------------------------
# ESA WorldCover land cover
# ---------------------------------------------------------------------------
# Two annual snapshots exist and no more, so most of the catalogue's range is
# an honest gap. Stating that plainly is the point — a land cover value
# invented for 2013 would be worse than no value at all.
WORLDCOVER_YEARS = {2020: "ESA/WorldCover/v100", 2021: "ESA/WorldCover/v200"}
WORLDCOVER_BAND = "Map"

# WorldCover class codes to the labels catalog.CLASS_VALUES already declares.
# 70 snow/ice, 95 mangroves and 100 moss/lichen are omitted deliberately: they
# do not occur in England, and inventing labels the catalogue does not list
# would break the categorical contract at the other end.
WORLDCOVER_CLASSES = {
    10: "Tree cover", 20: "Shrubland", 30: "Grassland", 40: "Cropland",
    50: "Built-up", 60: "Bare / sparse", 80: "Open water",
    90: "Herbaceous wetland",
}


def _worldcover_histogram(ee, geom, year: int) -> Optional[Dict[int, float]]:
    """Pixel counts per class for one year, or None if that year has no map."""
    dataset = WORLDCOVER_YEARS.get(year)
    if dataset is None:
        return None

    img = ee.ImageCollection(dataset).first().select(WORLDCOVER_BAND)
    hist = img.reduceRegion(
        reducer=ee.Reducer.frequencyHistogram(),
        geometry=geom, scale=10, maxPixels=1e9, bestEffort=True,
    ).getInfo()

    raw = (hist or {}).get(WORLDCOVER_BAND) or {}
    # Keys arrive as strings, and as floats ("10.0") depending on the path.
    return {int(float(k)): float(v) for k, v in raw.items()} if raw else None


def _annual_points(steps: List[str], value_for_year) -> List[Dict[str, Any]]:
    """Spread an annual value across monthly steps.

    January carries the observation; the rest of the year repeats it flagged
    `interpolated`, which is the same contract series.py uses for annual
    factors, so the frontend does not need to know this one is real.
    """
    out: List[Dict[str, Any]] = []
    cache: Dict[int, Any] = {}
    for step in steps:
        year = int(step[:4])
        if year not in cache:
            cache[year] = value_for_year(year)
        value = cache[year]
        out.append({
            "t": step,
            "value": value,
            "valid_fraction": 1.0 if value is not None else 0.0,
            "interpolated": value is not None and not step.endswith("-01"),
        })
    return out


def lc_dominant_series(geometry: dict, steps: List[str],
                       area_ha: float) -> List[Dict[str, Any]]:
    """Most common land cover class by area, per year.

    Categorical: reduced with a frequencyHistogram and resolved to the modal
    class. Averaging class codes would produce a number that looks fine and
    means nothing — halfway between Grassland (30) and Cropland (40) is not
    Built-up (50), and TECHNICAL_PLAN.md §8.5 makes this the rule.
    """
    import ee

    geom = ee.Geometry(geometry)

    def value_for_year(year: int) -> Optional[str]:
        counts = _worldcover_histogram(ee, geom, year)
        if not counts:
            return None
        known = {c: n for c, n in counts.items() if c in WORLDCOVER_CLASSES}
        if not known:
            return None
        return WORLDCOVER_CLASSES[max(known, key=known.get)]

    return _annual_points(steps, value_for_year)


def lc_tree_pct_series(geometry: dict, steps: List[str],
                       area_ha: float) -> List[Dict[str, Any]]:
    """Share of the AOI classed as tree cover, per year, as a percentage."""
    import ee

    geom = ee.Geometry(geometry)

    def value_for_year(year: int) -> Optional[float]:
        counts = _worldcover_histogram(ee, geom, year)
        if not counts:
            return None
        total = sum(counts.values())
        if total <= 0:
            return None
        return round(100.0 * counts.get(10, 0.0) / total, 2)

    return _annual_points(steps, value_for_year)


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
    "air_temp_mean": air_temp_series,
    "lc_dominant": lc_dominant_series,
    "lc_tree_pct": lc_tree_pct_series,
}


def install(registry: Dict[str, Any]) -> None:
    """Register the real implementations into routes_catalog's hook."""
    registry.update(REAL_SERIES)
