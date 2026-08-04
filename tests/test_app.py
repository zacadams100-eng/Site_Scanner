"""
app.py — request/response shapes, caching, and error handling.

Earth Engine is faked (see conftest.py); these assert the contract the
frontend depends on, not the correctness of the EE expressions.
"""

import pytest

from conftest import STATE

WORLDCOVER_CODES = {"10", "20", "30", "40", "50", "60", "70", "80", "90", "95", "100"}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
def test_health_shape(app_client):
    r = app_client.get("/")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "message": "Site Scanner Earth Engine API is running"}


# ---------------------------------------------------------------------------
# Tiles
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("layer", ["ndvi", "landcover"])
def test_tile_returns_only_a_url_template(app_client, layer):
    r = app_client.post(f"/api/tile/{layer}", json={"year": 2024})
    assert r.status_code == 200
    body = r.json()
    # The frontend passes this straight to L.tileLayer, so the key name and
    # the fact that nothing else is present both matter.
    assert list(body) == ["tile_url_template"]
    assert isinstance(body["tile_url_template"], str)
    assert "{z}" in body["tile_url_template"]


@pytest.mark.parametrize("layer", ["ndvi", "landcover"])
def test_tile_accepts_optional_month(app_client, layer):
    assert app_client.post(f"/api/tile/{layer}", json={"year": 2024, "month": 6}).status_code == 200


@pytest.mark.parametrize("body", [{}, {"month": 6}, {"year": "not-a-year"}, {"year": None}])
def test_tile_rejects_malformed_body_with_422(app_client, body):
    assert app_client.post("/api/tile/ndvi", json=body).status_code == 422


def test_tile_earth_engine_failure_becomes_500_with_detail(app_client):
    STATE.failure = RuntimeError("EE quota exceeded")
    r = app_client.post("/api/tile/ndvi", json={"year": 2024})
    assert r.status_code == 500
    assert "EE quota exceeded" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------
def test_stats_shape(app_client, guildford_polygon):
    r = app_client.post("/api/stats", json={"year": 2024, "geometry": guildford_polygon})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"ndvi_mean", "landcover_histogram", "flood_proxy_mean", "area_ha"}
    assert isinstance(body["ndvi_mean"], float)
    assert isinstance(body["flood_proxy_mean"], float)
    assert isinstance(body["area_ha"], float)
    assert isinstance(body["landcover_histogram"], dict)


def test_stats_histogram_uses_string_esa_codes_and_float_counts(app_client, guildford_polygon):
    body = app_client.post(
        "/api/stats", json={"year": 2024, "geometry": guildford_polygon}
    ).json()
    hist = body["landcover_histogram"]
    assert hist, "a real site always has at least one land cover class"
    # ee.Reducer.frequencyHistogram() returns string keys and float pixel
    # counts. The frontend parses codes with Number(); if these ever became
    # ints the JSON would still work but the contract would have drifted.
    assert set(hist) <= WORLDCOVER_CODES
    assert all(isinstance(k, str) for k in hist)
    assert all(isinstance(v, float) for v in hist.values())
    assert all(v > 0 for v in hist.values())


def test_stats_ndvi_within_sensor_range(app_client, guildford_polygon):
    body = app_client.post(
        "/api/stats", json={"year": 2024, "geometry": guildford_polygon}
    ).json()
    assert -1.0 <= body["ndvi_mean"] <= 1.0


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"year": 2024},                                   # geometry missing
        {"geometry": {"type": "Polygon", "coordinates": []}},  # year missing
        {"year": 2024, "geometry": "not-an-object"},
    ],
)
def test_stats_rejects_malformed_body_with_422(app_client, body):
    assert app_client.post("/api/stats", json=body).status_code == 422


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "Point", "coordinates": [-0.58, 51.24]},
        {"type": "Polygon"},
        {"coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
        {},
    ],
)
def test_stats_bad_geometry_becomes_500_with_detail(app_client, geometry):
    # ee.Geometry() raises on these, and app.py's blanket except turns any
    # exception into a 500 — not a 422, because the body itself parsed fine.
    r = app_client.post("/api/stats", json={"year": 2024, "geometry": geometry})
    assert r.status_code == 500
    assert isinstance(r.json()["detail"], str) and r.json()["detail"]


def test_stats_earth_engine_failure_becomes_500(app_client, guildford_polygon):
    STATE.failure = RuntimeError("computation timed out")
    r = app_client.post("/api/stats", json={"year": 2024, "geometry": guildford_polygon})
    assert r.status_code == 500
    assert "computation timed out" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------
def test_repeated_stats_request_does_not_recompute(app_client, guildford_polygon):
    payload = {"year": 2024, "geometry": guildford_polygon}
    first = app_client.post("/api/stats", json=payload).json()
    assert STATE.calls["stats"] == 1

    second = app_client.post("/api/stats", json=payload).json()
    assert second == first
    assert STATE.calls["stats"] == 1, "second identical request should have been served from cache"


def test_stats_cache_keys_on_year(app_client, guildford_polygon):
    app_client.post("/api/stats", json={"year": 2024, "geometry": guildford_polygon})
    app_client.post("/api/stats", json={"year": 2019, "geometry": guildford_polygon})
    assert STATE.calls["stats"] == 2


