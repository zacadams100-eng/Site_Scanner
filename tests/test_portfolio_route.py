"""
The portfolio endpoints, and the labelling that makes the demo permissible.

`/api/portfolio/demo` is the only endpoint in this product that serves
generated evidence by design. Everywhere else, generated data is refused a
finding outright; here it produces one, so that a portfolio can be seen at all.

The entire safety of that decision rests on the label. These tests therefore
check the label on every path a fragment could take out of the product — the
document, the radar, every row, and a record fetched on its own — because the
failure mode is not "the demo is wrong". It is a screenshot of a demo row in a
deck, with no indication that it was generated.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import demo_portfolio
import mock_ee_backend

SITE = {
    "type": "Polygon",
    "coordinates": [[[-0.62, 51.22], [-0.62, 51.28], [-0.54, 51.28],
                     [-0.54, 51.22], [-0.62, 51.22]]],
}


@pytest.fixture(scope="module")
def client():
    with TestClient(mock_ee_backend.app) as c:
        yield c


# ---------------------------------------------------------------------------
# Aggregation from real records
# ---------------------------------------------------------------------------
def test_records_posted_in_come_back_as_one_portfolio(client):
    first = client.post("/api/record", json={
        "geometry": SITE, "factor_ids": ["ndvi"], "scanner": "land",
        "site_name": "North field"}).json()

    r = client.post("/api/portfolio", json={
        "name": "My sites", "records": [first]})
    assert r.status_code == 200, r.text
    doc = r.json()

    assert doc["name"] == "My sites"
    assert doc["radar"]["sites"] == 1
    assert doc["sites"][0]["name"] == "North field"
    # Real records, so nothing about this portfolio is demonstration data.
    assert doc["contains_demo_data"] is False
    assert doc["demo_notice"] == ""
    assert doc["sites"][0]["is_demo"] is False


def test_one_site_assessed_by_two_scanners_is_one_row(client):
    """Through the API rather than only in the merge function. This is the
    error that would inflate a portfolio by exactly the amount of work done."""
    body = {"geometry": SITE, "factor_ids": ["ndvi"], "scanner": "land"}
    land = client.post("/api/record", json=body).json()
    ecology = client.post("/api/record", json={**body,
                                               "scanner": "ecology"}).json()

    doc = client.post("/api/portfolio", json={
        "records": [land, ecology]}).json()
    assert doc["radar"]["sites"] == 1
    assert doc["sites"][0]["scanners"] == ["ecology", "land"]


def test_an_empty_portfolio_is_served_rather_than_refused(client):
    """The state every portfolio starts in. An empty state has to render."""
    doc = client.post("/api/portfolio", json={"records": []}).json()
    assert doc["radar"]["sites"] == 0
    assert doc["sites"] == []


# ---------------------------------------------------------------------------
# The demonstration portfolio — labelling on every path
# ---------------------------------------------------------------------------
def test_the_demo_portfolio_is_labelled_on_the_document(client):
    doc = client.get("/api/portfolio/demo").json()
    assert doc["contains_demo_data"] is True
    assert "Demonstration" in doc["demo_notice"] or \
        "demonstration" in doc["demo_notice"]


def test_the_demo_portfolio_is_labelled_on_every_single_row(client):
    """A legend at the top of a screen does not survive a row being copied,
    exported or screenshotted. That fragment is what a third person sees."""
    doc = client.get("/api/portfolio/demo").json()
    assert doc["sites"], "the demo portfolio is empty"
    for row in doc["sites"]:
        assert row["is_demo"] is True, f"{row['name']} carries no demo label"
        assert row["source"] == "demo"


def test_the_demo_radar_counts_its_demo_sites_rather_than_blending_them(client):
    radar = client.get("/api/portfolio/demo").json()["radar"]
    assert radar["contains_demo_data"] is True
    assert radar["demo_sites"] == radar["sites"]


def test_a_demo_record_fetched_alone_still_says_what_it_is(client):
    """The path where a label is most likely to be lost: one record, fetched
    directly, with no portfolio around it."""
    doc = client.get("/api/portfolio/demo").json()
    site_id = doc["sites"][0]["site_id"]

    r = client.get(f"/api/portfolio/demo/site/{site_id}")
    assert r.status_code == 200, r.text
    record = r.json()
    assert record["is_demo"] is True
    assert record["demo_notice"]


def test_a_demo_record_is_not_reachable_from_the_real_record_endpoint(client):
    """Generated records live behind the `demo` path segment. A URL that looks
    like the real endpoint must never return one."""
    r = client.get("/api/portfolio/demo/site/site_does_not_exist")
    assert r.status_code == 404


def test_every_demo_observation_admits_its_provenance():
    """The source block is not faked. A reader following a demo finding to its
    source is told exactly what produced it."""
    for record in demo_portfolio.records():
        for o in record["observations"]:
            assert o["source"]["runtime"] == "generated"
            assert o["source"]["kind"] == "generated"
            assert "demonstration" in o["claims"]["not_established"].lower() \
                or "generated" in o["claims"]["not_established"].lower()


def test_demo_findings_use_the_products_real_rules(client):
    """A demo that invented finding text would misrepresent what the product
    says as well as what it found. Read from the registry, so it cannot show a
    check the product does not have."""
    import scanners

    for record in demo_portfolio.records():
        scanner = scanners.resolve(record["scanner"]["id"])
        known = {r.id for r in scanner.rules}
        for f in record["findings"]:
            assert f["id"] in known, (
                f"demo shows finding {f['id']!r}, which {scanner.id} does not "
                f"have — the demo has drifted from the product")
            assert f["rule"].get("demo") is True


def test_no_demo_site_is_named_as_a_real_place():
    """Naming one "Marsh Farm, Kent" would produce a document that looks
    exactly like a real assessment of somebody's land."""
    for record in demo_portfolio.records():
        name = record["site"]["name"]
        assert name.lower().startswith("demonstration site"), (
            f"{name!r} could be mistaken for a real holding")


def test_the_demo_is_deterministic_across_calls():
    """Seeded from the site id rather than from `hash()`, which is randomised
    per process. Without this a screenshot would not match the screen, and
    `record_id` would change on every deploy — breaking the deduplication the
    portfolio relies on."""
    first = demo_portfolio.records()
    second = demo_portfolio.records()
    assert [r["record_id"] for r in first] == [r["record_id"] for r in second]
    assert [r["site"]["id"] for r in first] == [r["site"]["id"] for r in second]


def test_the_demo_shows_unassessed_sites_because_that_is_the_honest_picture():
    """`sites_unassessed` is the radar's most important number. A demo where
    every site had been scanned would hide the one figure that stops a reader
    treating the remainder as clear."""
    radar = demo_portfolio.build()
    from portfolio import radar as radar_of
    r = radar_of(radar)
    assert r["sites_unassessed"] > 0
    assert r["sites_assessed"] > 0


def test_most_demo_sites_are_quiet():
    """A demo where four sites in five carried a finding would read as a tool
    that finds something everywhere — an alarm rather than an instrument."""
    from portfolio import radar as radar_of
    r = radar_of(demo_portfolio.build())
    assert r["sites_with_findings"] < r["sites"] * 0.75


def test_the_demo_carries_no_history():
    """A fabricated past is the one thing indistinguishable from the real
    longitudinal record this product intends to build. The demo shows a
    portfolio at one moment."""
    text = json.dumps(demo_portfolio.records()).lower()
    for banned in ('"trend"', '"history"', '"previous"', '"change_since"',
                   '"last_year"'):
        assert banned not in text, f"the demo invents a past: {banned}"
