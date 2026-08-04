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
    """Every factor, not a sample of four.

    lo/hi drive the colour ramp and the axis, so a generator that overshoots
    paints a cell off the end of the ramp and draws a chart nobody can read.
    With 260-odd factors this is the only way to know the whole catalogue is
    renderable."""
    steps = series_mod.month_steps("2011-01", "2025-12")
    for f in catalog.FACTORS:
        s = series_mod.generate_series(f["id"], (-0.57, 51.24), 150.0, steps)
        for p in s["points"]:
            v = p["value"]
            if v is None or isinstance(v, str):
                continue
            assert f["lo"] <= v <= f["hi"], (f["id"], v, f["lo"], f["hi"])


def test_every_group_has_a_generator_character():
    """A group the generator has never heard of falls back to the middle of
    its range and sits there, which reads as broken data rather than as a
    site. Every group must be tied to some site characteristic."""
    import series as sm
    site = {"urbanity": 0.9, "northness": 0.2, "wetness": 0.3,
            "elevation": 0.4, "affluence": 0.8}
    rural = {"urbanity": 0.05, "northness": 0.8, "wetness": 0.7,
             "elevation": 0.6, "affluence": 0.2}
    for group in catalog.GROUPS:
        a = sm._coherent_position("x", group, site)
        b = sm._coherent_position("x", group, rural)
        assert a != b, f"{group} does not respond to the site at all"


def test_the_catalogue_serves_more_than_one_profession():
    """The point of the second half: a developer, an insurer, a grid engineer
    and a farm agent should each find their own screen in here."""
    groups = set(catalog.GROUPS)
    for expected in ("Planning & consents", "Property market", "Ground risk",
                     "Infrastructure", "Agriculture", "Energy"):
        assert expected in groups
    assert catalog.catalogue_summary()["factor_count"] > 240


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


# --------------------------------------------------------------------------
# Real-data registry — the seam between generated and Earth Engine
# --------------------------------------------------------------------------
@pytest.fixture
def registry():
    """Gives a clean REAL_SERIES and always restores it, so one test cannot
    leave real data wired into another.

    The series cache is cleared with it: two tests registering different
    implementations for the same factor and geometry would otherwise collide,
    the second one silently reading the first one's answer.
    """
    import routes_catalog
    routes_catalog.REAL_SERIES.clear()
    routes_catalog.SERIES_CACHE.clear()
    yield routes_catalog.REAL_SERIES
    routes_catalog.REAL_SERIES.clear()
    routes_catalog.SERIES_CACHE.clear()


SHORT = {"start": "2024-01", "end": "2024-06"}


def _stub(geometry, steps, area_ha):
    return [{"t": s, "value": 0.5, "valid_fraction": 0.9, "interpolated": False}
            for s in steps]


def test_unregistered_factors_are_labelled_generated(client, registry):
    r = client.post("/api/series", json={"geometry": GUILDFORD,
                                         "factor_ids": ["ndvi"], **SHORT})
    body = r.json()
    assert body["series"]["ndvi"]["source"] == "generated"
    assert body["real_factors"] == []


def test_a_registered_factor_returns_real_data_and_says_so(client, registry):
    registry["ndvi"] = _stub
    body = client.post("/api/series", json={"geometry": GUILDFORD,
                                            "factor_ids": ["ndvi", "precip_total"],
                                            **SHORT}).json()
    assert body["series"]["ndvi"]["source"] == "earth-engine"
    assert body["series"]["precip_total"]["source"] == "generated"
    assert body["real_factors"] == ["ndvi"]


def test_real_series_still_gets_the_annual_rollup_and_meta(client, registry):
    """A real factor has to be indistinguishable to the frontend apart from its
    label — same rollup, same provenance, same point shape."""
    registry["ndvi"] = _stub
    s = client.post("/api/series", json={"geometry": GUILDFORD,
                                         "factor_ids": ["ndvi"], **SHORT}).json()["series"]["ndvi"]
    assert len(s["points"]) == 6
    assert s["annual"] and s["annual"][0]["year"] == 2024
    assert s["meta"]["base_meta"]["licence"]
    assert s["kind"] == "continuous" and s["unit"] == "index"
    assert "elapsed_ms" in s


def test_a_failing_real_source_falls_back_rather_than_breaking_the_report(client, registry):
    """One flaky Earth Engine call must not blank a report with eleven other
    factors in it — and the substitution must be visible, not silent."""
    def boom(geometry, steps, area_ha):
        raise RuntimeError("EE quota exceeded")

    registry["ndvi"] = boom
    r = client.post("/api/series", json={"geometry": GUILDFORD,
                                         "factor_ids": ["ndvi", "precip_total"], **SHORT})
    assert r.status_code == 200
    ndvi = r.json()["series"]["ndvi"]
    assert ndvi["source"] == "generated"
    assert "quota" in ndvi["error"]
    assert ndvi["points"], "fallback must still return a usable series"
    assert r.json()["real_factors"] == []


