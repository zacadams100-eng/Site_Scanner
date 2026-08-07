"""
Environment Agency rainfall, against recorded response shapes.

`environment.data.gov.uk` is not reachable from the environment this was
written in, so every test here substitutes a payload for the HTTP call. That
proves the station selection, the monthly aggregation and the failure
behaviour. It does not prove the endpoint still answers in that shape, which
is what `scripts/check_environment_agency.py` is for.

Fixtures are shaped from the Hydrology API reference. Where a field is a
convention rather than a documented certainty the test says so, because the
difference is what the live check will find.
"""

import pytest

import catalog
import ea_hydrology
from open_data import OpenDataError


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a test tried to make a real HTTP request")
    monkeypatch.setattr(ea_hydrology._SESSION, "get", boom)
    ea_hydrology._LOOKUP.clear()


GUILDFORD = {
    "type": "Polygon",
    "coordinates": [[
        [-0.58, 51.235], [-0.56, 51.235], [-0.56, 51.245], [-0.58, 51.245],
        [-0.58, 51.235],
    ]],
}


def fake_api(monkeypatch, routes):
    def _get(path, params=None):
        for fragment, payload in routes.items():
            if fragment in path:
                return payload(params) if callable(payload) else payload
        raise AssertionError(f"unexpected request to {path}")
    monkeypatch.setattr(ea_hydrology, "_get", _get)


def stations(*rows):
    return {"items": [
        {"notation": n, "label": lbl, "lat": lat, "long": lng}
        for n, lbl, lat, lng in rows
    ]}


def readings(*rows):
    return {"items": [{"date": d, "value": v} for d, v in rows]}


# ---------------------------------------------------------------------------
# Station selection
# ---------------------------------------------------------------------------

def test_picks_the_nearest_gauge_not_the_first_row(monkeypatch):
    # The API's dist filter is a filter, not an ordering. Taking items[0] gets
    # a gauge that is merely within range, which on a 25 km radius can be
    # 25 km away while a 2 km one sits further down the list.
    fake_api(monkeypatch, {"/id/stations": stations(
        ("far", "Farnham", 51.45, -0.80),
        ("near", "Guildford STW", 51.24, -0.57),
        ("mid", "Woking", 51.32, -0.56),
    )})
    s = ea_hydrology.nearest_rainfall_station(GUILDFORD)
    assert s["id"] == "near"
    assert s["distance_km"] < 2


def test_reports_the_distance_so_the_user_can_judge_it(monkeypatch):
    fake_api(monkeypatch, {"/id/stations": stations(
        ("far", "Farnham", 51.45, -0.80),
    )})
    s = ea_hydrology.nearest_rainfall_station(GUILDFORD)
    # ~28 km away. The threshold is generous; the number is what lets someone
    # decide the reading is not about their field.
    assert s["distance_km"] > 20


def test_no_gauge_in_range_raises_rather_than_inventing_one(monkeypatch):
    fake_api(monkeypatch, {"/id/stations": {"items": []}})
    with pytest.raises(OpenDataError, match="no Environment Agency rainfall gauge"):
        ea_hydrology.nearest_rainfall_station(GUILDFORD)


def test_gauges_without_coordinates_are_skipped(monkeypatch):
    fake_api(monkeypatch, {"/id/stations": {"items": [
        {"notation": "broken", "label": "No position"},
        {"notation": "ok", "label": "Guildford", "lat": 51.24, "long": -0.57},
    ]}})
    assert ea_hydrology.nearest_rainfall_station(GUILDFORD)["id"] == "ok"


def test_label_survives_the_api_returning_a_list(monkeypatch):
    # Linked-data endpoints return `label` as a string or a list of strings
    # depending on how many the record carries. Both are normal.
    fake_api(monkeypatch, {"/id/stations": {"items": [
        {"notation": "a", "label": ["Guildford", "Guildford STW"],
         "lat": 51.24, "long": -0.57},
    ]}})
    assert ea_hydrology.nearest_rainfall_station(GUILDFORD)["label"] == "Guildford"


# ---------------------------------------------------------------------------
# Monthly aggregation
# ---------------------------------------------------------------------------

ONE_GAUGE = stations(("g1", "Guildford", 51.24, -0.57))


