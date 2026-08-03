"""
Tests for the real Earth Engine series that do not need Earth Engine.

The query itself can only be checked against the live service — that is what
scripts/check_real_ndvi.py is for. What is worth pinning here is the logic
around the query, because it is the part that decides how long a request takes
and whether a gap is honest, and it is pure Python.

`ee` is stubbed rather than installed: these tests must keep passing in CI and
on a laptop with no credentials.
"""

import sys
import types

import pytest


@pytest.fixture
def ee_series(monkeypatch):
    """Import ee_series with a stub `ee`, and no real network anywhere."""
    fake = types.ModuleType("ee")
    fake.Geometry = lambda g: g
    monkeypatch.setitem(sys.modules, "ee", fake)

    import ee_series as mod

    # Stand in for the Earth Engine round trip, recording what it was asked
    # for so a test can assert months were never sent.
    mod._asked = []

    def fake_chunk(ee, geom, steps, total_m2):
        mod._asked.extend(steps)
        return [{"t": s, "value": 0.5, "valid_fraction": 1.0,
                 "interpolated": False} for s in steps]

    monkeypatch.setattr(mod, "_ndvi_chunk", fake_chunk)
    return mod


GEOM = {"type": "Polygon", "coordinates": [[[0, 51], [0.01, 51],
                                            [0.01, 51.01], [0, 51.01], [0, 51]]]}


def months(start_year, end_year):
    return [f"{y}-{m:02d}"
            for y in range(start_year, end_year + 1)
            for m in range(1, 13)]


def test_months_before_sentinel2_are_gaps_without_asking(ee_series):
    """Sentinel-2 L2A starts in 2017-03. Everything earlier is a gap we can
    state directly, and asking Earth Engine about it wastes ~40% of the wait
    on a full-range request."""
    steps = months(2011, 2025)
    points = ee_series.ndvi_series(GEOM, steps, 100.0)

    assert len(points) == len(steps)
    early = [p for p in points if p["t"] < "2017-03"]
    assert len(early) == 74
    assert all(p["value"] is None for p in early)
    assert all(p["valid_fraction"] == 0.0 for p in early)
    assert not any(s < "2017-03" for s in ee_series._asked)


def test_a_pre_coverage_gap_is_never_interpolated(ee_series):
    """The rule the whole system follows: a gap stays a gap."""
    points = ee_series.ndvi_series(GEOM, months(2011, 2012), 100.0)
    assert all(p["value"] is None and p["interpolated"] is False
               for p in points)


def test_order_is_preserved_across_the_coverage_boundary(ee_series):
    """The timeline reads these positionally — reordering would silently
    misdate every point."""
    steps = months(2015, 2019)
    points = ee_series.ndvi_series(GEOM, steps, 100.0)
    assert [p["t"] for p in points] == steps


def test_a_fully_covered_range_asks_for_everything(ee_series):
    steps = months(2018, 2019)
    points = ee_series.ndvi_series(GEOM, steps, 100.0)
    assert ee_series._asked == steps
    assert all(p["value"] is not None for p in points)


def test_requests_are_chunked(ee_series):
    """One call for 180 months risks the payload limit and loses the lot."""
    calls = []
    original = ee_series._ndvi_chunk

    def counting(ee, geom, steps, total_m2):
        calls.append(len(steps))
        return original(ee, geom, steps, total_m2)

    ee_series._ndvi_chunk = counting
    ee_series.ndvi_series(GEOM, months(2018, 2025), 100.0)
    assert len(calls) > 1
    assert max(calls) <= ee_series.CHUNK_MONTHS


def test_ndvi_is_registered_as_a_real_factor(ee_series):
    """routes_catalog swaps generated data for real via this registry, so an
    empty or renamed entry silently leaves the app on demo data."""
    registry = {}
    ee_series.install(registry)
    assert "ndvi" in registry
    assert callable(registry["ndvi"])


# ---------------------------------------------------------------------------
# Registry integrity
# ---------------------------------------------------------------------------
def test_every_real_factor_exists_in_the_catalogue(ee_series):
    """A typo here fails silently — the factor never matches, so the app
    quietly serves demo data for something advertised as live."""
    import catalog

    for factor_id in ee_series.REAL_SERIES:
        assert factor_id in catalog.FACTOR_BY_ID, f"{factor_id} is not a factor"


