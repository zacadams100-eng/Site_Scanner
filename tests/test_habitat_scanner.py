"""
Habitat Scanner, end to end.

Scanner #2, and the first real test of whether the platform abstraction
survives a second product rather than a fabricated one.

The rules here are the shipped rules, not experiment stand-ins. What is
fabricated is the *data* — a Sentinel-2-shaped NDVI series installed through
`REAL_SERIES`, exactly as the land scanner's tests do it, because Earth Engine
is not reachable from this environment.

The claim under test: **Habitat required no engine change.** If any assertion
here needed `radar.py`, `evidence.py`, `investigation.py`, `brief.py` or
`claims.py` to be modified, the abstraction was too optimistic and the diff
would say so.
"""

import pytest

import brief
import evidence
import investigation
import radar
import scanners

GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[
        [-0.58, 51.235], [-0.56, 51.235], [-0.56, 51.245],
        [-0.58, 51.245], [-0.58, 51.235],
    ]],
}

HABITAT_FACTORS = ["ndvi", "ndmi", "evi"]


def fetch(client, factors=("ndvi",), scanner="habitat"):
    r = client.post("/api/series", json={
        "geometry": GEOMETRY, "factor_ids": list(factors), "scanner": scanner})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# The scanner runs through the shared chain
# ---------------------------------------------------------------------------
def test_habitat_assesses_through_the_same_api_as_land(mock_client, live_ndvi):
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))
    body = fetch(mock_client)

    # The habitat domain's own vocabulary, carried intact into Ecology. The
    # scanner adds vegetation and designations from the core rule set, which is
    # what makes it an ecology scanner rather than a habitat one — but nothing
    # the habitat package contributed may go missing in the move.
    topics = {t["id"] for t in body["radar"]["topics"]}
    assert {"condition", "moisture", "cover", "water", "structure"} <= topics
    # Still not land's flood vocabulary. Ecology is not the sweep.
    assert "flood" not in topics
    assert "terrain" not in topics and "ground" not in topics


def test_a_habitat_decline_raises_an_ecological_appraisal(mock_client, live_ndvi):
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))
    body = fetch(mock_client)

    assert "habitat_vegetation_decline" in {f["id"] for f in body["radar"]["flags"]}
    raised = [i for i in body["radar"]["investigations"] if i["id"] == "ecology_survey"]
    assert raised and raised[0]["name"] == "Preliminary ecological appraisal"


def test_the_whole_downstream_chain_carries_habitat(mock_client, live_ndvi):
    """radar → evidence → investigation → brief, with no module changed."""
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))
    body = fetch(mock_client)

    entry = next(e for e in body["evidence"] if e["factor"] == "ndvi")
    assert entry["state"] == "flagged"

    work = investigation.find(body["workspace"], "ecology_survey")
    assert work and work["chains"], "the evidence chain assembles for habitat"
    hist = next(c for c in work["chains"]
                if c["rule"] == "Habitat vegetation condition change")
    assert [s["label"] for s in hist["steps"]] == [
        "Source", "Observation", "Method", "Evidence observed", "Compared",
        "Threshold", "Finding"]

    r = mock_client.post("/api/brief", json={
        "geometry": GEOMETRY, "factor_ids": ["ndvi"], "scanner": "habitat",
        "site_name": "Manor Meadow"})
    assert r.status_code == 200
    doc = r.json()
    assert doc["findings"] and doc["findings"][0]["not_established"]


# ---------------------------------------------------------------------------
# The threshold, and what it is not
# ---------------------------------------------------------------------------
def test_habitat_reuses_the_threshold_rather_than_copying_it():
    """Two scanners holding two copies of one number is how they drift, and the
    first symptom would be the app and the brief disagreeing about what
    crossed."""
    from habitat import rules as habitat_rules
    from historical.rules import VEGETATION_CHANGE_INVESTIGATION_THRESHOLD

    assert habitat_rules.RULE_META["threshold"] is \
        VEGETATION_CHANGE_INVESTIGATION_THRESHOLD


def test_the_habitat_threshold_is_labelled_product_defined(mock_client, live_ndvi):
    """It says when to look, never what was found."""
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))
    body = fetch(mock_client)

    flag = next(f for f in body["radar"]["flags"]
                if f["id"] == "habitat_vegetation_decline")
    meta = flag["rule_meta"]
    assert meta["threshold_type"] == "Contour reporting threshold"
    assert "not a regulatory or scientific standard" in meta["threshold_status"]


def test_habitat_refuses_to_claim_condition(mock_client, live_ndvi):
    """The specific misreading this scanner invites: a spectral index is not a
    condition assessment, and "unfavourable condition" is a defined term
    assessed on the ground."""
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))
    body = fetch(mock_client)

    entry = next(e for e in body["evidence"] if e["factor"] == "ndvi")
    limits = " ".join(entry["claims"]["not_established"]).lower()
    assert "not evidence of habitat deterioration" in limits
    assert "unfavourable condition" in limits
    assert "assessed on the ground" in limits


def test_habitat_states_no_conclusion_about_the_parcel(mock_client, live_ndvi):
    """EM8 in a domain where "this habitat is degraded" is the tempting
    sentence."""
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))
    body = fetch(mock_client)

    prose = repr(body["radar"]).lower() + repr(body["evidence"]).lower()
    for forbidden in ("degraded", "poor condition", "unfavourable status",
                      "habitat quality", "restoration priority"):
        assert forbidden not in prose


