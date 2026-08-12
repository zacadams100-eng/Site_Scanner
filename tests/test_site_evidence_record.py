"""
The Site Evidence Record.

The record is the product's memory. Everything asserted here is a property
someone reading a two-year-old record has to be able to rely on, and the tests
are grouped by the question that reader is asking:

    Is this the same site as that one?          → identity
    Has anything changed since?                 → stability
    What was actually established?              → states and provenance
    What was never asked?                       → gaps
    Who checked it?                             → review
    Can I still read it?                        → versioning

The identity tests carry the most weight. A site identifier that is not stable
across processes makes longitudinal comparison impossible, and the failure is
silent — every record looks fine on its own, and no two ever match.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import mock_ee_backend
import scanners
import site_record

SITE = {
    "type": "Polygon",
    "coordinates": [[[-0.62, 51.22], [-0.62, 51.28], [-0.54, 51.28],
                     [-0.54, 51.22], [-0.62, 51.22]]],
}

OTHER_SITE = {
    "type": "Polygon",
    "coordinates": [[[-1.62, 52.22], [-1.62, 52.28], [-1.54, 52.28],
                     [-1.54, 52.22], [-1.62, 52.22]]],
}


@pytest.fixture(scope="module")
def client():
    with TestClient(mock_ee_backend.app) as c:
        yield c


@pytest.fixture(scope="module")
def payload(client):
    """A real assessment, not a fixture. The record is a read over the
    product's actual output, and a hand-built payload would let the two drift
    apart without a test noticing."""
    cat = client.get("/api/catalog?scanner=land").json()
    factors = [f["id"] for f in cat["factors"]][:12]
    r = client.post("/api/series", json={
        "geometry": SITE, "factor_ids": factors, "scanner": "land"})
    assert r.status_code == 200, r.text
    body = r.json()
    body.setdefault("geometry", SITE)
    return body


@pytest.fixture(scope="module")
def record(payload):
    return site_record.build(payload, scanner=scanners.resolve("land"),
                             site_name="Test field",
                             assessed_at="2026-08-12T10:00:00Z")


@pytest.fixture
def found(mock_client, live_ndvi):
    """A record that actually contains a finding.

    The mock backend produces none — correctly, because nothing may be claimed
    from generated numbers — which means a record built from it has an empty
    `findings` list and every assertion about findings passes by being
    unreached. Three tests in this file were vacuous until this fixture
    existed, and a vacuous test is worse than a missing one: it reports
    coverage it does not have.

    So this installs a real declining NDVI series the same way the habitat and
    historical suites do, which raises a genuine vegetation-decline flag
    through the ordinary engine path.
    """
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))
    r = mock_client.post("/api/series", json={
        "geometry": SITE, "factor_ids": ["ndvi"], "scanner": "land"})
    assert r.status_code == 200, r.text
    body = r.json()
    body.setdefault("geometry", SITE)
    rec = site_record.build(body, scanner=scanners.resolve("land"),
                            assessed_at="2026-08-12T10:00:00Z")
    assert rec["findings"], (
        "the fixture produced no finding, so every test using it would pass "
        "by being unreached")
    return rec


# ---------------------------------------------------------------------------
# Identity — the property longitudinal comparison rests on
# ---------------------------------------------------------------------------
def test_the_same_ground_is_the_same_site_every_time():
    """The whole reason `site_id` is a content hash rather than a counter.

    Assessed in March and in August, one field must produce one site id or the
    change between the two assessments is unobservable.
    """
    assert site_record.site_id(SITE) == site_record.site_id(SITE)
    assert site_record.site_id(SITE) != site_record.site_id(OTHER_SITE)
    assert site_record.site_id(SITE).startswith("site_")


def test_a_site_id_survives_a_round_trip_through_json():
    """A geometry that has been through a permalink, a database or an HTTP
    request must still be the same site. Float noise from that trip is exactly
    what the rounding exists to absorb."""
    round_tripped = json.loads(json.dumps(SITE))
    assert site_record.site_id(round_tripped) == site_record.site_id(SITE)


def test_a_site_id_ignores_noise_below_the_accuracy_of_any_source():
    """Six decimal places is ~0.1 m. Every source here is orders of magnitude
    coarser, so this cannot merge two genuinely different sites — and without
    it a redrawn polygon would be a new site with no history."""
    nudged = json.loads(json.dumps(SITE))
    nudged["coordinates"][0][0][0] += 1e-9
    assert site_record.site_id(nudged) == site_record.site_id(SITE)


def test_a_site_id_does_not_ignore_a_real_difference():
    """The other half. A shift of a few metres is a different site."""
    moved = json.loads(json.dumps(SITE))
    moved["coordinates"][0][0][0] += 0.0001
    assert site_record.site_id(moved) != site_record.site_id(SITE)


def test_identifiers_say_what_kind_of_thing_they_are(record):
    """An id in a log or a URL should not need a lookup to be understood."""
    assert record["record_id"].startswith("rec_")
    assert record["site"]["id"].startswith("site_")


def test_the_record_id_is_stable_for_one_assessment(payload):
    """Safe to store and safe to deduplicate. Building the same record twice
    must not produce two documents."""
    a = site_record.build(payload, scanner=scanners.resolve("land"))
    b = site_record.build(payload, scanner=scanners.resolve("land"))
    assert a["record_id"] == b["record_id"]


def test_the_record_id_ignores_the_clock(payload):
    """Two identical assessments of one site are one record. Including the
    timestamp would make every re-run a new document with nothing different in
    it, and a portfolio would fill with duplicates that each looked new."""
    a = site_record.build(payload, scanner=scanners.resolve("land"),
                          assessed_at="2026-01-01T00:00:00Z")
    b = site_record.build(payload, scanner=scanners.resolve("land"),
                          assessed_at="2026-08-12T00:00:00Z")
    assert a["record_id"] == b["record_id"]
    assert a["assessed_at"] != b["assessed_at"]


def test_the_record_id_changes_when_the_evidence_does(payload):
    """The property that makes the record auditable: it cannot be edited
    without becoming a different record."""
    tampered = json.loads(json.dumps(payload))
    assert tampered.get("evidence"), (
        "no evidence to tamper with, so this test asserts nothing")
    # The specific edit worth catching: turning a gap into a clear result. It
    # is the one change that makes a record look better than the assessment
    # was, and it must not be possible to make it invisibly.
    tampered["evidence"][0]["state"] = "clear"
    tampered["evidence"][0]["reason"] = None
    a = site_record.build(payload, scanner=scanners.resolve("land"))
    b = site_record.build(tampered, scanner=scanners.resolve("land"))
    assert a["record_id"] != b["record_id"]


def test_the_record_id_changes_when_the_scanner_version_does(payload):
    """A reader comparing two records has to be able to tell "the site
    changed" from "the checks changed". Same evidence under a new scanner
    version is a different record."""
    import dataclasses
    land = scanners.resolve("land")
    bumped = dataclasses.replace(land, version="99.0.0")
    a = site_record.build(payload, scanner=land)
    b = site_record.build(payload, scanner=bumped)
    assert a["record_id"] != b["record_id"]


# ---------------------------------------------------------------------------
# What the record establishes
# ---------------------------------------------------------------------------
def test_every_observation_carries_its_state_and_provenance(record):
    assert record["observations"], "the record established nothing at all"
    for o in record["observations"]:
        assert o["state"] in site_record.EVIDENCE_STATES
        assert "source" in o and "runtime" in o["source"]
        # `EM5`: whether this deployment ran it live is not the same as an
        # entry existing in a registry, and a stored record is exactly where
        # that distinction would otherwise be lost.
        assert o["source"]["runtime"]


def test_an_unassessed_observation_says_why(record):
    """"We could not look" is only useful with the reason attached. A gap
    caused by a source that never answered is closeable; one caused by a
    factor that was never selected is a different action entirely."""
    for o in record["observations"]:
        if o["state"] == "not_assessed":
            assert o["reason"], f"{o['factor']}: unassessed with no reason"


def test_the_claim_boundary_is_carried_and_not_recomposed(record):
    """`EM12`. Two wordings of one boundary drift, and the drift is
    invisible. The record carries what the engine composed."""
    for o in record["observations"]:
        claims = o.get("claims") or {}
        assert claims, f"{o['factor']}: no claim boundary"
        assert claims.get("not_established"), (
            f"{o['factor']}: no limitation stated. A boundary that goes "
            f"missing on some path is worse than none — a reader learns to "
            f"expect it and reads its absence as nothing to qualify.")


def test_a_finding_is_attributed_to_the_domain_that_raised_it(found):
    """The field that makes a record useful to a portfolio. "Eleven sites have
    a finding in Water's coastal domain" cannot be answered from a rule id
    without knowing the taxonomy at read time."""
    land = scanners.resolve("land")
    for f in found["findings"]:
        assert f["domain"] in {d.id for d in land.domains}, (
            f"{f['id']} is attributed to {f['domain']!r}, which is not a "
            f"domain of the scanner that produced it")


def test_a_finding_carries_the_rule_that_reached_it(found):
    """A record read in two years has no access to the rule that raised the
    finding. If the threshold does not travel with it, the finding becomes an
    assertion nobody can check."""
    for f in found["findings"]:
        if f["kind"] != "flag":
            continue
        assert f["statement"], f"{f['id']}: a finding with no statement"
        assert f["rule"] or f["threshold"], (
            f"{f['id']}: neither a rule description nor a threshold, so the "
            f"finding cannot be re-checked by its reader")


def test_the_investigation_chain_is_traceable_backwards(found):
    """From an investigation back to the measurement that caused it. This is
    the difference between a record that is complete and one that is
    auditable."""
    finding_ids = {f["id"] for f in found["findings"]}
    for inv in found["investigations"]:
        assert inv["raised_by"], f"{inv['id']}: raised by nothing"
        for why in inv["raised_by"]:
            assert why in finding_ids, (
                f"{inv['id']} names {why}, which is not a finding in this "
                f"record — the chain is broken")


# ---------------------------------------------------------------------------
# What the record admits it does not know
# ---------------------------------------------------------------------------
def test_the_gaps_block_counts_the_factors_that_could_not_be_assessed(record):
    gaps = record["gaps"]
    unassessed = [o for o in record["observations"]
                  if o["state"] == "not_assessed"]
    assert gaps["factor_count"] == len(unassessed)
    assert sum(gaps["by_reason"].values()) == len(unassessed)


def test_the_record_carries_the_shape_of_its_own_ignorance(payload):
    """The more dangerous gap, and the one no report can show.

    Water returning no groundwater finding looks identical whether groundwater
    was clear or was never asked. The domain gap is the only thing in the
    document that distinguishes them.
    """
    water = scanners.resolve("water")
    rec = site_record.build(payload, scanner=water)
    gaps = rec["gaps"]
    assert gaps["domain_count"] >= 3
    named = {d["id"] for d in gaps["domains"]}
    assert {"groundwater", "drainage", "catchment"} <= named
    for d in gaps["domains"]:
        assert d["blocked_by"], f"{d['id']}: a gap with no reason given"


def test_a_live_scanner_reports_no_domain_gap(record):
    """The other direction. Land covers all seven of its domains, and a
    fabricated gap would be as misleading as a hidden one."""
    assert record["gaps"]["domain_count"] == 0
    assert record["scanner"]["status"] == "live"


# ---------------------------------------------------------------------------
# No score, at any level
# ---------------------------------------------------------------------------
def test_the_record_contains_no_score_grade_or_index(record):
    """`EM7`, checked structurally rather than trusted.

    The record is the most tempting place in the product to add one: it is
    structured, it is comparable, and a portfolio would sort by it. That is
    exactly why it must not be there.
    """
    text = json.dumps(record).lower()
    for banned in ('"score"', '"grade"', '"rating"', '"index"',
                   '"suitability"', '"risk_score"', '"health"'):
        assert banned not in text, f"the record carries a {banned} field"


def test_the_summary_shows_gaps_beside_findings(record):
    """A row showing "3 findings" without "18 unassessed" invites the reading
    this product exists to prevent. Both are counts and neither is a rating."""
    s = site_record.summarise(record)
    assert "flagged" in s and "not_assessed" in s
    assert isinstance(s["flagged"], int)
    assert isinstance(s["not_assessed"], int)
    assert s["factors_assessed"] + s["not_assessed"] == \
        len(record["observations"])


def test_the_summary_cannot_disagree_with_the_record(record):
    """Derived from the record rather than computed alongside it, so a row and
    the document it opens say the same thing."""
    s = site_record.summarise(record)
    assert s["record_id"] == record["record_id"]
    assert s["site_id"] == record["site"]["id"]
    assert s["flagged"] == sum(1 for f in record["findings"]
                               if f["kind"] == "flag")
    assert s["domain_gaps"] == record["gaps"]["domain_count"]


# ---------------------------------------------------------------------------
# Review — defined, and empty
# ---------------------------------------------------------------------------
def test_every_record_says_nobody_has_reviewed_it(record):
    """`unreviewed` is a state, not a missing value — the same distinction the
    whole product rests on, applied to the reviewer instead of the check."""
    review = record["review"]
    assert review["status"] == "unreviewed"
    assert review["reviews"] == []
    assert "No professional has reviewed" in review["statement"]


def test_no_reviewer_is_ever_invented(record):
    """The worst fabrication available in this codebase would be a named
    professional who did not review anything."""
    assert json.dumps(record["review"]).count("reviewer") == 0 or \
        record["review"]["reviews"] == []


# ---------------------------------------------------------------------------
# Versioning — can a reader still read this?
# ---------------------------------------------------------------------------
def test_three_versions_travel_with_every_record(record):
    """Three different questions a reader of an old record asks: did the checks
    change, did the meaning of "assessed" change, did the shape of the document
    change. Collapsed into one, none of them is answerable."""
    assert record["record_schema"] == site_record.RECORD_SCHEMA
    assert record["engine_version"] == site_record.ENGINE_VERSION
    assert record["scanner"]["version"]
    assert record["scanner"]["methodology_version"]


def test_a_record_can_be_built_for_a_scanner_that_no_longer_exists(payload):
    """A record that became unreadable when a scanner was retired would defeat
    the purpose of keeping records. It reports what the payload knows and
    invents no domain gaps."""
    rec = site_record.build(payload, scanner=None)
    assert rec["record_id"].startswith("rec_")
    assert rec["observations"]
    assert rec["gaps"]["domains"] == []
    assert rec["scanner"]["version"] == ""


def test_the_record_is_json_serialisable(record):
    """It is stored and transmitted. A type that survives in memory and fails
    at the database boundary would fail on write, which is the worst place."""
    assert json.loads(json.dumps(record))["record_id"] == record["record_id"]


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------
def test_the_api_serves_a_record_for_an_assessment(client):
    """The endpoint a portfolio calls. Everything a longitudinal view needs is
    here and nowhere else."""
    r = client.post("/api/record", json={
        "geometry": SITE, "factor_ids": ["ndvi", "elevation_mean"],
        "scanner": "land", "site_name": "North field"})
    assert r.status_code == 200, r.text
    rec = r.json()

    assert rec["record_id"].startswith("rec_")
    assert rec["site"]["id"] == site_record.site_id(SITE)
    assert rec["site"]["name"] == "North field"
    assert rec["scanner"]["id"] == "land"
    assert rec["record_schema"] == site_record.RECORD_SCHEMA
    # Stamped by the server, not the client: a record whose assessment time
    # came from the caller could be backdated.
    assert rec["assessed_at"]


def test_two_assessments_of_one_site_share_a_site_id(client):
    """The property the whole longitudinal idea rests on, end to end through
    the API rather than only in the hashing function."""
    body = {"geometry": SITE, "factor_ids": ["ndvi"], "scanner": "land"}
    first = client.post("/api/record", json=body).json()
    second = client.post("/api/record", json={**body, "scanner": "ecology"})
    assert second.status_code == 200, second.text
    second = second.json()

    assert first["site"]["id"] == second["site"]["id"], (
        "one piece of ground assessed by two scanners produced two site ids, "
        "which makes a portfolio unable to group them")
    # Different scanners, so genuinely different records of that one site.
    assert first["record_id"] != second["record_id"]


def test_the_record_endpoint_refuses_an_unbuilt_scanner(client):
    """Same refusal as everywhere else. A record from a scanner that cannot
    assess anything would be a stored document full of silence."""
    r = client.post("/api/record", json={
        "geometry": SITE, "factor_ids": ["ndvi"], "scanner": "heritage"})
    assert r.status_code == 422


def test_a_retired_scanner_id_still_produces_a_record(client):
    """A stored link or client written against `coastal` keeps working, and
    the record names the scanner that actually served it."""
    r = client.post("/api/record", json={
        "geometry": SITE, "factor_ids": ["elevation_mean"],
        "scanner": "coastal"})
    assert r.status_code == 200, r.text
    assert r.json()["scanner"]["id"] == "water"
