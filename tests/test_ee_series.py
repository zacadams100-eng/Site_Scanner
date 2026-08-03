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
