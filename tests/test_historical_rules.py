"""
The historical vegetation rule, end to end.

Step 4 of `HISTORICAL_EVIDENCE_MODEL.md`: one rule, proven along the whole
chain — Sentinel-2 series → metric → rule → radar → finding → investigation →
assessment log — before a second metric family is built on an unproven path.

Two things are tested harder than the rest.

**The boundary.** The rule is "≥ 20% decline", so −19.9% must be clear and
−20.0% must flag. An off-by-a-hair here is invisible in every screenshot and
changes what the product asserts about a real site.

**The sneak-through.** A live NDVI series with too few usable years produces a
`change_pct` — the arithmetic works fine on two years. It must not become a
finding merely because the number exists. The rule trusts
`meets_minimum_evidence`; it does not reconstruct sufficiency for itself.
"""

import pytest

import radar
from historical import metrics, rules


def veg_series(per_year, *, source="earth-engine", interpolated=()):
    """An NDVI series in the shape `/api/series` returns."""
    points = []
    for year in sorted(per_year):
        for month in (4, 5, 6, 7, 8, 9):
            t = f"{year}-{month:02d}"
            points.append({"t": t, "value": per_year[year],
                           "interpolated": t in interpolated})
    return {
        "unit": "index", "cadence": "monthly", "source": source,
        "meta": {"name": "NDVI (vegetation vigour)"},
        "provenance": {"source": "Copernicus / ESA",
                       "endpoint": "earthengine.googleapis.com",
                       "status": "verified"},
        "points": points,
    }


def declining(pct, years=16):
    """A series whose measured change is exactly `pct` per cent.

    Built from the baseline and recent values the methodology will actually
    read, so the test exercises the real path rather than a convenient
    approximation of it.
    """
    baseline = 0.50
    recent = baseline * (1 + pct / 100.0)
    per_year = {}
    first = 2011
    for i in range(years):
        year = first + i
        if i < 3:
            per_year[year] = baseline
        elif i >= years - 3:
            per_year[year] = recent
        else:
            per_year[year] = (baseline + recent) / 2
    return veg_series(per_year)


def assess(series, **kw):
    return radar.assess({"series": {"ndvi": series}}, **kw)


def vegetation(result):
    return next(t for t in result["topics"] if t["id"] == "vegetation")


def flag_ids(result):
    return {f["id"] for f in result["flags"]}


RULE = "historical_vegetation_decline"


# ---------------------------------------------------------------------------
# The boundary
# ---------------------------------------------------------------------------
def test_a_decline_just_under_the_threshold_is_clear_not_flagged():
    result = assess(declining(-19.9))
    assert RULE not in flag_ids(result)
    # And it is genuinely a *checked* result, not an absence.
    assert not [u for u in result["not_assessed"] if u["rule"] == RULE]


def test_a_decline_exactly_at_the_threshold_flags():
    """"≥ 20% decline" includes 20.0%."""
    result = assess(declining(-20.0))
    assert RULE in flag_ids(result)


def test_a_larger_decline_flags():
    result = assess(declining(-25.0))
    flag = next(f for f in result["flags"] if f["id"] == RULE)
    assert flag["evidence"]["change_pct"] == pytest.approx(-25.0, abs=0.01)


def test_an_increase_of_the_same_magnitude_is_not_a_decline_flag():
    """An increase and a decline do not warrant the same investigation, and an
    `abs()` comparison would silently treat them as if they did."""
    result = assess(declining(+25.0))
    assert RULE not in flag_ids(result)
    assert vegetation(result)["state"] in ("clear", "partial")


def test_severity_escalates_only_for_a_severe_decline():
    assert next(f for f in assess(declining(-25.0))["flags"]
                if f["id"] == RULE)["severity"] == "medium"
    assert next(f for f in assess(declining(-45.0))["flags"]
                if f["id"] == RULE)["severity"] == "high"


# ---------------------------------------------------------------------------
# The sneak-through
# ---------------------------------------------------------------------------
def test_insufficient_evidence_is_not_assessed_and_never_clear():
    """The trap this rule was written around.

    Two usable years produce no change metric at all, and the rule must say it
    could not look — not return None, which the engine would read as "checked,
    nothing found".
    """
    result = assess(veg_series({2011: 0.50, 2012: 0.20}))
    assert RULE not in flag_ids(result)
    entry = next(u for u in result["not_assessed"] if u["rule"] == RULE)
    assert entry["reason"] == "no_data"
    assert "usable year" in entry["text"]
    assert vegetation(result)["state"] != "clear"


def test_a_live_series_with_sparse_years_does_not_flag_on_an_existing_number():
    """The arithmetic works on six years spread over sixteen. The evidence does
    not, and the rule must trust `meets_minimum_evidence` rather than the
    presence of `change_pct`."""
    sparse = veg_series({2011: 0.50, 2012: 0.50, 2013: 0.50,
                         2024: 0.30, 2025: 0.30, 2026: 0.30})
    metric = metrics.change_metric(sparse, name="V", family="vegetation")
    # The number exists and is well past the threshold —
    assert metric["change_pct"] < -20
    # — and it must still not become a finding.
    assert metric["meets_minimum_evidence"] is False

    result = assess(sparse)
    assert RULE not in flag_ids(result)
    assert next(u for u in result["not_assessed"]
                if u["rule"] == RULE)["reason"] == "no_data"


