"""
mock_ee_backend.py — the contract it promises to keep with app.py.

The mock is only useful if its responses are indistinguishable from the real
backend's, so most of these assert parity rather than behaviour.
"""

import math

import pytest

import mock_ee_backend
from mock_ee_backend import (
    WORLDCOVER_CODES,
    geometry_area_m2,
    make_landcover_histogram,
    make_stats,
)

CODE_STRINGS = {str(c) for c in WORLDCOVER_CODES}


# ---------------------------------------------------------------------------
# Parity with app.py
# ---------------------------------------------------------------------------
def test_request_models_match_app(ee_env):
    """A body accepted by one backend must be accepted by the other."""
    import app

    for name in ("TileRequest", "StatsRequest", "PriceRequest"):
        real = getattr(app, name).model_fields
        mock = getattr(mock_ee_backend, name).model_fields
        assert set(real) == set(mock), f"{name} fields drifted"
        for field, info in real.items():
            assert info.annotation == mock[field].annotation, f"{name}.{field} type drifted"
            assert info.is_required() == mock[field].is_required(), f"{name}.{field} optionality drifted"


FRONTEND_ROUTES = {
    "/", "/api/stats", "/api/stats/price", "/api/summary",
    "/api/tile/ndvi", "/api/tile/landcover",
}


def test_routes_match_app(ee_env):
    """Every route the frontend calls must exist on both, with the same
    methods — swapping backends is meant to be a one-word change."""
    import app

    def routes(a):
        return {
            (r.path, frozenset(r.methods))
            for r in a.routes
            if hasattr(r, "methods") and r.path in FRONTEND_ROUTES
        }

    real, mock = routes(app.app), routes(mock_ee_backend.app)
    assert {r[0] for r in real} == FRONTEND_ROUTES, "app.py is missing a frontend route"
    assert real == mock, "the mock and the real backend disagree on routes or methods"


# ---------------------------------------------------------------------------
# Response shapes
# ---------------------------------------------------------------------------
def test_health_flags_the_mock(mock_client):
    body = mock_client.get("/").json()
    assert body["status"] == "ok"
    assert body["mock"] is True


def test_every_response_carries_the_mock_header(mock_client, guildford_polygon):
    for method, path, payload in [
        ("get", "/", None),
        ("post", "/api/tile/ndvi", {"year": 2024}),
        ("post", "/api/stats", {"year": 2024, "geometry": guildford_polygon}),
    ]:
        r = getattr(mock_client, method)(path, **({"json": payload} if payload else {}))
        assert r.headers.get("X-Contour-Mock") == "true", f"{path} was not tagged"


@pytest.mark.parametrize("layer", ["ndvi", "landcover"])
def test_tile_endpoints_return_a_usable_xyz_template(mock_client, layer):
    body = mock_client.post(f"/api/tile/{layer}", json={"year": 2024}).json()
    assert list(body) == ["tile_url_template"]
    url = body["tile_url_template"]
    assert url.startswith("http")
    # Leaflet substitutes these; a template missing them would silently 404.
    assert "{z}" in url and "{x}" in url and "{y}" in url


def test_ndvi_and_landcover_are_visually_distinguishable(mock_client):
    a = mock_client.post("/api/tile/ndvi", json={"year": 2024}).json()
    b = mock_client.post("/api/tile/landcover", json={"year": 2024}).json()
    assert a["tile_url_template"] != b["tile_url_template"]


def test_tile_urls_are_overridable_by_env(mock_client, monkeypatch):
    monkeypatch.setenv("MOCK_TILE_URL_NDVI", "https://example.test/{z}/{x}/{y}.png")
    body = mock_client.post("/api/tile/ndvi", json={"year": 2024}).json()
    assert body["tile_url_template"] == "https://example.test/{z}/{x}/{y}.png"


def test_stats_shape(mock_client, guildford_polygon):
    body = mock_client.post(
        "/api/stats", json={"year": 2024, "geometry": guildford_polygon}
    ).json()
    assert set(body) == {"ndvi_mean", "landcover_histogram", "flood_proxy_mean", "area_ha"}