def january(values):
    return readings(*[(f"2024-01-{d:02d}", v) for d, v in enumerate(values, start=1)])


def test_totals_maxima_and_day_counts_come_from_one_query(monkeypatch):
    calls = []

    def track(path, params=None):
        calls.append(path)
        if "/id/stations" in path:
            return ONE_GAUGE
        return january([0.0, 5.0, 0.4, 12.0] + [0.0] * 27)

    monkeypatch.setattr(ea_hydrology, "_get", track)
    out = ea_hydrology.rainfall_group(GUILDFORD, ["2024-01"], 20.0)

    assert out["ea_rain_total"][0]["value"] == pytest.approx(17.4)
    assert out["ea_rain_max_daily"][0]["value"] == 12.0
    # 5.0 and 12.0 clear 1 mm; 0.4 does not.
    assert out["ea_rain_wet_days"][0]["value"] == 2
    assert out["ea_rain_dry_days"][0]["value"] == 29
    # Four factors, two requests. Fetching per factor would be four times the
    # load on a free public service for identical bytes.
    assert len(calls) == 2


def test_a_dry_month_is_zero_and_not_a_gap(monkeypatch):
    # Zero rainfall is the single most common true value in this series, and
    # reporting it as missing would put a hole in every dry summer.
    fake_api(monkeypatch, {
        "/id/stations": ONE_GAUGE,
        "/data/readings": january([0.0] * 31),
    })
    out = ea_hydrology.rainfall_group(GUILDFORD, ["2024-01"], 20.0)
    assert out["ea_rain_total"][0]["value"] == 0
    assert out["ea_rain_total"][0]["valid_fraction"] == 1.0
    assert out["ea_rain_dry_days"][0]["value"] == 31


def test_a_month_with_no_readings_is_a_gap_not_a_zero(monkeypatch):
    fake_api(monkeypatch, {
        "/id/stations": ONE_GAUGE,
        "/data/readings": {"items": []},
    })
    out = ea_hydrology.rainfall_group(GUILDFORD, ["2024-01"], 20.0)
    for factor in ea_hydrology.FACTOR_IDS:
        assert out[factor][0]["value"] is None, factor


def test_a_part_covered_month_is_labelled_not_scaled_up(monkeypatch):
    # Ten days of a 31-day January is 10/31 confidence, not a January total.
    # Scaling to a full month would invent 21 days of weather.
    fake_api(monkeypatch, {
        "/id/stations": ONE_GAUGE,
        "/data/readings": january([2.0] * 10),
    })
    out = ea_hydrology.rainfall_group(GUILDFORD, ["2024-01"], 20.0)
    point = out["ea_rain_total"][0]
    assert point["value"] == pytest.approx(20.0)
    assert point["valid_fraction"] == pytest.approx(10 / 31, abs=1e-3)


def test_readings_flagged_missing_or_invalid_are_dropped(monkeypatch):
    # A broken gauge reads zero, and zero is also the most common true value —
    # so the quality flag is the only thing that tells them apart.
    fake_api(monkeypatch, {
        "/id/stations": ONE_GAUGE,
        "/data/readings": {"items": [
            {"date": "2024-01-01", "value": 4.0},
            {"date": "2024-01-02", "value": 0.0, "quality": "Missing"},
            {"date": "2024-01-03", "value": 0.0, "quality": "Invalid"},
            {"date": "2024-01-04", "value": 6.0, "quality": "Good"},
        ]},
    })
    out = ea_hydrology.rainfall_group(GUILDFORD, ["2024-01"], 20.0)
    assert out["ea_rain_total"][0]["value"] == pytest.approx(10.0)
    assert out["ea_rain_dry_days"][0]["value"] == 0        # two good days, both wet
    assert out["ea_rain_wet_days"][0]["value"] == 2


def test_february_length_follows_the_leap_year(monkeypatch):
    fake_api(monkeypatch, {
        "/id/stations": ONE_GAUGE,
        "/data/readings": readings(*[(f"2024-02-{d:02d}", 0.0) for d in range(1, 30)]),
    })
    out = ea_hydrology.rainfall_group(GUILDFORD, ["2024-02"], 20.0)
    # 2024 is a leap year: 29 readings is a complete February, not 29/28.
    assert out["ea_rain_total"][0]["valid_fraction"] == 1.0
    assert out["ea_rain_dry_days"][0]["value"] == 29