def test_registered_functions_match_the_declared_cadence(ee_series):
    import catalog

    for factor_id in ee_series.REAL_SERIES:
        f = catalog.FACTOR_BY_ID[factor_id]
        assert f["cadence"] in ("monthly", "annual"), \
            f"{factor_id} has cadence {f['cadence']}, which has no real path"


# ---------------------------------------------------------------------------
# Land cover — the categorical case
# ---------------------------------------------------------------------------
def test_worldcover_labels_are_ones_the_catalogue_declares(ee_series):
    """The frontend colours and filters on these strings. A label the
    catalogue does not list would render as an unknown class."""
    import catalog

    allowed = set(catalog.CLASS_VALUES["lc_dominant"])
    assert set(ee_series.WORLDCOVER_CLASSES.values()) <= allowed


def test_dominant_class_is_the_modal_one_never_an_average(ee_series, monkeypatch):
    """Averaging class codes yields a number that looks fine and means
    nothing: halfway between Grassland (30) and Cropland (40) is Built-up
    (50), which is not what is on the ground."""
    monkeypatch.setattr(ee_series, "_worldcover_histogram",
                        lambda ee, geom, year: {30: 400.0, 40: 600.0})
    points = ee_series.lc_dominant_series(GEOM, ["2020-01"], 100.0)
    assert points[0]["value"] == "Cropland"
    assert points[0]["value"] != "Built-up"


def test_classes_outside_england_are_ignored_not_guessed(ee_series, monkeypatch):
    """Snow/ice, mangroves and moss have no catalogue label. They must not
    win the vote and must not invent a class."""
    monkeypatch.setattr(ee_series, "_worldcover_histogram",
                        lambda ee, geom, year: {70: 9999.0, 30: 5.0})
    assert ee_series.lc_dominant_series(GEOM, ["2020-01"], 100.0)[0]["value"] == "Grassland"


def test_a_year_with_no_worldcover_map_is_a_gap(ee_series, monkeypatch):
    """Only 2020 and 2021 exist. Inventing 2013 land cover would be worse
    than leaving it blank."""
    monkeypatch.setattr(ee_series, "_worldcover_histogram",
                        lambda ee, geom, year: None)
    p = ee_series.lc_dominant_series(GEOM, ["2013-01"], 100.0)[0]
    assert p["value"] is None
    assert p["valid_fraction"] == 0.0
    assert p["interpolated"] is False


def test_tree_percentage_is_a_share_of_the_whole_aoi(ee_series, monkeypatch):
    monkeypatch.setattr(ee_series, "_worldcover_histogram",
                        lambda ee, geom, year: {10: 250.0, 30: 750.0})
    assert ee_series.lc_tree_pct_series(GEOM, ["2020-01"], 100.0)[0]["value"] == 25.0


# ---------------------------------------------------------------------------
# Annual values spread over monthly steps
# ---------------------------------------------------------------------------
def test_january_carries_the_observation_and_the_rest_repeat_it(ee_series, monkeypatch):
    """series.py's contract for annual factors, matched here so the frontend
    cannot tell a real annual factor from a generated one."""
    monkeypatch.setattr(ee_series, "_worldcover_histogram",
                        lambda ee, geom, year: {10: 1000.0})
    steps = [f"2020-{m:02d}" for m in range(1, 13)]
    points = ee_series.lc_dominant_series(GEOM, steps, 100.0)

    assert all(p["value"] == "Tree cover" for p in points)
    assert points[0]["interpolated"] is False
    assert all(p["interpolated"] is True for p in points[1:])


def test_the_map_is_fetched_once_per_year_not_once_per_month(ee_series, monkeypatch):
    """Twelve identical reduceRegion calls for one annual value would make a
    15-year request 180 round trips instead of 15."""
    calls = []

    def counting(ee, geom, year):
        calls.append(year)
        return {10: 1000.0}

    monkeypatch.setattr(ee_series, "_worldcover_histogram", counting)
    steps = [f"{y}-{m:02d}" for y in (2020, 2021) for m in range(1, 13)]
    ee_series.lc_dominant_series(GEOM, steps, 100.0)
    assert calls == [2020, 2021]


def test_kelvin_conversion_is_the_right_way_round(ee_series):
    """A sign error here gives -270 °C for an English summer, which is
    obviously wrong, or 546, which is not obviously anything."""
    assert round(300.0 - ee_series.KELVIN, 2) == 26.85
