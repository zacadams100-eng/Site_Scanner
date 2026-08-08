"""JRC Global Surface Water, without Earth Engine.

`ee` is stubbed, as in `test_ee_series.py` — these must pass on a laptop with
no credentials. What is worth pinning is the reasoning around the query, and
one decision in particular: two of these three factors are **static** products
and only one has a genuine annual value.

Spreading a long-baseline statistic across fifteen years as though it were
measured each one would manufacture a trend out of a constant, which is the
exact failure `insights.py` guards against for carried-forward census figures.
So the carried-forward flag is load-bearing, and it is tested.
"""

import sys
import types

import pytest


@pytest.fixture
def gsw(monkeypatch):
    fake = types.ModuleType("ee")
    fake.Geometry = lambda g: g
    monkeypatch.setitem(sys.modules, "ee", fake)

    import ee_series as mod
    mod._GROUP_CACHE.clear()

    # Record which years were asked for, so sharing and range-clipping can be
    # asserted rather than assumed.
    mod._years_asked = []

    def fake_static(ee, geom):
        return {"water_seasonality": 4.5, "water_change": -12.0}

    def fake_extent(ee, geom, year):
        mod._years_asked.append(year)
        return 3.0 + (year - 2015) * 0.5

    monkeypatch.setattr(mod, "_gsw_static", fake_static)
    monkeypatch.setattr(mod, "_gsw_year_extent", fake_extent)
    return mod


GEOM = {"type": "Polygon", "coordinates": [[[0, 51], [0.01, 51],
                                            [0.01, 51.01], [0, 51.01], [0, 51]]]}


def months(start_year, end_year):
    return [f"{y}-{m:02d}"
            for y in range(start_year, end_year + 1)
            for m in range(1, 13)]


# ---------------------------------------------------------------------------
# Static versus annual — the decision this file exists to protect
# ---------------------------------------------------------------------------
def test_seasonality_is_constant_and_says_it_is_carried_forward(gsw):
    out = gsw.gsw_group(GEOM, months(2015, 2019), 200.0)
    pts = out["water_seasonality"]
    assert len({p["value"] for p in pts}) == 1, \
        "seasonality is a 1984-2021 statistic; it has no annual value"
    assert pts[0]["interpolated"] is False
    assert all(p["interpolated"] for p in pts[1:]), \
        "a constant that does not say it is carried forward becomes a trend"


def test_change_is_also_static(gsw):
    pts = gsw.gsw_group(GEOM, months(2015, 2017), 200.0)["water_change"]
    assert len({p["value"] for p in pts}) == 1
    assert pts[0]["value"] == -12.0, "change_norm is legitimately negative"


def test_occurrence_actually_varies_by_year(gsw):
    pts = gsw.gsw_group(GEOM, months(2015, 2019), 200.0)["water_occurrence"]
    januaries = [p["value"] for p in pts if p["t"].endswith("-01")]
    assert len(set(januaries)) == 5, \
        "occurrence comes from YearlyHistory and must differ between years"


def test_occurrence_repeats_within_a_year_and_flags_it(gsw):
    pts = gsw.gsw_group(GEOM, months(2016, 2016), 200.0)
    year = pts["water_occurrence"]
    assert len({p["value"] for p in year}) == 1
    assert year[0]["interpolated"] is False
    assert all(p["interpolated"] for p in year[1:])


# ---------------------------------------------------------------------------
# Coverage — the record ends in 2021
# ---------------------------------------------------------------------------
def test_months_after_the_record_ends_are_gaps(gsw):
    out = gsw.gsw_group(GEOM, months(2020, 2023), 200.0)
    for fid in gsw.GSW_FACTORS:
        after = [p for p in out[fid] if p["t"] >= "2022-01"]
        assert after, "the fixture should span the end of the record"
        assert all(p["value"] is None for p in after), \
            f"{fid} claimed data after 2021"
        assert all(p["valid_fraction"] == 0.0 for p in after)