def test_the_real_source_receives_the_drawn_geometry(client, registry):
    """The generator only needs a centroid; a real reduceRegion needs the shape
    itself, so the geometry has to reach the hook intact."""
    seen = {}

    def capture(geometry, steps, area_ha):
        seen["geometry"] = geometry
        seen["area_ha"] = area_ha
        return _stub(geometry, steps, area_ha)

    registry["ndvi"] = capture
    client.post("/api/series", json={"geometry": GUILDFORD,
                                     "factor_ids": ["ndvi"], **SHORT})
    assert seen["geometry"] == GUILDFORD
    assert seen["area_ha"] > 0


def test_the_catalogue_says_which_factors_are_real(client, registry):
    """A user picking factors should see which return observations *before*
    spending a query, not afterwards from a badge on the result."""
    registry["ndvi"] = _stub
    body = client.get("/api/catalog").json()
    by_id = {f["id"]: f for f in body["factors"]}
    assert by_id["ndvi"]["real"] is True
    assert by_id["precip_total"]["real"] is False
    assert body["real_factor_ids"] == ["ndvi"]
    assert body["summary"]["real_factor_count"] == 1


def test_the_catalogue_marks_nothing_real_with_no_registry(client, registry):
    body = client.get("/api/catalog").json()
    assert body["real_factor_ids"] == []
    assert all(f["real"] is False for f in body["factors"])


# ---------------------------------------------------------------------------
# Series cache — the difference between one Earth Engine call and eleven
# ---------------------------------------------------------------------------
def test_a_repeated_factor_is_served_from_cache(client, registry):
    """Adding a factor to a report must not re-run the factors already in it.
    That is eleven Earth Engine calls per toggle otherwise."""
    calls = {"n": 0}

    def counted(geometry, steps, area_ha):
        calls["n"] += 1
        return _stub(geometry, steps, area_ha)

    registry["ndvi"] = counted
    first = client.post("/api/series", json={"geometry": GUILDFORD,
                                             "factor_ids": ["ndvi"], **SHORT}).json()
    second = client.post("/api/series", json={"geometry": GUILDFORD,
                                              "factor_ids": ["ndvi", "precip_total"],
                                              **SHORT}).json()
    assert calls["n"] == 1
    assert first["series"]["ndvi"]["cached"] is False
    assert second["series"]["ndvi"]["cached"] is True
    assert second["series"]["ndvi"]["points"] == first["series"]["ndvi"]["points"]
    assert second["series"]["ndvi"]["source"] == "earth-engine"


def test_a_different_shape_is_not_a_cache_hit(client, registry):
    calls = {"n": 0}

    def counted(geometry, steps, area_ha):
        calls["n"] += 1
        return _stub(geometry, steps, area_ha)

    registry["ndvi"] = counted
    elsewhere = {"type": "Polygon", "coordinates": [[
        [-1.58, 52.235], [-1.56, 52.235], [-1.56, 52.245], [-1.58, 52.245], [-1.58, 52.235],
    ]]}
    client.post("/api/series", json={"geometry": GUILDFORD, "factor_ids": ["ndvi"], **SHORT})
    client.post("/api/series", json={"geometry": elsewhere, "factor_ids": ["ndvi"], **SHORT})
    assert calls["n"] == 2


def test_a_different_time_range_is_not_a_cache_hit(client, registry):
    calls = {"n": 0}

    def counted(geometry, steps, area_ha):
        calls["n"] += 1
        return _stub(geometry, steps, area_ha)

    registry["ndvi"] = counted
    client.post("/api/series", json={"geometry": GUILDFORD, "factor_ids": ["ndvi"], **SHORT})
    client.post("/api/series", json={"geometry": GUILDFORD, "factor_ids": ["ndvi"],
                                     "start": "2024-01", "end": "2024-09"})
    assert calls["n"] == 2


def test_a_failure_is_never_cached(client, registry):
    """A flaky call should be retried next request, not remembered for fifteen
    minutes — otherwise one blip freezes demo data onto a real factor."""
    state = {"fail": True, "n": 0}

    def flaky(geometry, steps, area_ha):
        state["n"] += 1
        if state["fail"]:
            raise RuntimeError("EE quota exceeded")
        return _stub(geometry, steps, area_ha)

    registry["ndvi"] = flaky
    first = client.post("/api/series", json={"geometry": GUILDFORD,
                                             "factor_ids": ["ndvi"], **SHORT}).json()
    assert first["series"]["ndvi"]["source"] == "generated"

    state["fail"] = False
    second = client.post("/api/series", json={"geometry": GUILDFORD,
                                              "factor_ids": ["ndvi"], **SHORT}).json()
    assert state["n"] == 2
    assert second["series"]["ndvi"]["source"] == "earth-engine"


