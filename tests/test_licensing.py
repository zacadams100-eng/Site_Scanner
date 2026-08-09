"""Commercial clearance.

The point of this module is that a licensing decision is enforced by code
rather than recorded in a document, because a document does not stop a number
reaching a customer's PDF.

So the tests are mostly about the enforcement holding under the conditions
where it would actually be tested: a blocked source must not be queried, must
not return a value, and must not acquire one further down the pipeline in a
chart, an export or an AI summary.
"""

import pytest
from fastapi.testclient import TestClient

import catalog
import licensing
import routes_catalog


AOI = {
    "type": "Polygon",
    "coordinates": [[
        [-0.57, 51.235], [-0.55, 51.235], [-0.55, 51.25], [-0.57, 51.25], [-0.57, 51.235],
    ]],
}


@pytest.fixture(scope="module")
def client():
    import mock_ee_backend
    return TestClient(mock_ee_backend.app)


@pytest.fixture
def block_ndvi(monkeypatch):
    """Block the base NDVI belongs to, for the duration of one test."""
    base = catalog.FACTOR_BY_ID["ndvi"]["base"]
    monkeypatch.setattr(licensing, "BLOCKED_BASES",
                        {base: "test: licence position unresolved"})
    return base


# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------
def test_every_base_resolves_to_a_state():
    """No base may be silently absent from the licensing view. A source with
    no state is one nobody decided about, which is the condition this exists
    to make visible."""
    for base in catalog.BASES:
        assert licensing.status_for_base(base["id"]) in (
            licensing.CLEARED, licensing.CONDITIONAL,
            licensing.UNKNOWN, licensing.BLOCKED)


def test_a_verify_licence_is_conditional_not_cleared():
    """`commercial='verify'` in the catalogue means somebody flagged a doubt.
    Reading that as cleared would erase the flag."""
    assert licensing.status_for_base("sentinel2_sr") == licensing.CONDITIONAL
    assert "share-alike" in licensing.reason_for_base("sentinel2_sr").lower()


def test_an_unknown_factor_is_unknown_not_cleared():
    """The default must fail closed. A typo in a factor id resolving to
    `cleared` would be the worst possible default."""
    assert licensing.status_for_factor("no_such_factor") == licensing.UNKNOWN


def test_nothing_is_blocked_today_and_that_is_deliberate():
    """Marking a source blocked on suspicion takes a working factor away on no
    evidence, which is the mirror image of shipping one on no evidence. The
    unresolved risks are `conditional` and carried in LEGAL_ACTION_PLAN.md."""
    assert licensing.BLOCKED_BASES == {}
    assert licensing.summary()["base_counts"]["blocked"] == 0


# ---------------------------------------------------------------------------
# Enforcement — the part that matters
# ---------------------------------------------------------------------------
def test_a_blocked_factor_returns_no_values(client, block_ndvi):
    body = client.post("/api/series",
                       json={"geometry": AOI, "factor_ids": ["ndvi"]}).json()
    series = body["series"]["ndvi"]
    assert series["source"] == "unavailable"
    assert series["points"] == []
    assert series["annual"] == []
    assert "unresolved" in series["unavailable_reason"]


def test_a_blocked_factor_is_never_queried(monkeypatch, client, block_ndvi):
    """Refused before the fetch, not after. A blocked source that is still
    called has already been used — the request left the building, the upstream
    counted it, and only the rendering was suppressed."""
    called = []
    monkeypatch.setattr(routes_catalog, "_series_for",
                        lambda *a, **k: called.append(a) or {})
    client.post("/api/series", json={"geometry": AOI, "factor_ids": ["ndvi"]})
    assert called == []


def test_blocking_one_factor_does_not_break_the_others(client, block_ndvi):
    body = client.post("/api/series", json={
        "geometry": AOI, "factor_ids": ["ndvi", "precip_total"]}).json()
    assert body["series"]["ndvi"]["source"] == "unavailable"
    assert body["series"]["precip_total"]["points"], \
        "an unrelated factor must still serve"


def test_a_blocked_factor_is_not_counted_as_real(client, block_ndvi):
    """`real_factors` drives the honesty labelling and the export footer. A
    blocked factor appearing there would be counted as delivered data."""
    body = client.post("/api/series",
                       json={"geometry": AOI, "factor_ids": ["ndvi"]}).json()
    assert "ndvi" not in (body.get("real_factors") or [])


def test_a_blocked_factor_gets_no_baseline(client, block_ndvi):
    """A percentile is a customer-facing statistic derived from the source.
    Suppressing the value but shipping "higher than 9 in 10 places" would
    publish the analysis while claiming not to."""
    body = client.post("/api/series",
                       json={"geometry": AOI, "factor_ids": ["ndvi"]}).json()
    assert body["series"]["ndvi"]["baseline"] is None


def test_a_blocked_factor_produces_no_findings(client, block_ndvi):
    """insights.py turns series into sentences. A blocked source must not
    reach the one part of the product written to sound authoritative."""
    body = client.post("/api/series",
                       json={"geometry": AOI, "factor_ids": ["ndvi"]}).json()
    for finding in body.get("insights") or []:
        assert finding["factor"] != "ndvi"


# ---------------------------------------------------------------------------
# What is claimed
# ---------------------------------------------------------------------------
def test_clearance_says_it_is_not_a_legal_opinion():
    """The strongest available claim is "the licence we recorded appears to
    permit this". Anything read as more than that is the failure mode of the
    whole exercise."""
    c = licensing.clearance("ndvi")
    assert "not checked against the publisher" in c["basis"]


def test_the_summary_states_that_no_licence_page_was_fetched():
    s = licensing.summary()
    assert s["verified_against_publisher"] is False
    assert "No licence page has been fetched" in s["note"]
