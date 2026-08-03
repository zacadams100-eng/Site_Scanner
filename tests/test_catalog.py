"""Tests for the factor catalogue, series generation and the shared routes.

These assert the contract the frontend is built against. The response shapes
here are what `web/src/types.ts` mirrors, so a change that breaks one should
break the other loudly rather than at runtime in a browser.
"""

import pytest
from fastapi.testclient import TestClient

import catalog
import series as series_mod


GUILDFORD = {
    "type": "Polygon",
    "coordinates": [[
        [-0.58, 51.235], [-0.56, 51.235], [-0.56, 51.245], [-0.58, 51.245], [-0.58, 51.235],
    ]],
}


@pytest.fixture
def client():
    import mock_ee_backend
    return TestClient(mock_ee_backend.app)


# --------------------------------------------------------------------------
# Catalogue
# --------------------------------------------------------------------------
def test_catalogue_has_no_duplicate_factor_ids():
    ids = [f["id"] for f in catalog.FACTORS]
    assert len(ids) == len(set(ids))


def test_every_factor_points_at_a_real_base():
    for f in catalog.FACTORS:
        assert f["base"] in catalog.BASE_BY_ID, f"{f['id']} has an unknown base"


def test_continuous_factors_have_a_usable_range():
    """lo/hi drive colour ramps, axis defaults and the generator, so a missing
    or inverted range is a real bug rather than cosmetic."""
    for f in catalog.FACTORS:
        if f["kind"] != "continuous":
            continue
        assert f["lo"] is not None and f["hi"] is not None, f["id"]
        assert f["hi"] > f["lo"], f["id"]


def test_categorical_factors_declare_their_classes():
    for f in catalog.FACTORS:
        if f["kind"] == "categorical":
            assert f["id"] in catalog.CLASS_VALUES, f["id"]
            assert len(catalog.CLASS_VALUES[f["id"]]) > 1


def test_every_base_carries_provenance():
    """No number renders in the UI without a source and a licence behind it."""
    for b in catalog.BASES:
        assert b["source"] and b["licence"] and b["url"]


def test_catalogue_is_mostly_derived():
    """The whole storage argument rests on this: many factors, few stored
    bases. If this inverts, the cost model in TECHNICAL_PLAN.md 8.2 no
    longer holds."""
    s = catalog.catalogue_summary()
    assert s["factor_count"] > 100
    assert s["stored_base_count"] < 25
    assert s["monthly_base_count"] <= 10
    assert s["derived_factor_count"] > s["factor_count"] / 2


def test_catalog_endpoint_shape(client):
    r = client.get("/api/catalog")
    assert r.status_code == 200
    body = r.json()
    assert {"factors", "bases", "groups", "class_values", "summary",
            "coverage", "time"} <= set(body)
    assert body["coverage"]["name"] == "England"
    assert len(body["time"]["steps"]) == 180        # 15 years, monthly
    assert body["time"]["steps"][0] == "2011-01"
    assert body["time"]["steps"][-1] == "2025-12"


# --------------------------------------------------------------------------
# Series generation
# --------------------------------------------------------------------------
def test_month_steps_spans_inclusive():
    steps = series_mod.month_steps("2020-11", "2021-02")
    assert steps == ["2020-11", "2020-12", "2021-01", "2021-02"]


def test_series_is_deterministic():
    """The same shape must always return the same numbers, or charts flicker
    between reloads."""
    steps = series_mod.month_steps("2020-01", "2020-12")
    a = series_mod.generate_series("ndvi", (-0.57, 51.24), 150.0, steps)
    b = series_mod.generate_series("ndvi", (-0.57, 51.24), 150.0, steps)
    assert a == b


def test_static_factors_do_not_move_over_time():
    steps = series_mod.month_steps("2015-01", "2020-12")
    s = series_mod.generate_series("elevation_mean", (-0.57, 51.24), 150.0, steps)
    values = {p["value"] for p in s["points"]}
    assert len(values) == 1


def test_annual_factors_are_stepped_not_smooth():
    """A yearly product on a monthly axis holds its value and flags the months
    between observations as interpolated."""
    steps = series_mod.month_steps("2018-01", "2018-12")
    s = series_mod.generate_series("lc_tree_pct", (-0.57, 51.24), 150.0, steps)
    assert s["points"][0]["interpolated"] is False
    assert all(p["interpolated"] for p in s["points"][1:])
    assert len({p["value"] for p in s["points"]}) == 1


