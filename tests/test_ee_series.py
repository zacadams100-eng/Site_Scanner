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

    # The sharing cache is module-level and would otherwise leak a result from
    # one test into the next, which would hide exactly the bug it exists to
    # create — a stale series for the wrong AOI.
    mod._GROUP_CACHE.clear()

    # Stand in for the Earth Engine round trip, recording what it was asked
    # for so a test can assert months were never sent, and counting calls so a
    # test can assert siblings shared one.
    mod._asked = []
    mod._chunk_calls = []

    def fake_chunk(ee, geom, steps, total_m2):
        mod._asked.extend(steps)
        mod._chunk_calls.append(len(steps))
        return {name: [{"t": s, "value": 0.5, "valid_fraction": 1.0,
                        "interpolated": False} for s in steps]
                for name in mod.S2_FACTORS}

    monkeypatch.setattr(mod, "_s2_chunk", fake_chunk)
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
    ee_series.ndvi_series(GEOM, months(2018, 2025), 100.0)
    assert len(ee_series._chunk_calls) > 1
    assert max(ee_series._chunk_calls) <= ee_series.CHUNK_MONTHS


# ---------------------------------------------------------------------------
# Sharing one Sentinel-2 pass across the index family
# ---------------------------------------------------------------------------
def test_sibling_indices_share_a_single_pass(ee_series):
    """Loading and cloud-masking the scenes is nearly all the cost. Six
    indices off the same imagery must not fetch it six times."""
    steps = months(2018, 2019)
    for factor_id in ("ndvi", "ndmi", "ndbi", "evi", "savi", "nbr"):
        ee_series.REAL_SERIES[factor_id](GEOM, steps, 100.0)

    assert len(ee_series._chunk_calls) == 1, "the imagery was fetched more than once"


def test_a_different_aoi_is_not_served_from_the_cache(ee_series):
    """The failure this cache could cause is the worst kind — plausible
    numbers for the wrong place."""
    other = {"type": "Polygon", "coordinates": [[[9, 51], [9.01, 51],
                                                 [9.01, 51.01], [9, 51.01], [9, 51]]]}
    ee_series.ndvi_series(GEOM, months(2018, 2018), 100.0)
    ee_series.ndvi_series(other, months(2018, 2018), 100.0)
    assert len(ee_series._chunk_calls) == 2


def test_a_different_time_range_is_not_served_from_the_cache(ee_series):
    ee_series.ndvi_series(GEOM, months(2018, 2018), 100.0)
    ee_series.ndvi_series(GEOM, months(2019, 2019), 100.0)
    assert len(ee_series._chunk_calls) == 2


def test_every_sentinel2_index_is_a_real_catalogue_factor(ee_series):
    import catalog

    for factor_id in ee_series.S2_FACTORS:
        f = catalog.FACTOR_BY_ID[factor_id]
        assert f["base"] == "sentinel2_sr", f"{factor_id} is not a Sentinel-2 factor"


def test_modelled_indices_are_left_out_rather_than_approximated(ee_series):
    """Tasselled-cap components need published per-sensor coefficients and
    leaf area index needs a validated canopy model. A plausible-looking
    approximation is worse here than a blank column."""
    for factor_id in ("greenness", "wetness", "brightness", "leaf_area_index"):
        assert factor_id not in ee_series.REAL_SERIES


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


# ---------------------------------------------------------------------------
# Reanalysis and thermal groups
# ---------------------------------------------------------------------------
def rows(**bands):
    """One month of raw band means, as _reduce_months returns them."""
    return [dict(t="2024-07", **bands)]


def test_era5_temperature_becomes_celsius(ee_series):
    out = ee_series._assemble(rows(temperature_2m=290.15,
                                   dewpoint_temperature_2m=285.15,
                                   volumetric_soil_water_layer_1=0.31,
                                   total_evaporation_sum=-0.08),
                              ee_series.ERA5_MONTHLY_FACTORS)
    assert out["air_temp_mean"][0]["value"] == pytest.approx(17.0, abs=1e-6)


def test_soil_moisture_passes_through_unscaled(ee_series):
    out = ee_series._assemble(rows(temperature_2m=290.15,
                                   dewpoint_temperature_2m=285.15,
                                   volumetric_soil_water_layer_1=0.31,
                                   total_evaporation_sum=-0.08),
                              ee_series.ERA5_MONTHLY_FACTORS)
    assert out["soil_moisture"][0]["value"] == pytest.approx(0.31)


def test_evapotranspiration_is_positive_millimetres(ee_series):
    """ERA5 reports evaporation as negative metres, because the water leaves
    the surface. Reported as-is it would be a small negative number in a
    column whose unit is mm."""
    out = ee_series._assemble(rows(temperature_2m=290.15,
                                   dewpoint_temperature_2m=285.15,
                                   volumetric_soil_water_layer_1=0.31,
                                   total_evaporation_sum=-0.08),
                              ee_series.ERA5_MONTHLY_FACTORS)
    assert out["evapotranspiration"][0]["value"] == pytest.approx(80.0)