def test_histogram_mirrors_frequencyhistogram(mock_client, guildford_polygon):
    hist = mock_client.post(
        "/api/stats", json={"year": 2024, "geometry": guildford_polygon}
    ).json()["landcover_histogram"]
    assert set(hist) <= CODE_STRINGS
    assert all(isinstance(k, str) for k in hist)
    assert all(isinstance(v, float) and v > 0 for v in hist.values())


def test_histogram_pixel_counts_track_area(mock_client, guildford_polygon):
    """WorldCover is a 10 m product, so counts should sum to area_ha * 100."""
    body = mock_client.post(
        "/api/stats", json={"year": 2024, "geometry": guildford_polygon}
    ).json()
    expected = body["area_ha"] * 10_000 / 100
    assert math.isclose(sum(body["landcover_histogram"].values()), expected, rel_tol=1e-4)


def test_all_classes_can_be_forced(monkeypatch, guildford_polygon):
    """For exercising legend rendering — a real UK site never returns all 11."""
    monkeypatch.setenv("MOCK_STATS_ALL_CLASSES", "1")
    hist = make_stats(2024, guildford_polygon)["landcover_histogram"]
    assert set(hist) == CODE_STRINGS


def test_uk_sites_do_not_return_mangroves_or_snow(guildford_polygon):
    seen = set()
    for year in range(2016, 2027):
        seen |= set(make_stats(year, guildford_polygon)["landcover_histogram"])
    assert not (seen & {"70", "95", "100"}), "implausible classes for a UK site"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------
def test_same_request_gives_identical_stats(mock_client, guildford_polygon):
    payload = {"year": 2024, "geometry": guildford_polygon}
    a = mock_client.post("/api/stats", json=payload).json()
    b = mock_client.post("/api/stats", json=payload).json()
    assert a == b, "the report panel would flicker between reloads"


def test_stats_vary_with_year_and_place(guildford_polygon):
    elsewhere = {
        "type": "Polygon",
        "coordinates": [[[-2.60, 53.40], [-2.58, 53.40], [-2.58, 53.41],
                         [-2.60, 53.41], [-2.60, 53.40]]],
    }
    assert make_stats(2024, guildford_polygon) != make_stats(2019, guildford_polygon)
    assert make_stats(2024, guildford_polygon) != make_stats(2024, elsewhere)