def test_optical_factors_have_winter_gaps():
    """Decision 10, implemented: cloudy months return null rather than a
    guess. English winters genuinely produce unusable optical data."""
    steps = series_mod.month_steps("2011-01", "2025-12")
    s = series_mod.generate_series("ndvi", (-0.57, 51.24), 150.0, steps)
    gaps = [p for p in s["points"] if p["value"] is None]
    assert gaps, "expected some months to have no usable observation"
    # Gaps must be concentrated in winter, not scattered at random.
    winter = sum(1 for p in gaps if p["t"][5:] in ("11", "12", "01", "02"))
    assert winter / len(gaps) > 0.5


def test_gaps_never_carry_a_value():
    steps = series_mod.month_steps("2011-01", "2025-12")
    s = series_mod.generate_series("ndvi", (-0.57, 51.24), 150.0, steps)
    for p in s["points"]:
        if p["value"] is None:
            assert p["valid_fraction"] < series_mod.GAP_THRESHOLD


def test_modelled_factors_have_no_gaps():
    """Reanalysis and radar are cloud-independent — they should never blank."""
    steps = series_mod.month_steps("2011-01", "2025-12")
    for fid in ("precip_total", "sar_vv", "air_temp_mean"):
        s = series_mod.generate_series(fid, (-0.57, 51.24), 150.0, steps)
        assert all(p["value"] is not None for p in s["points"]), fid


def test_ndvi_peaks_in_summer():
    steps = series_mod.month_steps("2019-01", "2019-12")
    s = series_mod.generate_series("ndvi", (-0.57, 51.24), 150.0, steps)
    by_month = {p["t"][5:]: p["value"] for p in s["points"] if p["value"] is not None}
    assert by_month.get("07") is not None
    assert by_month["07"] > min(v for v in by_month.values())


def test_values_stay_inside_the_declared_range():
    steps = series_mod.month_steps("2011-01", "2025-12")
    for fid in ("ndvi", "precip_total", "lst_day", "avg_sale_price"):
        f = catalog.FACTOR_BY_ID[fid]
        s = series_mod.generate_series(fid, (-0.57, 51.24), 150.0, steps)
        for p in s["points"]:
            if p["value"] is not None:
                assert f["lo"] <= p["value"] <= f["hi"], (fid, p)


def test_unknown_factor_raises():
    with pytest.raises(ValueError):
        series_mod.generate_series("not_a_factor", (-0.57, 51.24), 1.0, ["2020-01"])


# --------------------------------------------------------------------------
# Annual rollup — the attribute table's default view
# --------------------------------------------------------------------------
def test_annual_rollup_is_one_row_per_year():
    steps = series_mod.month_steps("2011-01", "2025-12")
    s = series_mod.generate_series("ndvi", (-0.57, 51.24), 150.0, steps)
    rows = series_mod.annual_rollup(s)
    assert len(rows) == 15
    assert [r["year"] for r in rows] == list(range(2011, 2026))


def test_annual_rollup_reports_observation_count():
    steps = series_mod.month_steps("2011-01", "2025-12")
    s = series_mod.generate_series("ndvi", (-0.57, 51.24), 150.0, steps)
    for r in series_mod.annual_rollup(s):
        assert r["months_total"] == 12
        assert 0 <= r["months_observed"] <= 12


def test_categorical_rollup_uses_mode_not_mean():
    """Averaging a class code is meaningless — the rollup must return one of
    the declared class labels."""
    steps = series_mod.month_steps("2011-01", "2025-12")
    s = series_mod.generate_series("lc_dominant", (-0.57, 51.24), 150.0, steps)
    valid = catalog.CLASS_VALUES["lc_dominant"]
    for r in series_mod.annual_rollup(s):
        assert r["value"] in valid
        assert r["min"] is None and r["max"] is None


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
def test_series_endpoint_returns_monthly_and_annual(client):
    r = client.post("/api/series", json={"geometry": GUILDFORD, "factor_ids": ["ndvi", "precip_total"]})
    assert r.status_code == 200
    body = r.json()
    assert body["precision"] == "approx"
    assert body["area_ha"] > 0
    for fid in ("ndvi", "precip_total"):
        s = body["series"][fid]
        assert len(s["points"]) == 180
        assert len(s["annual"]) == 15
        assert s["meta"]["base_meta"]["licence"]


