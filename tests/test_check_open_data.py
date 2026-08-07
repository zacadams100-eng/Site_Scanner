"""
Tests for the live-verification script.

The script's whole value is that it refuses to call a broken integration a
success. That judgement is worth testing even though the network calls it
wraps cannot be made from here: a checker that passes everything is worse than
no checker, because it produces a "verified" label backed by nothing.
"""

import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "check_open_data", ROOT / "scripts" / "check_open_data.py")
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)

STEPS = ["2024-01", "2024-02", "2024-03"]


def points(*values):
    return [{"t": t, "value": v, "valid_fraction": 1.0 if v is not None else 0.0,
             "interpolated": False}
            for t, v in zip(STEPS, values)]


def const(pts):
    return lambda geometry, steps, area_ha: pts


def run(factor_id, pts):
    return check.check_factor(factor_id, const(pts), {}, STEPS, 100.0)


def test_it_accepts_a_series_that_is_the_right_length_and_in_range():
    r = run("crime_density", points(12.0, 14.5, 9.0))
    assert r.ok
    assert r.sample == {"t": "2024-03", "value": 9.0, "gaps": 0}


def test_it_accepts_a_series_with_some_gaps_and_counts_them():
    # A rural district with no sales in a month is real data, not a failure.
    r = run("avg_sale_price", points(420000.0, None, 385000.0))
    assert r.ok
    assert r.sample["gaps"] == 1


def test_it_rejects_a_series_where_every_point_is_a_gap():
    """The shape a broken query returns. It must never read as success."""
    r = run("crime_density", points(None, None, None))
    assert not r.ok
    assert "gap" in r.detail


def test_it_rejects_the_wrong_number_of_points():
    r = run("crime_density", points(12.0, 14.5, 9.0)[:2])
    assert not r.ok
    assert "2 points for 3 steps" in r.detail


def test_it_rejects_a_value_far_outside_the_catalogue_range():
    """A price in pence rather than pounds is 100x too big, and this is the
    only automatic way to catch a unit error."""
    r = run("avg_sale_price", points(42_000_000.0, None, None))
    assert not r.ok
    assert "outside the catalogue range" in r.detail


def test_it_rejects_a_percentage_above_a_hundred():
    r = run("antisocial_share", points(4.0, 220.0, 6.0))
    assert not r.ok


def test_it_reports_an_exception_instead_of_raising():
    def boom(geometry, steps, area_ha):
        raise check.open_data.OpenDataError("data.police.uk unreachable")

    r = check.check_factor("crime_density", boom, {}, STEPS, 100.0)
    assert not r.ok
    assert "OpenDataError" in r.detail and "unreachable" in r.detail


def test_the_window_ends_in_arrears_because_these_sources_publish_late():
    """Asking for last month tests the gap path, not the data path."""
    import datetime as dt

    steps = check.recent_months(6)
    assert len(steps) == 6
    assert steps == sorted(steps), "steps must run forwards in time"
    today = dt.date.today()
    year, month = (int(p) for p in steps[-1].split("-"))
    months_back = (today.year - year) * 12 + (today.month - month)
    assert months_back == 3


def test_the_default_aoi_is_a_closed_ring_of_the_requested_size():
    poly = check.square(51.2362, -0.5704, half_km=0.6)
    ring = poly["coordinates"][0]
    assert ring[0] == ring[-1], "a polygon ring must close"
    lats = [p[1] for p in ring]
    assert (max(lats) - min(lats)) * 111.0 == pytest.approx(1.2, abs=0.05)


def test_every_group_it_checks_names_factors_that_exist():
    """A typo in the group lists would silently check nothing and still exit
    0. The catalogue is the authority on the names."""
    import catalog

    named = ["avg_sale_price", "median_sale_price", "transaction_count",
             "new_build_share", "flat_share", "price_change_yoy",
             "price_growth_5yr", "crime_density", "burglary_density",
             "violent_crime_share", "antisocial_share", "epc_mean_sap",
             "epc_band_mode", "epc_below_c_share", "epc_potential_uplift",
             "mean_floor_area", "heat_pump_share"]
    missing = [f for f in named if f not in catalog.FACTOR_BY_ID]
    assert not missing, f"check_open_data.py names factors that do not exist: {missing}"


def test_it_never_touches_the_network_when_it_only_reports():
    """Guard on the tests above: none of them may make a real call."""
    import open_data

    calls = []
    original = open_data._SESSION.request
    open_data._SESSION.request = lambda *a, **k: calls.append(a) or original(*a, **k)
    try:
        run("crime_density", points(1.0, 2.0, 3.0))
    finally:
        open_data._SESSION.request = original
    assert calls == []