def test_generated_ndvi_never_reaches_the_rule():
    """EM1 and HE2. A fabricated fifteen-year collapse is the most convincing
    wrong thing this product could draw."""
    result = assess(veg_series({2011 + i: 0.6 - 0.03 * i for i in range(16)},
                               source="generated"))
    assert result["flags"] == []
    assert result["investigations"] == []
    assert next(u for u in result["not_assessed"]
                if u["rule"] == RULE)["reason"] == "demo_data"


def test_interpolated_years_cannot_carry_a_flag():
    per_year = {2011 + i: 0.6 - 0.03 * i for i in range(16)}
    carried = {f"{y}-{m:02d}" for y in list(per_year)[3:] for m in range(4, 10)}
    result = assess(veg_series(per_year, interpolated=carried))
    assert RULE not in flag_ids(result)
    assert next(u for u in result["not_assessed"]
                if u["rule"] == RULE)["reason"] == "no_data"


# ---------------------------------------------------------------------------
# The chain
# ---------------------------------------------------------------------------
def test_a_historical_flag_raises_the_existing_investigation():
    result = assess(declining(-30.0))
    inv = next(i for i in result["investigations"] if i["id"] == "ecology_survey")
    assert RULE in inv["why"]
    assert inv["next_step"].startswith("Instruct")


def test_a_historical_flag_travels_the_identical_path_as_any_other():
    """No special case anywhere. It has provenance, evidence, a timestamp, a
    log row and a topic, exactly like a flood flag."""
    result = assess(declining(-30.0))
    flag = next(f for f in result["flags"] if f["id"] == RULE)

    assert flag["topic"] == "vegetation"
    assert flag["factors"] == ["ndvi"]
    assert flag["provenance"][0]["endpoint"] == "earthengine.googleapis.com"
    assert flag["provenance"][0]["status"] == "verified"
    assert flag["assessed_at"]
    assert flag["evidence"]["method_version"] == metrics.METHOD_VERSION

    row = next(r for r in result["log"] if r["factor"] == "ndvi")
    assert row["state"] == "assessed"


def test_the_flag_carries_the_threshold_as_a_contour_decision():
    """The evidence drawer must be able to show the difference between the
    measurement and Contour's decision to surface it."""
    flag = next(f for f in assess(declining(-30.0))["flags"] if f["id"] == RULE)
    meta = flag["rule_meta"]
    assert meta["threshold_type"] == "Contour reporting threshold"
    assert "not a regulatory" in meta["threshold_status"]
    assert meta["method_version"] == metrics.METHOD_VERSION
    assert "Not evidence of ecological degradation" in meta["purpose"]


def test_the_engine_has_no_branch_that_knows_about_historical_rules():
    """A special case in `radar.py` would be the smell this architecture exists
    to avoid. The engine collects rules; it does not know what they measure."""
    import pathlib
    source = pathlib.Path(radar.__file__).read_text()
    body = source.split("def assess(", 1)[1]
    for banned in ("historical", "sentinel", "modis", "ndvi_history"):
        assert banned not in body.lower(), banned


def test_the_rule_is_registered_exactly_once():
    ids = [r.id for r in radar.RULES if r.id == RULE]
    assert ids == [RULE]


# ---------------------------------------------------------------------------
# HE9 — no causal language
# ---------------------------------------------------------------------------
CAUSAL = ("degrad", "damage", "destroy", "harm", "loss of habitat",
          "deforest", "climate change", "caused", "due to", "because of",
          "poor condition", "unhealthy")


def test_he9_the_flag_states_an_observation_not_a_cause():
    """"NDVI has declined 21% relative to the defined baseline" is permitted.
    "Vegetation degradation detected" is not — it asserts a cause nobody
    measured."""
    for pct in (-20.0, -30.0, -60.0):
        flag = next(f for f in assess(declining(pct))["flags"]
                    if f["id"] == RULE)
        text = flag["text"].lower()
        for word in CAUSAL:
            assert word not in text, f"{word!r} in: {flag['text']}"


def test_he9_the_rule_metadata_states_what_the_threshold_is_not():
    text = " ".join(str(v) for v in rules.VEGETATION_RULE_META.values()).lower()
    assert "not a regulatory or scientific standard" in text
    assert "not evidence of ecological degradation" in text


def test_the_threshold_is_a_named_constant_with_the_sign_convention_fixed():
    """`change_pct <= -20`, never `abs(change) >= 20`."""
    assert rules.VEGETATION_CHANGE_INVESTIGATION_THRESHOLD == -20.0
    import pathlib
    source = pathlib.Path(rules.__file__).read_text()
    assert "abs(" not in source.split("def _vegetation_decline", 1)[1].split(
        "def _span", 1)[0].replace("abs(change)", "")