def test_determinism_survives_a_restart():
    """Python salts str hashes per process, so the seeding must not rely on
    hash() — otherwise every restart reshuffles every site.

    This has to cross a process boundary to mean anything: within one process
    hash() is stable, so reloading the module would pass either way.
    """
    import json
    import os
    import pathlib
    import subprocess
    import sys

    root = str(pathlib.Path(__file__).resolve().parent.parent)
    script = (
        "import json,sys; sys.path.insert(0, %r);"
        "from mock_ee_backend import make_stats;"
        "print(json.dumps(make_stats(2024, {'type':'Polygon','coordinates':"
        "[[[-1,52],[-0.99,52],[-0.99,52.01],[-1,52.01],[-1,52]]]}), sort_keys=True))"
    ) % root

    outputs = []
    for seed in ("0", "1", "987654"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        outputs.append(
            subprocess.check_output([sys.executable, "-c", script], env=env, text=True).strip()
        )

    assert len(set(outputs)) == 1, (
        "stats changed between processes with different hash seeds — "
        f"seeding is not stable: {outputs}"
    )
    assert json.loads(outputs[0])["landcover_histogram"]


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
def test_area_matches_a_hand_calculation(guildford_polygon):
    # 0.02 deg lon x 0.01 deg lat at 51.24 N
    #   ~ (0.02 * 111320 * cos 51.24) x (0.01 * 110574) = 1393 m x 1106 m
    expected_ha = (0.02 * 111_320 * math.cos(math.radians(51.24))) * (0.01 * 110_574) / 10_000
    actual = geometry_area_m2(guildford_polygon) / 10_000
    assert math.isclose(actual, expected_ha, rel_tol=0.02)


def test_holes_are_subtracted():
    outer = [[-0.58, 51.235], [-0.56, 51.235], [-0.56, 51.245], [-0.58, 51.245], [-0.58, 51.235]]
    hole = [[-0.575, 51.238], [-0.565, 51.238], [-0.565, 51.242], [-0.575, 51.242], [-0.575, 51.238]]
    assert geometry_area_m2({"type": "Polygon", "coordinates": [outer, hole]}) < \
           geometry_area_m2({"type": "Polygon", "coordinates": [outer]})


def test_multipolygon_areas_add_up():
    a = [[[-0.58, 51.235], [-0.57, 51.235], [-0.57, 51.24], [-0.58, 51.24], [-0.58, 51.235]]]
    b = [[[-0.50, 51.235], [-0.49, 51.235], [-0.49, 51.24], [-0.50, 51.24], [-0.50, 51.235]]]
    total = geometry_area_m2({"type": "MultiPolygon", "coordinates": [a, b]})
    parts = (geometry_area_m2({"type": "Polygon", "coordinates": a})
             + geometry_area_m2({"type": "Polygon", "coordinates": b}))
    assert math.isclose(total, parts, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Errors — must match app.py's contract
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "Point", "coordinates": [-0.58, 51.24]},
        {"type": "Polygon"},
        {"type": "Polygon", "coordinates": [[[0, 0], [1, 1]]]},   # ring too short
        {"type": "Polygon", "coordinates": []},
        "not-an-object",
    ],
)
def test_bad_geometry_is_a_500_with_detail(mock_client, geometry):
    r = mock_client.post("/api/stats", json={"year": 2024, "geometry": geometry})
    assert r.status_code in (422, 500)
    if r.status_code == 500:
        assert isinstance(r.json()["detail"], str) and r.json()["detail"]


@pytest.mark.parametrize("body", [{}, {"year": 2024}, {"geometry": {}}])
def test_malformed_body_is_422(mock_client, body):
    assert mock_client.post("/api/stats", json=body).status_code == 422


def test_out_of_range_month_is_rejected(mock_client):
    assert mock_client.post("/api/tile/ndvi", json={"year": 2024, "month": 13}).status_code == 500
    assert mock_client.post("/api/tile/ndvi", json={"year": 2024, "month": 0}).status_code == 500


# ---------------------------------------------------------------------------
# Plausibility — the mock is only useful if the numbers look like the real ones
# ---------------------------------------------------------------------------
def test_values_stay_in_plausible_uk_ranges():
    import random

    rng = random.Random(11)
    for _ in range(200):
        lat, lng = rng.uniform(50.4, 55.5), rng.uniform(-4.5, 1.2)
        d = rng.choice([0.002, 0.01, 0.03])
        geom = {"type": "Polygon", "coordinates": [[
            [lng, lat], [lng + d, lat], [lng + d, lat + d], [lng, lat + d], [lng, lat]]]}
        s = make_stats(rng.choice([2018, 2021, 2024]), geom)
        assert -1.0 <= s["ndvi_mean"] <= 1.0
        assert 0.0 <= s["flood_proxy_mean"] <= 1.3
        assert s["area_ha"] > 0


def test_price_endpoint_shape(mock_client):
    body = mock_client.post("/api/stats/price", json={"postcode_district": " gu1 "}).json()
    assert set(body) == {"postcode_district", "avg_price", "count"}
    assert body["postcode_district"] == "GU1", "should be normalised like app.py does"


def test_empty_postcode_is_rejected(mock_client):
    assert mock_client.post("/api/stats/price", json={"postcode_district": "  "}).status_code == 500


def test_histogram_never_empty():
    """A site with no land cover at all would divide by zero downstream."""
    import random

    for seed in range(50):
        hist = make_landcover_histogram(random.Random(seed), 10_000.0)
        assert hist
