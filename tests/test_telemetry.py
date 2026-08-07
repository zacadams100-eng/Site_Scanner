"""Latency instrumentation.

The product's whole claim is speed, and a speed claim that is not measured is
one that will quietly stop being true. What these tests care about is that the
measurement survives the cases where measurement usually stops: the request
that failed, the request that was rate-limited, the tail rather than the mean,
and the long-running process that must not grow without bound while watching
itself.

They also check what is deliberately *not* recorded. A latency log is a poor
place to start keeping records of who asked what about which piece of land.
"""

import json
import logging

import pytest
from fastapi.testclient import TestClient

import ratelimit
import telemetry


@pytest.fixture(autouse=True)
def fresh():
    telemetry.RECORDER.reset()
    ratelimit.LIMITER.reset()
    yield
    telemetry.RECORDER.reset()
    ratelimit.LIMITER.reset()


@pytest.fixture(scope="module")
def client():
    import mock_ee_backend
    return TestClient(mock_ee_backend.app)


AOI = {
    "type": "Polygon",
    "coordinates": [[
        [-0.57, 51.235], [-0.55, 51.235], [-0.55, 51.25], [-0.57, 51.25], [-0.57, 51.235],
    ]],
}


# ---------------------------------------------------------------------------
# Percentiles, not averages
# ---------------------------------------------------------------------------
def test_reports_the_tail_not_the_mean():
    """The failure mode this exists to catch: 99 fast requests and one 10s
    request average out to something that looks healthy."""
    r = telemetry.Recorder()
    for _ in range(99):
        r.record("/api/series", 20.0)
    r.record("/api/series", 10_000.0)

    snap = r.snapshot()["routes"]["/api/series"]
    assert snap["p50_ms"] == 20.0
    assert snap["max_ms"] == 10_000.0
    assert snap["calls"] == 100


def test_percentiles_track_a_known_distribution():
    r = telemetry.Recorder()
    for i in range(1, 101):
        r.record("/api/series", float(i))
    snap = r.snapshot()["routes"]["/api/series"]
    assert snap["p50_ms"] == pytest.approx(50, abs=1)
    assert snap["p95_ms"] == pytest.approx(95, abs=1)
    assert snap["p99_ms"] == pytest.approx(99, abs=1)


def test_percentile_of_nothing_is_not_an_error():
    assert telemetry._percentile([], 0.95) == 0.0


# ---------------------------------------------------------------------------
# Bounds — the monitor must not become the outage
# ---------------------------------------------------------------------------
def test_samples_per_route_are_bounded():
    r = telemetry.Recorder(samples=10)
    for i in range(1000):
        r.record("/api/series", float(i))
    snap = r.snapshot()["routes"]["/api/series"]
    # All 1000 are counted, but only the last 10 are kept.
    assert snap["calls"] == 1000
    assert snap["sampled"] == 10
    assert snap["p50_ms"] >= 990


def test_route_count_is_bounded():
    """A caller probing /api/<random> would otherwise mint a bucket per
    request, turning the instrumentation into the memory leak."""
    r = telemetry.Recorder(max_routes=4)
    for i in range(500):
        r.record(f"/api/{i}", 1.0)
    assert len(r.snapshot()["routes"]) == 4


def test_counters_and_observations_are_bounded_too():
    r = telemetry.Recorder(max_routes=3)
    for i in range(50):
        r.increment(f"c{i}")
        r.observe(f"o{i}", 1.0)
    assert len(r.snapshot()["counters"]) == 3
    assert len(r.snapshot()["observed"]) == 3


# ---------------------------------------------------------------------------
# Where measurement usually stops
# ---------------------------------------------------------------------------
def test_errors_are_counted_separately(client):
    """A 500 that is fast is not a fast request. Without this, a route that
    starts failing immediately reads as a latency improvement."""
    r = telemetry.Recorder()
    r.record("/api/series", 5.0, status=500)
    r.record("/api/series", 5.0, status=200)
    snap = r.snapshot()["routes"]["/api/series"]
    assert snap["calls"] == 2
    assert snap["errors"] == 1


