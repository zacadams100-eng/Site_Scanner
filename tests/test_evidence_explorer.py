"""
The evidence explorer: every state, and the claim boundary on each.

The explorer's value is not that it shows a number's provenance — the radar
already did that. It is the pair of statements at the end of every entry:
**what this establishes** and **what this does not establish**. They are the
difference between

    measurement → diagnosis          (what a reader does by default)
    measurement → investigation      (what Contour actually supports)

so the tests here are mostly about the second sentence. The most important ones
assert what it *refuses* to claim in the states people over-read: `clear`, and
the three flavours of `not_assessed`.
"""

import pytest

import evidence
import radar

GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[
        [-0.58, 51.235], [-0.56, 51.235], [-0.56, 51.245],
        [-0.58, 51.245], [-0.58, 51.235],
    ]],
}


def fetch(client, factor_ids):
    r = client.post("/api/series", json={
        "geometry": GEOMETRY, "factor_ids": factor_ids,
    })
    assert r.status_code == 200, r.text
    return r.json()


def entry(body, factor):
    return next((e for e in body["evidence"] if e["factor"] == factor), None)


# ---------------------------------------------------------------------------
# The boundary exists everywhere, on every path
# ---------------------------------------------------------------------------
def test_every_entry_states_what_it_does_not_establish(mock_client):
    """The invariant the whole feature rests on.

    A claim boundary that goes missing on some path is worse than none at all:
    the reader learns to expect it and reads its absence as "nothing to qualify
    here". So it is asserted across every factor in a mixed report rather than
    on the one state that was convenient to build.
    """
    body = fetch(mock_client, ["ndvi", "lc_tree_pct", "flood_zone3_pct", "elevation_mean"])
    assert body["evidence"], "the explorer must cover the factors the rules wanted"

    for e in body["evidence"]:
        assert e["claims"]["not_established"], f"{e['factor']} has no limit"
        assert all(c.strip() for c in e["claims"]["not_established"])
        assert e["claims"]["established"], f"{e['factor']} establishes nothing"
        assert all(c.strip() for c in e["claims"]["established"])


def test_the_explorer_is_contextual_not_a_catalogue(mock_client):
    """273 factors thrown at a user answers "here is our database". The question
    is "why is Contour saying this", and its denominator is this site."""
    body = fetch(mock_client, ["ndvi"])
    assert len(body["evidence"]) < 60
    assert {e["factor"] for e in body["evidence"]} <= set(body["radar"]["log"] and
                                                          [r["factor"] for r in body["radar"]["log"]])


# ---------------------------------------------------------------------------
# not_assessed — three causes, three different fixes, one shared limit
# ---------------------------------------------------------------------------
def test_generated_evidence_says_it_produces_no_findings(mock_client):
    """The distinction this project spent the most effort engineering, finally
    visible to the user rather than implied by a badge."""
    body = fetch(mock_client, ["ndvi"])
    demo = [e for e in body["evidence"]
            if e["state"] == "not_assessed" and e["reason"] == "demo_data"]
    assert demo, "a mostly-generated catalogue must produce demo_data entries"

    e = demo[0]
    assert "demo data" in " ".join(e["claims"]["established"]).lower()
    assert "never used to produce a finding" in " ".join(e["claims"]["established"])
    assert e["source"]["runtime"] == "generated"


def test_an_unmeasured_factor_is_never_reported_as_absent(mock_client):
    """The most dangerous misreading in the product: unknown is not clear.

    A reader who sees "not assessed" and concludes "so there is no flood risk"
    has inverted the meaning, and this sentence is the only thing standing
    between them and that.
    """
    body = fetch(mock_client, ["ndvi", "flood_zone3_pct"])
    for e in body["evidence"]:
        if e["state"] != "not_assessed":
            continue
        assert "not a finding of absence" in " ".join(e["claims"]["not_established"])
        assert "unknown, not clear" in " ".join(e["claims"]["not_established"])


def test_not_loaded_and_no_live_source_do_not_read_the_same(mock_client):
    """One is a click; the other is a wall. Collapsing them makes a fixable gap
    and a permanent one look like the same problem."""
    body = fetch(mock_client, ["ndvi"])
    by_reason = {}
    for e in body["evidence"]:
        if e["state"] == "not_assessed":
            by_reason.setdefault(e["reason"], e)

    if "not_selected" in by_reason and "demo_data" in by_reason:
        assert (by_reason["not_selected"]["claims"]["established"]
                != by_reason["demo_data"]["claims"]["established"])