# ---------------------------------------------------------------------------
# Informational readings apply no threshold
# ---------------------------------------------------------------------------
def test_informational_readings_carry_no_threshold(mock_client, live_ndvi):
    """Five of habitat's six checks are measurements with no defensible line to
    draw. Inventing one to make a card look actionable is the failure this
    product is built to prevent."""
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.61))          # flat: a reading, no flag
    body = fetch(mock_client)

    for info in body["radar"]["informational"]:
        assert not info.get("threshold"), f"{info['id']} invented a threshold"


def test_an_unassessable_topic_reports_not_assessed(mock_client, live_ndvi):
    """`ndmi`, `evi`, cover and water are not in this request, so their topics
    must say so rather than come back clear."""
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))
    body = fetch(mock_client, factors=["ndvi"])

    states = {t["id"]: t["state"] for t in body["radar"]["topics"]}
    for tid in ("moisture", "structure", "cover", "water"):
        assert states[tid] == "not_assessed", f"{tid} is {states[tid]}"


def test_generated_habitat_data_produces_no_finding(mock_client):
    """EM1–EM3 in the second scanner. With no live NDVI installed the generator
    stands in, and a fabricated habitat trend is exactly as dangerous as a
    fabricated land one."""
    body = fetch(mock_client)
    assert body["series"]["ndvi"]["source"] == "generated"
    assert "habitat_vegetation_decline" not in {f["id"] for f in body["radar"]["flags"]}


# ---------------------------------------------------------------------------
# Invariants, in the second scanner
# ---------------------------------------------------------------------------
def test_no_score_reaches_a_habitat_payload(mock_client, live_ndvi):
    """EM7 is a property of the engine, so it holds for scanner #2 without
    anything being added."""
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))
    body = fetch(mock_client)

    blob = repr(body["radar"]).lower() + repr(body["workspace"]).lower()
    for banned in ("'score'", "'rating'", "'grade'", "'suitability'", "'overall'"):
        assert banned not in blob


def test_em12_composes_habitat_specific_limits_with_generic_ones(mock_client, live_ndvi):
    """The state-generic boundary and the rule's own negative, layered."""
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))
    body = fetch(mock_client)

    limits = next(e for e in body["evidence"]
                  if e["factor"] == "ndvi")["claims"]["not_established"]
    # Habitat's own.
    assert any("habitat deterioration" in c for c in limits)
    # The state-generic ones, unchanged.
    assert any("does not establish why the change occurred" in c for c in limits)
    assert any("not a regulatory determination" in c for c in limits)


def test_a_habitat_request_leaves_land_untouched(mock_client, live_ndvi):
    """Isolation, with a *built* second scanner rather than an empty one —
    which is the version of this test that could actually fail."""
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))

    def land():
        r = mock_client.post("/api/series", json={
            "geometry": GEOMETRY, "factor_ids": ["ndvi"], "scanner": "land"})
        assert r.status_code == 200
        return r.json()

    before = land()
    fetch(mock_client)                       # a full habitat assessment
    after = land()

    assert before["radar"]["topics"] == after["radar"]["topics"]
    assert [f["id"] for f in before["radar"]["flags"]] == \
           [f["id"] for f in after["radar"]["flags"]]
    # Land still raises its own rule, not habitat's.
    assert "historical_vegetation_decline" in {f["id"] for f in after["radar"]["flags"]}
    assert "habitat_vegetation_decline" not in {f["id"] for f in after["radar"]["flags"]}


def test_habitat_cannot_request_a_land_factor(mock_client):
    """A scanner sees only its own factors. Asking habitat for flood zones is
    asking the wrong scanner, and the message says so."""
    r = mock_client.post("/api/series", json={
        "geometry": GEOMETRY, "factor_ids": ["flood_zone3_pct"],
        "scanner": "habitat"})
    assert r.status_code == 422
    # Named by the scanner that actually served the request. `habitat` is an
    # alias for Ecology now, and a message naming the alias would send someone
    # looking for a scanner the catalogue does not list.
    assert "Ecology scanner does not cover" in r.json()["detail"]


def test_a_flagging_rule_declares_its_threshold_where_radar_reads_it():
    """A contract detail that fails silently, found by running the chain.

    `radar.py:998` reads `found["evidence"]["threshold"]` and ignores a
    top-level key. The habitat rule declared it at the top level, so the
    threshold vanished and the flag reached the investigation workspace with no
    threshold at all — no error, no empty string, just a missing step in the
    evidence chain a professional is meant to check.
    """
    from habitat.rules import _condition_change

    def insufficient(why):
        return radar.Insufficient(why)

    per_year = ({y: 0.61 for y in range(2017, 2020)}
                | {y: 0.54 for y in range(2020, 2023)}
                | {y: 0.47 for y in range(2023, 2026)})
    series = {"ndvi": {
        "source": "earth-engine",
        "points": [{"t": f"{y}-{m:02d}", "value": v, "interpolated": False,
                    "valid_fraction": 0.95}
                   for y, v in per_year.items() for m in (4, 5, 6, 7, 8, 9)],
    }}

    found = _condition_change(series, insufficient)
    assert found, "the fixture must raise the habitat flag"
    assert found["evidence"]["threshold"], (
        "a flagging rule must declare its threshold inside `evidence`, which "
        "is where radar reads it")