def test_a_rejected_request_is_still_timed(client):
    """A limiter that has started rejecting everything would otherwise show up
    as a sudden, flattering improvement in latency."""
    # /api/catalog costs 0.5, so a budget of 1.0 allows two and refuses eight.
    ratelimit.LIMITER.budget = 1.0
    try:
        codes = [client.get("/api/catalog").status_code for _ in range(10)]
        assert codes.count(429) == 8, "the limiter should have rejected these"

        recorded = telemetry.snapshot()["routes"].get("/api/catalog")
        assert recorded is not None
        # Every attempt was timed, not just the ones that got through.
        assert recorded["calls"] == 10
    finally:
        ratelimit.LIMITER.budget = ratelimit.BUDGET


def test_a_4xx_is_timed(client):
    client.post("/api/series", json={"geometry": AOI, "factor_ids": ["not_a_factor"]})
    assert telemetry.snapshot()["routes"]["/api/series"]["calls"] == 1


# ---------------------------------------------------------------------------
# The middleware and the headers
# ---------------------------------------------------------------------------
def test_timing_headers_are_set(client):
    r = client.get("/api/catalog")
    assert r.status_code == 200
    assert r.headers["Server-Timing"].startswith("app;dur=")
    assert r.headers["X-Response-Time"].endswith("ms")
    # A real, positive duration — not a placeholder.
    assert float(r.headers["Server-Timing"].split("=")[1]) > 0


def test_only_api_paths_are_timed(client):
    client.get("/health")
    assert "/health" not in telemetry.snapshot()["routes"]


# ---------------------------------------------------------------------------
# /api/metrics
# ---------------------------------------------------------------------------
def test_metrics_endpoint_reports_real_traffic(client):
    client.post("/api/series", json={"geometry": AOI, "factor_ids": ["ndvi", "lst_day"]})
    body = client.get("/api/metrics").json()

    assert body["routes"]["/api/series"]["calls"] == 1
    assert body["routes"]["/api/series"]["p50_ms"] > 0
    # The cache counters ride along, because "is it fast" and "is it fast
    # because it is cached" are never useful apart.
    assert "cache" in body
    # How many layers a real query carried, so the latency figures can be read
    # against the work people actually do.
    assert body["observed"]["series.factors"]["p50"] == 2


def test_metrics_says_it_is_per_instance(client):
    """The number most likely to be misquoted is the one read straight off an
    endpoint by somebody who never opened telemetry.py."""
    body = client.get("/api/metrics").json()
    assert "per-instance" in body["sampled_from"]
    assert "not per-deployment" in body["sampled_from"]


def test_metrics_is_cheap_enough_to_poll():
    assert ratelimit.cost_for("/api/metrics") < 1.0


# ---------------------------------------------------------------------------
# What is not recorded
# ---------------------------------------------------------------------------
def test_the_log_line_carries_no_user_data(client, caplog):
    with caplog.at_level(logging.INFO, logger="site_scanner.telemetry"):
        client.post("/api/series", json={"geometry": AOI, "factor_ids": ["ndvi"]})

    lines = [json.loads(r.message) for r in caplog.records
             if r.name == "site_scanner.telemetry"]
    assert lines, "a request should produce exactly one structured line"
    for line in lines:
        # Parseable six months from now without a regex — that is the whole
        # reason it is JSON.
        assert set(line) == {"evt", "route", "method", "status", "ms"}
        assert "51.2" not in json.dumps(line)   # no geometry
        assert "127.0.0.1" not in json.dumps(line)  # no client address


def test_metrics_body_carries_no_geometry(client):
    client.post("/api/series", json={"geometry": AOI, "factor_ids": ["ndvi"]})
    body = json.dumps(client.get("/api/metrics").json())
    assert "-0.57" not in body
    assert "coordinates" not in body


def test_a_slow_request_is_logged_louder(caplog):
    with caplog.at_level(logging.INFO, logger="site_scanner.telemetry"):
        telemetry._log("/api/series", telemetry.SLOW_MS + 1, 200, "POST")
        telemetry._log("/api/series", 5.0, 200, "POST")
    levels = [r.levelno for r in caplog.records if r.name == "site_scanner.telemetry"]
    assert logging.WARNING in levels
    assert logging.INFO in levels
