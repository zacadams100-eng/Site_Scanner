"""
The Site Investigation Brief.

The artefact that leaves the product, which makes it the one place where every
invariant has to hold at once and where nobody is present to explain it. A
screen can be clarified in conversation; a document cannot.

The tests are grouped by what would make the Brief *dishonest* rather than by
what would make it incomplete, because an incomplete brief is obvious to its
reader and a dishonest one is not.
"""

import pytest

import brief

GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[
        [-0.58, 51.235], [-0.56, 51.235], [-0.56, 51.245],
        [-0.58, 51.245], [-0.58, 51.235],
    ]],
}


def fetch(client, factor_ids=("ndvi",), name="Manor Farm, parcel 3"):
    r = client.post("/api/brief", json={
        "geometry": GEOMETRY, "factor_ids": list(factor_ids), "site_name": name,
    })
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Order is an editorial decision, and it is the one this module owns
# ---------------------------------------------------------------------------
def test_coverage_is_stated_before_any_finding(mock_client):
    """The load-bearing ordering choice.

    A reader who meets "1 flagged" before learning that 23 factors could not be
    assessed has already formed a view of the site, and no later section
    recovers that. In a document there is no tab to click — the order *is* the
    argument.
    """
    body = fetch(mock_client)
    order = body["sections"]
    assert order.index("coverage") < order.index("findings")
    assert order.index("coverage") < order.index("historical")


def test_the_brief_carries_its_own_terms(mock_client):
    """It travels away from the app, so it cannot rely on a principle shown in
    a corner of a screen the recipient never saw."""
    body = fetch(mock_client)
    assert "A clear result means we checked" in body["principle"]
    assert body["methodology"]["limits"]


# ---------------------------------------------------------------------------
# The claim boundary survives the trip
# ---------------------------------------------------------------------------
def test_every_finding_states_what_it_does_not_establish(mock_client, live_ndvi):
    """The candidate EM12, enforced here first.

    This is the surface where the limitation matters most: the reader is a
    professional being asked to quote for a survey, and the gap between
    "vegetation declined 23%" and "ecological degradation" is the difference
    between a scoping question and a diagnosis they did not make.
    """
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))
    body = fetch(mock_client)

    assert body["findings"], "the fixture must produce a flagged finding"
    for f in body["findings"]:
        assert f["not_established"], f"{f['factor']} has no limitation"
        assert all(c.strip() for c in f["not_established"])
        assert f["established"]


def test_the_brief_does_not_rewrite_the_explorer_s_wording(mock_client, live_ndvi):
    """One interpretation, viewed several ways.

    The Brief takes `claims` verbatim from `evidence.py`. Recomposing them here
    would produce two wordings of the same limitation, and the first time they
    disagreed the disagreement would be invisible — each would look correct on
    its own screen.
    """
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))

    r = mock_client.post("/api/series", json={
        "geometry": GEOMETRY, "factor_ids": ["ndvi"]})
    explorer = next(e for e in r.json()["evidence"] if e["factor"] == "ndvi")
    brief_finding = next(f for f in fetch(mock_client)["findings"]
                         if f["factor"] == "ndvi")

    assert brief_finding["not_established"] == explorer["claims"]["not_established"]
    assert brief_finding["established"] == explorer["claims"]["established"]


def test_informational_evidence_has_a_home_of_its_own(mock_client, live_ndvi):
    """Measured, and deliberately not judged.

    The roadmap's answer for LST and built surface is that they stay
    informational until there is a defensible basis for a threshold. That is
    only honest if the Brief has somewhere to put an unjudged measurement —
    otherwise the pressure to invent a threshold comes straight back, this time
    to fill a page.
    """
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.61))
    body = fetch(mock_client)

    for item in body["informational"]:
        assert item["not_established"], "an unjudged reading still states its limits"


# ---------------------------------------------------------------------------
# Gaps are evidence, not omissions
# ---------------------------------------------------------------------------
def test_gaps_are_grouped_by_cause_not_collapsed(mock_client):
    """Three causes, three fixes, three owners. "23 not assessed" tells the
    recipient nothing they can act on."""
    body = fetch(mock_client)
    reasons = {g["reason"] for g in body["gaps"]}
    assert reasons, "a mostly-generated catalogue must produce gaps"
    assert reasons <= {"not_selected", "demo_data", "no_data", "unknown"}

    for gap in body["gaps"]:
        assert gap["label"], "a cause without words is a code in a document"
        assert gap["count"] == len(gap["factors"])