def test_a_cache_hit_does_not_inherit_the_previous_response_decorations(client, registry):
    """The route decorates each series with `annual` and `meta`. If the cached
    dict were handed back by reference those would accumulate on it."""
    import routes_catalog
    registry["ndvi"] = _stub
    client.post("/api/series", json={"geometry": GUILDFORD, "factor_ids": ["ndvi"], **SHORT})
    key = list(routes_catalog.SERIES_CACHE._data)[0]
    cached, _ = routes_catalog.SERIES_CACHE._data[key]
    assert "annual" not in cached and "meta" not in cached


def test_the_series_cache_reports_its_counters(client, registry):
    registry["ndvi"] = _stub
    client.post("/api/series", json={"geometry": GUILDFORD, "factor_ids": ["ndvi"], **SHORT})
    client.post("/api/series", json={"geometry": GUILDFORD, "factor_ids": ["ndvi"], **SHORT})
    info = client.get("/api/cache/series").json()
    assert info["hits"] >= 1 and info["misses"] >= 1
    assert info["entries"] >= 1


def test_generated_factors_are_not_cached(client, registry):
    """The generator is microseconds; caching it would only hold memory."""
    import routes_catalog
    routes_catalog.SERIES_CACHE.clear()
    client.post("/api/series", json={"geometry": GUILDFORD,
                                     "factor_ids": ["precip_total"], **SHORT})
    assert len(routes_catalog.SERIES_CACHE) == 0


# ---------------------------------------------------------------------------
# Attribution — a licence condition, not a nicety
# ---------------------------------------------------------------------------
def test_every_base_carries_the_notice_its_licence_requires():
    """Almost every source here permits commercial use *on condition* that a
    specific wording is displayed. Naming the licence is not the same as
    meeting it, and a missing notice is a breach on a product being sold."""
    for base in catalog.BASES:
        assert base.get("attribution"), f"{base['id']} has no attribution"
        assert len(base["attribution"]) > 15, f"{base['id']} attribution is a stub"


def test_crown_copyright_sources_say_so():
    """OGL requires the Crown copyright line, not just 'OGL v3'."""
    for base in catalog.BASES:
        if base["licence"] == "OGL v3":
            text = base["attribution"].lower()
            assert "crown copyright" in text or "open government licence" in text, \
                f"{base['id']} is OGL but its notice omits the required wording"


def test_copernicus_sources_use_the_modified_data_wording():
    for bid in ("sentinel2_sr", "sentinel1_sar", "era5_land", "copernicus_air"):
        assert "modified copernicus" in catalog.BASE_BY_ID[bid]["attribution"].lower()


def test_attributions_are_deduplicated_for_display():
    """Several factors usually share one source; repeating the notice four
    times is noise that gets designed away, taking the notice with it."""
    lines = catalog.attributions_for(["sentinel2_sr", "sentinel1_sar", "os_open"])
    assert len(lines) == 2


def test_commercial_flags_are_triaged_not_assumed():
    """Sentinel is recorded as CC BY-SA, which would bite on a commercial
    derived product. It must stay flagged until someone confirms it."""
    assert catalog.COMMERCIAL_USE["sentinel2_sr"] == "verify"
    assert set(catalog.COMMERCIAL_USE.values()) <= {"yes", "verify"}


# ---------------------------------------------------------------------------
# The bundled basemap — a build artefact, so it can rot silently
# ---------------------------------------------------------------------------
def test_the_bundled_basemap_is_present_and_complete():
    """The map's only cartography used to be a third-party raster, and when it
    failed the canvas was an empty rectangle. This file is the fix, so its
    absence should break a test rather than a user's first impression."""
    import json
    import pathlib

    path = pathlib.Path(__file__).resolve().parent.parent / "web" / "public" / "basemap" / "england.json"
    assert path.exists(), "run scripts/build_basemap.py"

    data = json.loads(path.read_text())
    for layer in ("land", "urban", "lakes", "rivers", "roads", "rail", "places"):
        assert data[layer]["features"], f"{layer} is empty"

    # It ships to every visitor, so its size is a product decision.
    assert path.stat().st_size < 1_200_000, "basemap has grown past its budget"

    # England has to be in it, and the labels have to be named.
    names = {f["properties"]["name"] for f in data["places"]["features"]}
    assert {"London", "Manchester", "Bristol"} <= names
    assert data["attribution"]