# ---------------------------------------------------------------------------
# clear — the state most likely to be quoted as a clean bill of health
# ---------------------------------------------------------------------------
def test_clear_does_not_claim_the_topic_is_safe():
    """`clear` is a statement about one check, not about the site.

    Driven directly rather than over HTTP because a `clear` result needs a real
    factor that no rule flags, and constructing that through the mock backend
    would be an elaborate way to reach a function this module owns.
    """
    claims = evidence._claims("clear", None, findings=[],
                              measurement_text="Slope was assessed.")
    assert "does not establish that the site is free of risk" in " ".join(claims["not_established"])
    assert "other checks in the same topic may not have run" in " ".join(claims["not_established"]).lower()


def test_clear_still_carries_the_regulatory_limit():
    claims = evidence._claims("clear", None, findings=[], measurement_text="")
    assert "not a regulatory determination" in " ".join(claims["not_established"])


# ---------------------------------------------------------------------------
# flagged — the state that must not become a diagnosis
# ---------------------------------------------------------------------------
def test_a_flag_refuses_to_establish_a_cause(mock_client, live_ndvi):
    """HE9 at the point of reading. A 23% decline is exactly where a
    professional's eye completes the sentence with a cause."""
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))
    body = fetch(mock_client, ["ndvi"])

    e = entry(body, "ndvi")
    assert e["state"] == "flagged"
    limits = " ".join(e["claims"]["not_established"])
    assert "does not establish why the change occurred" in limits
    # The rule's own declared negative travels with the claim rather than
    # sitting three screens away in the threshold block.
    assert "ecological degradation" in limits
    assert "not a regulatory determination" in limits


def test_every_finding_on_a_factor_is_shown_not_just_the_strongest(mock_client, live_ndvi):
    """One NDVI series carries a trend flag *and* a historical-baseline flag.

    An earlier version kept only the first, so the explorer showed the trend
    rule and silently dropped the historical one — hiding half the answer to
    the only question this screen exists to answer.
    """
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))
    body = fetch(mock_client, ["ndvi"])

    e = entry(body, "ndvi")
    ids = {f["id"] for f in e["findings"]}
    assert "historical_vegetation_decline" in ids
    assert len(ids) >= 2, "both rules reading this series must be visible"


def test_a_flag_carries_its_rule_and_threshold(mock_client, live_ndvi):
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))
    body = fetch(mock_client, ["ndvi"])

    e = entry(body, "ndvi")
    hist = next(f for f in e["findings"]
                if f["id"] == "historical_vegetation_decline")
    assert hist["threshold"]
    assert hist["rule_meta"]["threshold_type"] == "Contour reporting threshold"


def test_a_flag_names_the_investigation_it_raised(mock_client, live_ndvi):
    """The link that makes the journey Overview → Radar → Explorer →
    Investigation, rather than four disconnected screens."""
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))
    body = fetch(mock_client, ["ndvi"])

    e = entry(body, "ndvi")
    assert e["investigations"], "a flag that raised an investigation must say so"
    assert e["investigations"][0]["name"]


# ---------------------------------------------------------------------------
# informational — harmless-feeling, and therefore bound
# ---------------------------------------------------------------------------
def test_informational_applies_no_threshold_and_says_so(mock_client, live_ndvi):
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.61))   # flat: no flag, but a reading exists
    body = fetch(mock_client, ["ndvi"])

    info = [e for e in body["evidence"] if e["state"] == "informational"]
    if info:
        limits = " ".join(info[0]["claims"]["not_established"])
        assert "No threshold was applied" in limits
        # An informational finding applies no threshold, so it must not carry
        # one — a fake threshold is exactly what this state must not invent.
        assert all(not f["threshold"] for f in info[0]["findings"])


# ---------------------------------------------------------------------------
# Provenance, kept in four separate fields
# ---------------------------------------------------------------------------
def test_publisher_and_endpoint_stay_distinct(mock_client, live_ndvi):
    """HE1. Sentinel-2 reaches this product *through* Earth Engine, which does
    the cloud masking and compositing. A user told only "Copernicus" would look
    for the number in the Copernicus Data Space and find a different one."""
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))
    body = fetch(mock_client, ["ndvi"])

    src = entry(body, "ndvi")["source"]
    assert src["publisher"] == "Copernicus / ESA"
    assert src["endpoint"] == "earthengine.googleapis.com"
    assert src["publisher"] != src["endpoint"]