def test_a_window_entirely_outside_the_record_asks_nothing(gsw):
    out = gsw.gsw_group(GEOM, months(2023, 2025), 200.0)
    assert gsw._years_asked == [], \
        "no round trip should be made for years the product does not cover"
    for fid in gsw.GSW_FACTORS:
        assert all(p["value"] is None for p in out[fid])


def test_coverage_window_is_declared(gsw):
    for fid in gsw.GSW_FACTORS:
        assert gsw.FACTOR_COVERAGE[fid] == (gsw.GSW_START, gsw.GSW_END)
    assert not gsw.covers("water_occurrence", months(2023, 2025))
    assert gsw.covers("water_occurrence", months(2018, 2020))


# ---------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------
def test_the_three_factors_share_one_pass(gsw):
    steps = months(2015, 2017)
    gsw.gsw_group(GEOM, steps, 200.0)
    first = list(gsw._years_asked)
    for fid in gsw.GSW_FACTORS:
        gsw.REAL_SERIES[fid](GEOM, steps, 200.0)
    assert gsw._years_asked == first, \
        "siblings must read the shared result, not re-query"


def test_each_year_is_asked_for_once_not_once_a_month(gsw):
    gsw.gsw_group(GEOM, months(2016, 2018), 200.0)
    assert sorted(gsw._years_asked) == [2016, 2017, 2018]


def test_a_different_aoi_does_not_reuse_the_result(gsw):
    steps = months(2016, 2016)
    gsw.gsw_group(GEOM, steps, 200.0)
    other = {"type": "Polygon", "coordinates": [[[1, 52], [1.01, 52],
                                                 [1.01, 52.01], [1, 52.01], [1, 52]]]}
    gsw._years_asked.clear()
    gsw.gsw_group(other, steps, 200.0)
    assert gsw._years_asked == [2016], "a new AOI must be recomputed"


# ---------------------------------------------------------------------------
# Missing data is a gap, never a zero
# ---------------------------------------------------------------------------
def test_a_year_with_no_classification_is_a_gap_not_dry_land(gsw, monkeypatch):
    """`_gsw_year_extent` returns None when no pixel was observed. Reporting
    0% water would say "this site is dry" on no evidence at all."""
    monkeypatch.setattr(gsw, "_gsw_year_extent", lambda ee, g, y: None)
    gsw._GROUP_CACHE.clear()
    pts = gsw.gsw_group(GEOM, months(2016, 2016), 200.0)["water_occurrence"]
    assert all(p["value"] is None for p in pts)
    assert all(p["valid_fraction"] == 0.0 for p in pts)


def test_an_unreadable_static_band_is_a_gap(gsw, monkeypatch):
    monkeypatch.setattr(gsw, "_gsw_static",
                        lambda ee, g: {"water_seasonality": None,
                                       "water_change": None})
    gsw._GROUP_CACHE.clear()
    out = gsw.gsw_group(GEOM, months(2016, 2016), 200.0)
    assert all(p["value"] is None for p in out["water_seasonality"])
    assert all(p["value"] is None for p in out["water_change"])


# ---------------------------------------------------------------------------
# The registry and the catalogue agree
# ---------------------------------------------------------------------------
def test_the_factors_are_registered_with_provenance(gsw):
    import catalog
    registry, provenance = {}, {}
    gsw.install(registry, provenance)
    for fid in gsw.GSW_FACTORS:
        assert fid in registry
        assert provenance[fid]["endpoint"] == "earthengine.googleapis.com"
        assert provenance[fid]["status"] == "written", \
            "never run against live Earth Engine — must not claim verified"
        assert provenance[fid]["source"] == \
            catalog.BASE_BY_ID[catalog.FACTOR_BY_ID[fid]["base"]]["source"]


def test_values_sit_inside_the_catalogue_range(gsw):
    import catalog
    out = gsw.gsw_group(GEOM, months(2016, 2018), 200.0)
    for fid in gsw.GSW_FACTORS:
        f = catalog.FACTOR_BY_ID[fid]
        for p in out[fid]:
            if p["value"] is None:
                continue
            assert f["lo"] <= p["value"] <= f["hi"], \
                f"{fid} returned {p['value']}, outside {f['lo']}..{f['hi']}"