def test_december_does_not_roll_the_year_over(monkeypatch):
    # _days_in_month builds the first of the next month; December needs the
    # special case or it asks for month 13 and raises.
    fake_api(monkeypatch, {
        "/id/stations": ONE_GAUGE,
        "/data/readings": readings(*[(f"2024-12-{d:02d}", 1.0) for d in range(1, 32)]),
    })
    out = ea_hydrology.rainfall_group(GUILDFORD, ["2024-12"], 20.0)
    assert out["ea_rain_wet_days"][0]["value"] == 31


def test_months_the_gauge_never_reported_stay_gaps(monkeypatch):
    fake_api(monkeypatch, {
        "/id/stations": ONE_GAUGE,
        "/data/readings": january([3.0] * 31),
    })
    out = ea_hydrology.rainfall_group(GUILDFORD, ["2024-01", "2024-02", "2024-03"], 20.0)
    assert out["ea_rain_total"][0]["value"] == pytest.approx(93.0)
    assert out["ea_rain_total"][1]["value"] is None
    assert out["ea_rain_total"][2]["value"] is None


def test_an_upstream_failure_raises_for_the_caller_to_fall_back(monkeypatch):
    # routes_catalog catches this, falls back to the generator and records the
    # failure in the response. Swallowing it here would show demo numbers with
    # a real factor's provenance on them.
    def boom(path, params=None):
        raise OpenDataError("Environment Agency hydrology: 503")
    monkeypatch.setattr(ea_hydrology, "_get", boom)
    with pytest.raises(OpenDataError):
        ea_hydrology.rainfall_group(GUILDFORD, ["2024-01"], 20.0)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_every_factor_id_exists_in_the_catalogue():
    # A registry entry for an id nobody can select is dead code that reads as
    # coverage — check 1 in scripts/audit_catalogue.py.
    for factor_id in ea_hydrology.FACTOR_IDS:
        assert factor_id in catalog.FACTOR_BY_ID


def test_install_registers_all_four_with_provenance():
    registry, provenance = {}, {}
    ea_hydrology.install(registry, provenance)
    for factor_id in ea_hydrology.FACTOR_IDS:
        assert factor_id in registry
        assert provenance[factor_id]["endpoint"] == "environment.data.gov.uk/hydrology"
        assert provenance[factor_id]["source"] == "Environment Agency"


def test_registers_as_written_never_verified():
    # Nothing here has been run against the live service. The distinction is
    # carried into the UI, and only check_environment_agency.py may change it.
    registry, provenance = {}, {}
    ea_hydrology.install(registry, provenance)
    for factor_id in ea_hydrology.FACTOR_IDS:
        assert provenance[factor_id]["status"] == "written"


def test_provenance_says_it_is_a_point_not_an_area():
    registry, provenance = {}, {}
    ea_hydrology.install(registry, provenance)
    note = provenance["ea_rain_total"]["note"]
    assert "point observation" in note
    assert "not an areal" in note


def test_installed_through_open_data_so_every_backend_gets_it():
    # Both backends and the audit call open_data.install. A separate call site
    # is how one of them quietly ends up without this source.
    import open_data
    registry, provenance = {}, {}
    open_data.install(registry, provenance)
    assert "ea_rain_total" in registry


def test_the_base_is_not_the_met_office_grid():
    # Serving gauge readings under haduk_precip's provenance would be exactly
    # the mislabel the catalogue audit exists to catch: a point measurement
    # presented as a 1 km areal average.
    base = catalog.FACTOR_BY_ID["ea_rain_total"]["base"]
    assert base == "ea_hydrology"
    assert catalog.BASE_BY_ID[base]["source"] == "Environment Agency"
    assert catalog.BASE_BY_ID[base]["attribution"]


def test_spi_is_not_registered():
    # A z-score of three-month totals is not SPI: rainfall is right-skewed, so
    # the two disagree most in the dry tail the index exists to measure.
    registry = {}
    ea_hydrology.install(registry, None)
    assert "spi_3month" not in registry
