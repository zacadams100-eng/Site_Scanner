"""
Tests for the Environment Agency verification script.

The script's whole value is that it refuses to call a broken integration a
success. That judgement is testable even though the network calls it wraps
cannot be made from here — and it has to be, because a checker that passes
everything produces a "verified" label backed by nothing.
"""

import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ea_hydrology                                   # noqa: E402
from open_data import OpenDataError                   # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "check_environment_agency", ROOT / "scripts" / "check_environment_agency.py")
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)


NEAR = {"id": "g1", "label": "Guildford", "lat": 51.24, "lng": -0.57,
        "distance_km": 1.4}


def install(monkeypatch, station, group):
    monkeypatch.setattr(ea_hydrology, "nearest_rainfall_station",
                        lambda g: station)
    monkeypatch.setattr(ea_hydrology, "rainfall_group",
                        lambda g, s, a: group(s))
    # The script's own module-level references, bound at import.
    monkeypatch.setattr(check.ea_hydrology, "nearest_rainfall_station",
                        lambda g: station)
    monkeypatch.setattr(check.ea_hydrology, "rainfall_group",
                        lambda g, s, a: group(s))


def healthy(steps):
    n = len(steps)
    return {
        "ea_rain_total": [{"t": s, "value": 60.0, "valid_fraction": 1.0} for s in steps],
        "ea_rain_max_daily": [{"t": s, "value": 14.0, "valid_fraction": 1.0} for s in steps],
        "ea_rain_wet_days": [{"t": s, "value": 12, "valid_fraction": 1.0} for s in steps],
        "ea_rain_dry_days": [{"t": s, "value": 18, "valid_fraction": 1.0} for s in steps],
    }


def test_a_healthy_response_passes(monkeypatch):
    install(monkeypatch, NEAR, healthy)
    assert check.check(51.23, -0.57, 6)["failures"] == []


def test_an_all_gaps_series_is_a_failure_not_a_pass(monkeypatch):
    # The shape a broken query returns. If this reads as success the script is
    # worthless, because a wrong field name produces exactly this.
    def gaps(steps):
        out = healthy(steps)
        out["ea_rain_total"] = [{"t": s, "value": None, "valid_fraction": 0.0}
                                for s in steps]
        return out
    install(monkeypatch, NEAR, gaps)
    failures = check.check(51.23, -0.57, 6)["failures"]
    assert any("every month is a gap" in f for f in failures)


def test_values_outside_the_catalogue_range_fail(monkeypatch):
    def wrong_unit(steps):
        out = healthy(steps)
        # Inches read as millimetres, or a 15-minute series summed as daily.
        out["ea_rain_max_daily"] = [{"t": s, "value": 900.0, "valid_fraction": 1.0}
                                    for s in steps]
        return out
    install(monkeypatch, NEAR, wrong_unit)
    failures = check.check(51.23, -0.57, 6)["failures"]
    assert any("outside the catalogue" in f for f in failures)


def test_absurd_monthly_rainfall_fails_even_inside_the_declared_range(monkeypatch):
    # ea_rain_total's declared hi is 260 mm, so this is caught twice over —
    # deliberately, because the range check is a catalogue assertion and the
    # plausibility check is a physical one, and they fail for different reasons.
    def flood(steps):
        out = healthy(steps)
        out["ea_rain_total"] = [{"t": s, "value": 4000.0, "valid_fraction": 1.0}
                                for s in steps]
        return out
    install(monkeypatch, NEAR, flood)
    failures = check.check(51.23, -0.57, 6)["failures"]
    assert any("not English weather" in f for f in failures)


def test_wet_plus_dry_exceeding_a_month_fails(monkeypatch):
    # The identity that catches double-counted readings. Neither 20 nor 20 is
    # outside the 0–31 declared range, so nothing else here would notice.
    def doubled(steps):
        out = healthy(steps)
        out["ea_rain_wet_days"] = [{"t": s, "value": 20, "valid_fraction": 1.0} for s in steps]
        out["ea_rain_dry_days"] = [{"t": s, "value": 20, "valid_fraction": 1.0} for s in steps]
        return out
    install(monkeypatch, NEAR, doubled)
    failures = check.check(51.23, -0.57, 6)["failures"]
    assert any("more than a month" in f for f in failures)


def test_a_gauge_outside_the_search_radius_fails(monkeypatch):
    # Means the dist parameter is not being applied, which would silently
    # answer a Surrey site with a reading from another county.
    far = dict(NEAR, distance_km=ea_hydrology.SEARCH_RADIUS_KM + 12)
    install(monkeypatch, far, healthy)
    failures = check.check(51.23, -0.57, 6)["failures"]
    assert any("outside the" in f and "radius" in f for f in failures)


def test_a_missing_factor_is_reported(monkeypatch):
    def incomplete(steps):
        out = healthy(steps)
        del out["ea_rain_wet_days"]
        return out
    install(monkeypatch, NEAR, incomplete)
    failures = check.check(51.23, -0.57, 6)["failures"]
    assert any("ea_rain_wet_days: not returned" in f for f in failures)


def test_months_out_of_order_are_reported(monkeypatch):
    def shuffled(steps):
        out = healthy(steps)
        out["ea_rain_total"] = list(reversed(out["ea_rain_total"]))
        return out
    install(monkeypatch, NEAR, shuffled)
    failures = check.check(51.23, -0.57, 6)["failures"]
    assert any("out of order" in f for f in failures)


def test_a_wrong_point_count_is_reported(monkeypatch):
    def short(steps):
        out = healthy(steps)
        out["ea_rain_total"] = out["ea_rain_total"][:2]
        return out
    install(monkeypatch, NEAR, short)
    failures = check.check(51.23, -0.57, 6)["failures"]
    assert any("points for" in f for f in failures)


def test_an_unreachable_service_fails_rather_than_passing_empty(monkeypatch):
    def boom(g):
        raise OpenDataError("Tunnel connection failed: 403 Forbidden")
    monkeypatch.setattr(check.ea_hydrology, "nearest_rainfall_station", boom)
    result = check.check(51.23, -0.57, 6)
    assert result["failures"]
    assert "station lookup" in result["failures"][0]


def test_recent_steps_excludes_the_current_month():
    # A partly observed month would make every run report one low month and
    # train the reader to ignore the coverage figure.
    import datetime as dt
    steps = check.recent_steps(6)
    assert len(steps) == 6
    assert steps == sorted(steps)
    assert dt.date.today().strftime("%Y-%m") not in steps


def test_recent_steps_crosses_a_year_boundary_correctly():
    steps = check.recent_steps(18)
    assert len(steps) == len(set(steps)) == 18
    for s in steps:
        assert 1 <= int(s[5:7]) <= 12, s