def test_no_live_source_and_not_loaded_read_differently(mock_client):
    body = fetch(mock_client)
    by_reason = {g["reason"]: g for g in body["gaps"]}
    if "not_selected" in by_reason and "demo_data" in by_reason:
        assert by_reason["not_selected"]["label"] != by_reason["demo_data"]["label"]
        assert "demo data" in by_reason["demo_data"]["label"].lower()


def test_the_partition_that_actually_holds_is_the_one_reported(mock_client):
    """`assessed + not_assessed = relevant`.

    The four finding states are *not* a partition — `flagged` and
    `informational` are independent factor sets and one factor can be in both.
    A document that prints four numbers a careful reader can add is a document
    that will be found wrong by a careful reader.
    """
    cov = fetch(mock_client)["coverage"]
    assert cov["assessed"] + cov["not_assessed"] == cov["relevant"]
    assert cov["not_loaded"] + cov["no_live_source"] <= cov["not_assessed"]


def test_coverage_carries_its_note(mock_client):
    """Coverage is how much we could look at, never how good the site is — and
    the sentence saying so ships in the payload rather than the stylesheet."""
    assert "not how good the site is" in fetch(mock_client)["coverage"]["note"]


# ---------------------------------------------------------------------------
# The invariants, on the artefact that leaves the building
# ---------------------------------------------------------------------------
def test_the_brief_contains_no_score(mock_client, live_ndvi):
    """EM7 where it matters most. A document is quoted, screenshotted and
    pasted into decks; a number in it outlives every caveat around it."""
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))
    blob = repr(fetch(mock_client)).lower()

    for banned in ("'score'", "'rating'", "'grade'", "'suitability'",
                   "'overall'", "'health'"):
        assert banned not in blob


def test_the_brief_states_no_conclusion_about_the_site(mock_client, live_ndvi):
    """EM8. It prepares the professional's question; it does not answer it."""
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))
    body = fetch(mock_client)

    prose = " ".join(
        [*(c for f in body["findings"] for c in f["established"]),
         *(c for f in body["findings"] for c in f["not_established"]),
         *(g["label"] for g in body["gaps"])]).lower()

    for forbidden in ("suitable for", "recommend developing", "viable site",
                      "good site", "poor site", "we advise"):
        assert forbidden not in prose


def test_the_assessment_log_is_complete_not_filtered(mock_client):
    """A reader three months later needs to see what was asked for and did not
    arrive, not only what did."""
    body = fetch(mock_client)
    assert len(body["log"]) == body["coverage"]["relevant"]
    assert all(r["name"] for r in body["log"])


def test_attribution_travels_with_the_document(mock_client, live_ndvi):
    """Attribution is a licence condition, not a courtesy.

    It has to be on the artefact that leaves the building rather than on a
    screen the recipient never sees — which is the whole reason the licence
    audit built `attribution` into `catalog.py` in the first place.
    """
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))
    body = fetch(mock_client)

    assert body["methodology"]["attributions"], "a real source must be credited"
    assert any("Copernicus" in a for a in body["methodology"]["attributions"])


def test_a_generated_source_is_never_credited(mock_client):
    """Crediting demo data would assert that a publisher stood behind numbers
    this product invented."""
    body = fetch(mock_client, factor_ids=["ndvi"])
    assert body["methodology"]["attributions"] == [] or all(
        isinstance(a, str) for a in body["methodology"]["attributions"])
    # With no live factor installed, nothing has been observed to credit.
    assert not any("demo" in a.lower() for a in body["methodology"]["attributions"])


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
def test_the_brief_never_invents_a_place_name(mock_client):
    """A drawn shape carries no county. The header states coordinates."""
    site = fetch(mock_client)["site"]
    assert site["name"] == "Manor Farm, parcel 3"
    assert set(site["centroid"]) == {"lng", "lat"}
    assert "county" not in site and "region" not in site


def test_an_unnamed_site_is_not_left_blank(mock_client):
    assert fetch(mock_client, name="")["site"]["name"] == "Untitled site"


def test_build_is_a_pure_read_over_one_payload():
    """It takes the whole response rather than its parts, so a caller cannot
    assemble a Brief whose coverage and findings came from different
    assessments — internally consistent, and wrong."""
    empty = brief.build({}, site_name="Nowhere")
    assert empty["site"]["name"] == "Nowhere"
    assert empty["findings"] == []
    assert empty["coverage"]["relevant"] == 0
    assert empty["sections"] == list(brief.SECTIONS)
