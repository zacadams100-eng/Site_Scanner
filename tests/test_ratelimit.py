"""Rate limiting.

The failure this guards against is not a crash. It is one script quietly
spending an Earth Engine quota that is shared with every other user of the
app, which shows up as everyone else's requests failing for reasons they
cannot see. So the tests care as much about who is *not* limited as who is.
"""

import pytest
from fastapi.testclient import TestClient

import ratelimit


@pytest.fixture(autouse=True)
def fresh():
    ratelimit.LIMITER.reset()
    yield
    ratelimit.LIMITER.reset()


@pytest.fixture(scope="module")
def client():
    import mock_ee_backend
    return TestClient(mock_ee_backend.app)


# ---------------------------------------------------------------------------
# The window
# ---------------------------------------------------------------------------
def test_allows_up_to_the_budget_then_refuses():
    w = ratelimit.SlidingWindow(budget=10, window=60)
    assert all(w.check("a", 1.0, now=0.0)[0] for _ in range(10))
    allowed, remaining, retry_after = w.check("a", 1.0, now=0.0)
    assert not allowed
    assert remaining == 0
    assert retry_after == pytest.approx(60, abs=1)


def test_the_window_slides():
    w = ratelimit.SlidingWindow(budget=2, window=60)
    assert w.check("a", 1.0, now=0.0)[0]
    assert w.check("a", 1.0, now=10.0)[0]
    assert not w.check("a", 1.0, now=20.0)[0]
    # The first request ages out at t=60, which frees exactly its cost.
    assert w.check("a", 1.0, now=61.0)[0]
    assert not w.check("a", 1.0, now=61.0)[0]


def test_a_refused_request_is_not_counted():
    """Otherwise a client that is already over can hold itself over forever by
    retrying, turning a one-minute limit into a permanent ban."""
    w = ratelimit.SlidingWindow(budget=1, window=60)
    assert w.check("a", 1.0, now=0.0)[0]
    for _ in range(50):
        assert not w.check("a", 1.0, now=10.0)[0]
    # One second after the original request ages out, the client is served.
    assert w.check("a", 1.0, now=61.0)[0]


def test_clients_are_independent():
    w = ratelimit.SlidingWindow(budget=1, window=60)
    assert w.check("a", 1.0, now=0.0)[0]
    assert not w.check("a", 1.0, now=0.0)[0]
    assert w.check("b", 1.0, now=0.0)[0], "one client must not limit another"


def test_expensive_routes_cost_more():
    assert ratelimit.cost_for("/api/series") > ratelimit.cost_for("/api/catalog")
    assert ratelimit.cost_for("/api/ask") == ratelimit.cost_for("/api/series")
    assert ratelimit.cost_for("/api/unknown-route") == 1.0


def test_browsing_the_catalogue_stays_cheap():
    """The factor browser refetches the catalogue; throttling that would break
    ordinary use while doing nothing about the calls that cost anything."""
    w = ratelimit.SlidingWindow(budget=ratelimit.BUDGET, window=60)
    cost = ratelimit.cost_for("/api/catalog")
    served = sum(1 for _ in range(300) if w.check("a", cost, now=0.0)[0])
    assert served >= 200


def test_tracked_clients_are_bounded():
    """X-Forwarded-For is forgeable, so an unbounded map of clients would make
    this middleware the memory exhaustion it exists to prevent."""
    w = ratelimit.SlidingWindow(budget=10, window=60, max_clients=50)
    for i in range(500):
        w.check(f"client-{i}", 1.0, now=float(i))
    assert len(w._hits) <= 50


# ---------------------------------------------------------------------------
# Identifying the caller
# ---------------------------------------------------------------------------
def test_client_key_prefers_the_forwarded_address():
    """Behind Vercel and Cloud Run the socket address is the proxy — limiting
    on it would rate-limit every user as though they were one client."""
    key = ratelimit.client_key({"x-forwarded-for": "203.0.113.7, 10.0.0.1"}, "10.0.0.1")
    assert key == "203.0.113.7"


def test_client_key_falls_back_to_the_socket():
    assert ratelimit.client_key({}, "198.51.100.4") == "198.51.100.4"
    assert ratelimit.client_key({}, None) == "unknown"


# ---------------------------------------------------------------------------
# Through the app
# ---------------------------------------------------------------------------
def test_headers_report_the_budget(client):
    r = client.get("/api/catalog")
    assert r.status_code == 200
    assert int(r.headers["X-RateLimit-Limit"]) == int(ratelimit.BUDGET)
    assert "X-RateLimit-Remaining" in r.headers


def test_over_the_limit_returns_429_with_retry_after(client):
    for _ in range(400):
        r = client.get("/api/catalog")
        if r.status_code == 429:
            break
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) >= 1
    # `detail` is the field the frontend surfaces verbatim, so the user is told
    # what happened rather than shown a bare status code.
    assert "Too many requests" in r.json()["detail"]


def test_non_api_paths_are_not_limited(client):
    ratelimit.LIMITER.reset()
    for _ in range(400):
        assert client.get("/").status_code == 200