def test_series_rejects_unknown_factor(client):
    r = client.post("/api/series", json={"geometry": GUILDFORD, "factor_ids": ["ndvi", "bogus"]})
    assert r.status_code == 422
    assert "bogus" in r.json()["detail"]


def test_series_rejects_area_outside_england(client):
    paris = {"type": "Polygon", "coordinates": [[
        [2.5, 48.8], [2.6, 48.8], [2.6, 48.9], [2.5, 48.9], [2.5, 48.8]]]}
    r = client.post("/api/series", json={"geometry": paris, "factor_ids": ["ndvi"]})
    assert r.status_code == 400
    assert "England" in r.json()["detail"]


def test_series_rejects_an_oversized_area(client):
    """Nothing should stop a user drawing over half the country except us."""
    huge = {"type": "Polygon", "coordinates": [[
        [-4.0, 50.5], [1.0, 50.5], [1.0, 54.5], [-4.0, 54.5], [-4.0, 50.5]]]}
    r = client.post("/api/series", json={"geometry": huge, "factor_ids": ["ndvi"]})
    assert r.status_code == 400
    assert "ha" in r.json()["detail"]


def test_series_rejects_an_empty_factor_list(client):
    r = client.post("/api/series", json={"geometry": GUILDFORD, "factor_ids": []})
    assert r.status_code == 422


def test_cells_endpoint_clips_to_the_drawn_shape(client):
    """A freehand outline must not come back as its bounding box."""
    triangle = {"type": "Polygon", "coordinates": [[
        [-0.58, 51.235], [-0.56, 51.235], [-0.57, 51.245], [-0.58, 51.235]]]}
    r = client.post("/api/cells", json={"geometry": triangle, "resolution": 12})
    assert r.status_code == 200
    cells = r.json()["cells"]
    assert cells
    assert len(cells) < 12 * 12 * 0.75      # a triangle is about half its bbox
    for c in cells:
        assert -1.0 <= c["offset"] <= 1.0


def test_cells_are_deterministic(client):
    a = client.post("/api/cells", json={"geometry": GUILDFORD}).json()
    b = client.post("/api/cells", json={"geometry": GUILDFORD}).json()
    assert a == b


def test_both_backends_expose_the_same_new_routes():
    """Parity is the point of routes_catalog.py — assert it rather than trust
    it. app.py cannot be imported without Earth Engine credentials, so the
    router itself is inspected instead."""
    from routes_catalog import router
    paths = {r.path for r in router.routes}
    assert {"/api/catalog", "/api/series", "/api/cells"} <= paths


# --------------------------------------------------------------------------
# /api/stats size guard — the failure the handoff flagged
# --------------------------------------------------------------------------
def test_stats_refuses_a_county_sized_area_with_a_readable_reason(client):
    """reduceRegion at scale=10 over a county exceeds maxPixels or times out,
    and Earth Engine reports that as an opaque failure the user reads as "the
    app is broken". Refusing it with a plain-English reason is both honest and
    cheaper than the quota it saves."""
    huge = {"type": "Polygon", "coordinates": [[
        [-4.0, 50.5], [1.0, 50.5], [1.0, 54.5], [-4.0, 54.5], [-4.0, 50.5]]]}
    r = client.post("/api/stats", json={"year": 2024, "geometry": huge})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "ha" in detail and "smaller" in detail


def test_stats_still_accepts_a_field(client):
    r = client.post("/api/stats", json={"year": 2024, "geometry": GUILDFORD})
    assert r.status_code == 200
    assert "ndvi_mean" in r.json()


def test_stats_malformed_geometry_keeps_its_500(client):
    """The size guard must not reshape any other failure — a malformed body is
    still the 500 both backends have always returned."""
    r = client.post("/api/stats", json={"year": 2024, "geometry": {"type": "Polygon"}})
    assert r.status_code == 500