def test_stats_cache_keys_on_geometry(app_client, guildford_polygon):
    other = {
        "type": "Polygon",
        "coordinates": [[[-0.50, 51.20], [-0.49, 51.20], [-0.49, 51.21],
                         [-0.50, 51.21], [-0.50, 51.20]]],
    }
    app_client.post("/api/stats", json={"year": 2024, "geometry": guildford_polygon})
    app_client.post("/api/stats", json={"year": 2024, "geometry": other})
    assert STATE.calls["stats"] == 2


def test_stats_cache_ignores_key_ordering(app_client, guildford_polygon):
    """The same polygon with JSON keys in a different order is the same site."""
    reordered = {"coordinates": guildford_polygon["coordinates"], "type": "Polygon"}
    app_client.post("/api/stats", json={"year": 2024, "geometry": guildford_polygon})
    app_client.post("/api/stats", json={"geometry": reordered, "year": 2024})
    assert STATE.calls["stats"] == 1


def test_tile_cache_keys_on_year_and_month(app_client):
    app_client.post("/api/tile/ndvi", json={"year": 2024})
    app_client.post("/api/tile/ndvi", json={"year": 2024})
    assert STATE.calls["tile"] == 1

    app_client.post("/api/tile/ndvi", json={"year": 2024, "month": 6})
    assert STATE.calls["tile"] == 2

    app_client.post("/api/tile/ndvi", json={"year": 2023})
    assert STATE.calls["tile"] == 3


def test_ndvi_and_landcover_tiles_do_not_share_cache_entries(app_client):
    """Both take the same request body — without the layer in the key, one
    would serve the other's URL."""
    ndvi = app_client.post("/api/tile/ndvi", json={"year": 2024}).json()
    app_client.post("/api/tile/landcover", json={"year": 2024}).json()
    assert STATE.calls["tile"] == 2, "landcover must not hit the ndvi entry"
    assert list(ndvi) == ["tile_url_template"]


def test_failed_requests_are_not_cached(app_client, guildford_polygon):
    STATE.failure = RuntimeError("transient EE error")
    assert app_client.post(
        "/api/stats", json={"year": 2024, "geometry": guildford_polygon}
    ).status_code == 500

    STATE.failure = None
    r = app_client.post("/api/stats", json={"year": 2024, "geometry": guildford_polygon})
    assert r.status_code == 200, "a transient failure must not be cached as a result"


def test_cache_info_endpoint(app_client, guildford_polygon):
    app_client.post("/api/stats", json={"year": 2024, "geometry": guildford_polygon})
    app_client.post("/api/stats", json={"year": 2024, "geometry": guildford_polygon})

    body = app_client.get("/api/cache").json()
    assert set(body) == {"tiles", "stats", "series"}
    assert set(body["stats"]) == {
        "enabled", "entries", "max_entries", "ttl_seconds", "hits", "misses",
    }
    assert body["stats"]["hits"] == 1
    assert body["stats"]["misses"] == 1
    assert body["stats"]["entries"] == 1


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
def test_summary_shape_without_api_key(app_client, guildford_polygon, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    stats = app_client.post(
        "/api/stats", json={"year": 2024, "geometry": guildford_polygon}
    ).json()

    r = app_client.post("/api/summary", json={"year": 2024, "stats": stats})
    assert r.status_code == 200
    body = r.json()
    assert body["generated_by"] == "fallback"
    assert isinstance(body["summary"], str) and len(body["summary"]) > 60


def test_summary_rejects_malformed_body_with_422(app_client):
    assert app_client.post("/api/summary", json={"year": 2024}).status_code == 422


# ---------------------------------------------------------------------------
# Price — HM Land Registry, not Earth Engine. `requests` is stubbed so no
# outbound call is made.
# ---------------------------------------------------------------------------
class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


@pytest.fixture
def stub_requests(monkeypatch):
    """Replaces requests.get for the duration of a test and records the call."""
    import requests

    captured = {}

    def install(payload=None, status=200, raises=None):
        def fake_get(url, **kwargs):
            captured["url"] = url
            captured["params"] = kwargs.get("params")
            captured["timeout"] = kwargs.get("timeout")
            if raises:
                raise raises
            return _FakeResponse(payload, status)

        monkeypatch.setattr(requests, "get", fake_get)
        return captured

    return install


def test_price_returns_normalised_district(app_client, stub_requests):
    captured = stub_requests({
        "results": {"bindings": [
            {"avgPrice": {"value": "425000.5"}, "count": {"value": "132"}}
        ]}
    })
    r = app_client.post("/api/stats/price", json={"postcode_district": " gu1 "})
    assert r.status_code == 200
    assert r.json() == {"postcode_district": "GU1", "avg_price": 425000.5, "count": 132}
    assert "landregistry" in captured["url"]
    assert captured["timeout"], "an unbounded request would hang the worker"


def test_price_handles_no_matching_transactions(app_client, stub_requests):
    stub_requests({"results": {"bindings": []}})
    body = app_client.post("/api/stats/price", json={"postcode_district": "ZZ99"}).json()
    assert body == {"postcode_district": "ZZ99", "avg_price": None, "count": 0}


def test_price_upstream_failure_becomes_500_with_the_reason(app_client, stub_requests):
    stub_requests(raises=RuntimeError("Land Registry timed out"))
    r = app_client.post("/api/stats/price", json={"postcode_district": "GU1"})
    assert r.status_code == 500
    # The specific cause must survive to the client, not be flattened to a
    # generic message — this is the only signal for diagnosing a live failure.
    assert "Land Registry timed out" in r.json()["detail"]


def test_price_rejects_malformed_body_with_422(app_client):
    assert app_client.post("/api/stats/price", json={}).status_code == 422
