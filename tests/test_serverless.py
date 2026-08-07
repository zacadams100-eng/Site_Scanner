"""The Vercel serverless entry point.

The deployment path this file supports — one function, no Cloud Run, no
credentials — is the difference between "clone it and run two terminals" and
"here is a link". These tests exist because the failure mode is a 404 in
production that looks like an application routing bug, and Vercel cannot be
exercised from CI.
"""

import importlib
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def handler():
    sys.path.insert(0, "api")
    mod = importlib.import_module("index")
    return mod


def test_the_function_exposes_an_asgi_app(handler):
    assert callable(handler.app)


def test_it_serves_the_catalogue_at_the_real_path(handler):
    client = TestClient(handler.app)
    r = client.get("/api/catalog")
    assert r.status_code == 200
    assert r.json()["summary"]["factor_count"] > 200


def test_it_recovers_the_path_when_vercel_rewrites_to_the_function_name(handler):
    """A rewrite to /api/index must not become a 404. Which form Vercel
    delivers depends on the route that matched, so the handler accepts all of
    them rather than betting on one."""
    client = TestClient(handler.app)
    r = client.get("/api/index/catalog")
    assert r.status_code == 200
    assert "factors" in r.json()


def test_it_recovers_the_path_from_the_original_path_header(handler):
    client = TestClient(handler.app)
    r = client.get("/api/index", headers={"x-vercel-original-path": "/api/catalog"})
    assert r.status_code == 200
    assert "factors" in r.json()

    r = client.get("/", headers={"x-forwarded-uri": "/api/catalog?x=1"})
    assert r.status_code == 200
    assert "factors" in r.json()


def test_the_health_check_still_answers_at_the_root(handler):
    client = TestClient(handler.app)
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers.get("X-Contour-Mock") == "true"


def test_a_series_request_works_end_to_end(handler):
    client = TestClient(handler.app)
    r = client.post("/api/series", json={
        "geometry": {"type": "Polygon", "coordinates": [[
            [-0.58, 51.235], [-0.56, 51.235], [-0.56, 51.245],
            [-0.58, 51.245], [-0.58, 51.235]]]},
        "factor_ids": ["ndvi"], "start": "2024-01", "end": "2024-06",
    })
    assert r.status_code == 200
    assert len(r.json()["series"]["ndvi"]["points"]) == 6