def test_relative_humidity_is_saturated_when_dewpoint_meets_temperature(ee_series):
    assert ee_series._relative_humidity(290.15, 290.15) == pytest.approx(100.0)


def test_relative_humidity_falls_as_air_dries(ee_series):
    humid = ee_series._relative_humidity(290.15, 289.0)
    dry = ee_series._relative_humidity(290.15, 275.0)
    assert 0.0 < dry < humid < 100.0


def test_diurnal_range_converts_before_differencing(ee_series):
    """The trap. MODIS stores kelvin scaled by 0.02, so differencing the raw
    integers gives a range fifty times too large — 500 °C between day and
    night, which is obviously wrong, or a plausible-looking 12 when the truth
    is 0.24."""
    day_scaled, night_scaled = 15000, 14500     # 300.0 K and 290.0 K
    out = ee_series._assemble(
        rows(LST_Day_1km=day_scaled, LST_Night_1km=night_scaled),
        ee_series.MODIS_FACTORS)

    assert out["lst_day"][0]["value"] == pytest.approx(26.85, abs=1e-6)
    assert out["lst_night"][0]["value"] == pytest.approx(16.85, abs=1e-6)
    assert out["lst_diurnal_range"][0]["value"] == pytest.approx(10.0, abs=1e-6)
    assert out["lst_diurnal_range"][0]["value"] != pytest.approx(
        day_scaled - night_scaled)


def test_a_missing_band_is_a_gap_not_a_zero(ee_series):
    out = ee_series._assemble(rows(LST_Day_1km=None, LST_Night_1km=14500),
                              ee_series.MODIS_FACTORS)
    assert out["lst_day"][0]["value"] is None
    assert out["lst_day"][0]["valid_fraction"] == 0.0
    # A derived factor needing both bands cannot be computed from one.
    assert out["lst_diurnal_range"][0]["value"] is None
    assert out["lst_night"][0]["value"] is not None


def test_full_coverage_groups_are_not_gapped_at_the_sentinel2_boundary(ee_series):
    """Sentinel-2's March 2017 start must not leak into ERA5 or MODIS, which
    run from 1950 and 2000. Applying it there would blank two thirds of the
    table for no reason."""
    import catalog

    for factor_id in list(ee_series.ERA5_MONTHLY_FACTORS) + list(ee_series.MODIS_FACTORS):
        assert catalog.FACTOR_BY_ID[factor_id]["base"] != "sentinel2_sr"
        assert factor_id not in ee_series.S2_FACTORS


def test_reanalysis_siblings_share_one_round_trip(ee_series, monkeypatch):
    calls = []

    def fake_reduce(ee, geom, steps, month_image, bands, scale):
        calls.append(len(steps))
        return [{"t": s, **{b: 290.0 for b in bands}} for s in steps]

    monkeypatch.setattr(ee_series, "_reduce_months", fake_reduce)
    steps = months(2015, 2015)
    for factor_id in ee_series.ERA5_MONTHLY_FACTORS:
        ee_series.REAL_SERIES[factor_id](GEOM, steps, 100.0)
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Coverage windows
# ---------------------------------------------------------------------------
def test_a_source_that_published_nothing_is_not_a_failure(ee_series):
    """The first CI run failed on this: WorldCover released 2020 and 2021
    only, the check ran against 2024, and an honest gap was reported as a
    fault. Empty because the data does not exist is not the same as empty
    because something is broken."""
    y2024 = [f"2024-{m:02d}" for m in range(1, 13)]
    y2020 = [f"2020-{m:02d}" for m in range(1, 13)]

    assert not ee_series.covers("lc_tree_pct", y2024)
    assert ee_series.covers("lc_tree_pct", y2020)


def test_sentinel2_is_not_covered_before_it_launched(ee_series):
    assert not ee_series.covers("ndvi", [f"2013-{m:02d}" for m in range(1, 13)])
    assert ee_series.covers("ndvi", [f"2024-{m:02d}" for m in range(1, 13)])


def test_full_range_sources_cover_the_whole_catalogue(ee_series):
    import catalog

    steps = [f"{y}-{m:02d}" for y in (2011, 2025) for m in range(1, 13)]
    for factor_id in list(ee_series.ERA5_MONTHLY_FACTORS) + list(ee_series.MODIS_FACTORS):
        assert ee_series.covers(factor_id, steps), factor_id
    assert catalog.TIME_START >= "2011-01"


def test_every_real_factor_declares_a_coverage_window(ee_series):
    """A factor missing from the table is silently treated as always covered,
    which reintroduces the failure this table exists to prevent."""
    for factor_id in ee_series.REAL_SERIES:
        assert factor_id in ee_series.FACTOR_COVERAGE, factor_id