def test_licence_and_clearance_are_not_the_same_field(mock_client, live_ndvi):
    """"CC BY-SA 3.0 IGO" is a fact about the data. "conditional" is this
    project's own unverified reading of it, and merging them would present an
    opinion as a licence term."""
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))
    body = fetch(mock_client, ["ndvi"])

    src = entry(body, "ndvi")["source"]
    assert src["licence"] == "CC BY-SA 3.0 IGO"
    assert src["clearance"] == "conditional"
    assert src["attribution"]


def test_runtime_verification_reports_this_process(mock_client, live_ndvi):
    """EM5. `verified` means verified in the runtime doing the answering, not
    present in a registry somewhere."""
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))
    body = fetch(mock_client, ["ndvi"])
    assert entry(body, "ndvi")["source"]["runtime"] == "verified"

    # A factor with no live implementation reports `generated`, not `unknown`:
    # its runtime state is known exactly.
    gen = [e for e in body["evidence"] if e["source"]["kind"] == "generated"]
    assert gen and all(e["source"]["runtime"] == "generated" for e in gen)

    # Consistency with the log rather than a demand that some factor be
    # unloaded: how many factors are merely not-loaded versus permanently
    # generated depends on how many real implementations this process has
    # installed, which is not what this test is about.
    by_factor = {r["factor"]: r["state"] for r in body["radar"]["log"]}
    for e in body["evidence"]:
        if by_factor.get(e["factor"]) == "not_selected":
            assert e["source"]["runtime"] == "not_loaded"


def test_never_loaded_is_not_reported_as_demo_data():
    """The mapping itself, driven directly so it cannot go untested.

    A factor that was never loaded has no series entry at all, and an earlier
    version defaulted that missing series to `generated` — telling a user "demo
    data" about something that was simply never fetched. Those are the two
    causes this product works hardest to keep apart, and which of them a given
    report contains depends on what is installed, so the mapping is pinned here
    rather than through a fixture that may not produce both.
    """
    unloaded = evidence._source_block("ndvi", {}, {"state": "not_selected"})
    assert unloaded["runtime"] == "not_loaded"
    assert unloaded["kind"] == "not_loaded"

    generated = evidence._source_block("ndvi", {}, {"state": "generated"})
    assert generated["runtime"] == "generated"
    assert generated["kind"] == "generated"

    assert unloaded["runtime"] != generated["runtime"]


def test_the_explorer_reads_states_and_never_reaches_one(mock_client, live_ndvi):
    """EM11 one layer below the UI. Every state in the explorer must be
    traceable to the engine's own output rather than recomputed here."""
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))
    body = fetch(mock_client, ["ndvi"])

    flagged = {e["factor"] for e in body["evidence"] if e["state"] == "flagged"}
    engine_flagged = {f for flag in body["radar"]["flags"] for f in flag["factors"]}
    assert flagged == engine_flagged

    info = {e["factor"] for e in body["evidence"] if e["state"] == "informational"}
    engine_info = {f for i in body["radar"]["informational"] for f in i["factors"]}
    # An informational factor that is also flagged reports flagged — one state
    # per factor, and the flag is the one that needs acting on.
    assert info == engine_info - engine_flagged


def test_no_score_reaches_the_explorer(mock_client, live_ndvi):
    """EM7, on the screen a reader studies hardest."""
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))
    body = fetch(mock_client, ["ndvi"])

    blob = repr(body["evidence"]).lower()
    for banned in ("'score'", "'rating'", "'grade'", "'suitability'", "'overall'"):
        assert banned not in blob


def test_a_source_that_answered_with_nothing_is_never_clear(mock_client, live_ndvi):
    """EM6, at the explorer layer.

    The trap is specific: the assessment log says NDVI was `assessed` — a real
    service was called and it replied. But every month came back a gap, so the
    rule could not evaluate. Reading only the log state lands on `clear`, which
    claims "we checked and found nothing" about a question that was never
    actually answered. The cause has to come from the rule, because only the
    rule knows the reply held nothing usable.

    This is the same false zero EM6 was written for, one layer up, and it was
    live in this module until the full test suite surfaced it.
    """
    # A series with no usable years at all: real source, real call, no answer.
    live_ndvi({})
    body = fetch(mock_client, ["ndvi"])

    e = entry(body, "ndvi")
    assert e["state"] != "clear", "an empty answer is not a clean result"
    assert e["state"] == "not_assessed"
    assert "not a finding of absence" in " ".join(e["claims"]["not_established"])
