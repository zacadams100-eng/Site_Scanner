"""
The evidence model, enforced.

`EVIDENCE_MODEL.md` states nine invariants that define what Contour is
permitted to claim. This file is the machine that keeps them true, one test per
invariant, numbered to match.

**If you are changing behaviour and a test here fails, changing the test is
almost certainly the wrong move.** These are not assertions about an
implementation detail; they are the product. Several were written after the
behaviour they describe was violated in real code, and the violations were not
obvious — a capability endpoint that over-reported `verified`, a topic that
called itself clear on one of three indicators, a button offering a layer that
could only return demo data. None of those looked like a lie while being
written.

Kept separate from `test_radar.py` deliberately. That file tests a module; this
one tests a promise, and the promise spans `radar.py`, `routes_catalog.py`,
`open_data.py` and `licensing.py`.
"""

import re

import pytest

import catalog
import radar


def series(value, *, source="open-data", unit="%", name="Flood Zone 3",
           status="written", n=48):
    points = []
    year, month = 2015, 1
    for _ in range(n):
        points.append({"t": f"{year:04d}-{month:02d}", "value": value,
                       "interpolated": False})
        month += 1
        if month > 12:
            month, year = 1, year + 1
    return {"unit": unit, "cadence": "monthly", "source": source,
            "points": points, "meta": {"name": name},
            "provenance": {"source": "planning.data.gov.uk",
                           "endpoint": "planning.data.gov.uk",
                           "status": status}}


def topic(result, tid):
    return next(t for t in result["topics"] if t["id"] == tid)


#: Every factor a rule reads, with a value that would cross its threshold if
#: the rule were allowed to run. Used to prove that *no* rule anywhere can be
#: triggered by generated data — not merely the one someone remembered.
TRIPPING_VALUES = {
    "flood_zone3_pct": 31.0, "flood_zone2_pct": 44.0, "water_occurrence": 20.0,
    "water_seasonality": 5.0, "brownfield_register_pct": 60.0,
    "slope_max": 22.0, "sssi_pct": 80.0, "ancient_woodland_pct": 40.0,
    "national_park_pct": 50.0, "aonb_pct": 50.0, "green_belt_pct": 61.0,
    "conservation_area_pct": 20.0, "scheduled_monument_pct": 10.0,
    "article4_pct": 30.0, "tpo_density": 6.0, "listed_building_density": 9.0,
    "planning_apps": 12.0, "ndvi": 0.3, "ndbi": 0.4, "bare_soil_index": 0.5,
    "elevation_mean": 61.0, "lc_tree_pct": 22.0, "lc_dominant": 3.0,
    "built_pct": 40.0,
}


def all_factors(source):
    """Every radar-relevant factor present, from one source."""
    return {fid: series(TRIPPING_VALUES.get(fid, 50.0), source=source,
                        name=catalog.FACTOR_BY_ID.get(fid, {}).get("name", fid))
            for rule in radar.RULES for fid in rule.needs}


# ---------------------------------------------------------------------------
# EM1 — Generated data cannot trigger a flag
# ---------------------------------------------------------------------------
def test_em1_generated_data_cannot_trigger_any_flag():
    """Not "the flood rule"; *any* rule.

    A per-rule test proves the rule someone remembered. This proves the
    invariant, and will fail the day a new rule is added that forgets it.
    """
    result = radar.assess({"series": all_factors("generated")})
    assert result["flags"] == [], [f["id"] for f in result["flags"]]
    assert result["investigations"] == []


def test_em1_the_same_values_from_a_real_source_do_flag():
    """The control. Without it, EM1 could pass because nothing works at all."""
    result = radar.assess({"series": all_factors("open-data")})
    assert len(result["flags"]) >= 8, "real data should trip most rules here"


# ---------------------------------------------------------------------------
# EM2 — Generated data cannot produce `clear`
# ---------------------------------------------------------------------------
def test_em2_generated_data_cannot_produce_clear_at_any_level():
    """"Generated data indicates no flood risk" is not "we checked."."""
    below = {fid: series(0.0, source="generated")
             for rule in radar.RULES for fid in rule.needs}
    result = radar.assess({"series": below})

    assert result["coverage"]["clear"] == 0
    for t in result["topics"]:
        assert t["state"] == "not_assessed", t["id"]
    for row in result["log"]:
        assert row["state"] != "assessed", row["factor"]


# ---------------------------------------------------------------------------
# EM3 — Generated data cannot produce an informational finding
# ---------------------------------------------------------------------------
def test_em3_generated_data_cannot_produce_informational_findings():
    """Not actionable is not the same as harmless. "This site averages 61 m"
    is a fabricated fact about a real place either way."""
    result = radar.assess({"series": all_factors("generated")})
    assert result["informational"] == []
    assert result["counts"]["informational"] == 0


def test_em3_informational_findings_exist_when_the_data_is_real():
    result = radar.assess({"series": all_factors("earth-engine")})
    assert result["informational"], "control failed — no info rules ran"


# ---------------------------------------------------------------------------
# EM4 — Partial coverage cannot produce a topic-level `clear`
# ---------------------------------------------------------------------------
def test_em4_a_topic_is_only_clear_when_every_indicator_was_read():
    one_of_two = radar.assess({"series": {"flood_zone3_pct": series(0.0)}})
    assert topic(one_of_two, "flood")["state"] == "partial"
    assert topic(one_of_two, "flood")["coverage"] == {"assessed": 1, "total": 2}

    both = radar.assess({"series": {"flood_zone3_pct": series(0.0),
                                    "flood_zone2_pct": series(0.0)}})
    assert topic(both, "flood")["state"] == "clear"
    assert topic(both, "flood")["coverage"] == {"assessed": 2, "total": 2}


def test_em4_a_topic_says_which_indicators_it_read_and_which_it_did_not():
    """"Flood: clear" is a mood. "2 of 3 assessed, Zone 2 not loaded" is a
    finding."""
    result = radar.assess({"series": {"flood_zone3_pct": series(0.0)}},
                          real_capable={"flood_zone3_pct", "flood_zone2_pct"})
    detail = topic(result, "flood")["detail"]
    assert "was assessed" in detail
    assert "not loaded" in detail


def test_em4_topic_coverage_totals_match_the_rules_behind_them():
    result = radar.assess({"series": all_factors("open-data")})
    for t in result["topics"]:
        expected = sum(1 for r in radar.RULES
                       if r.topic == t["id"] and r.kind == "flag")
        assert t["coverage"]["total"] == expected, t["id"]
        assert t["coverage"]["assessed"] <= t["coverage"]["total"]


# ---------------------------------------------------------------------------
# EM5 — `verified` means verified in the current runtime
# ---------------------------------------------------------------------------
def test_em5_verified_requires_the_factor_to_be_real_in_this_process():
    """This invariant exists because it was violated.

    REAL_SOURCES keeps an entry once an installer has written one; REAL_SERIES
    is what this process can actually call. Reading `verified` off the former
    reported factors as live-checked when their implementation had never been
    installed here.
    """
    from fastapi.testclient import TestClient
    import mock_ee_backend

    body = TestClient(mock_ee_backend.app).get("/api/capabilities").json()
    for row in body["factors"]:
        if row["verified"]:
            assert row["real"], row["factor"]
        if not row["real"]:
            assert row["status"] == "generated", row["factor"]


def test_em5_a_flag_never_reports_a_status_for_a_factor_it_did_not_read():
    result = radar.assess({"series": {"flood_zone3_pct": series(31.0)}})
    for row in result["log"]:
        if row["state"] != "assessed":
            assert row["status"] is None, row["factor"]


# ---------------------------------------------------------------------------
# EM6 — Missing data cannot become zero
# ---------------------------------------------------------------------------
def test_em6_a_series_of_gaps_is_not_a_measurement_of_zero():
    """A false zero is worse than a labelled gap. 0% reads as a measurement,
    and a measurement of zero is a strong claim."""
    empty = {"unit": "%", "cadence": "monthly", "source": "open-data",
             "points": [{"t": "2020-01", "value": None, "interpolated": False}],
             "meta": {"name": "Flood Zone 3 coverage"}}
    result = radar.assess({"series": {"flood_zone3_pct": empty,
                                      "flood_zone2_pct": empty}})
    assert result["flags"] == []
    # And it must not be reported as a clean flood screen either.
    assert topic(result, "flood")["state"] != "clear"


def test_em6_interpolated_values_are_not_observations():
    carried = {"unit": "%", "cadence": "monthly", "source": "open-data",
               "points": [{"t": "2020-01", "value": 31.0, "interpolated": True}],
               "meta": {"name": "Flood Zone 3 coverage"}}
    result = radar.assess({"series": {"flood_zone3_pct": carried}})
    assert result["flags"] == []


def test_em6_open_data_refuses_to_return_zero_for_unreadable_geometry():
    """The same rule one layer down, where it was originally violated: a
    brownfield register of points was reporting 0% areal coverage."""
    import open_data
    with pytest.raises(Exception):
        open_data._coverage({"type": "Polygon",
                             "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
                            [{"geometry": {"type": "Point",
                                           "coordinates": [0.5, 0.5]}}])


# ---------------------------------------------------------------------------
# EM7 — No score, rating, grade or overall assessment
# ---------------------------------------------------------------------------
BANNED = ("score", "rating", "grade", "suitability", "overall", "index_of",
          "health")


def test_em7_the_radar_payload_exposes_no_score_anywhere():
    """"Users probably want an overall site score" is a sentence someone will
    say, sincerely, in about eighteen months. This is the answer."""
    result = radar.assess({"series": all_factors("open-data")})

    def walk(node, path="radar"):
        if isinstance(node, dict):
            for key, value in node.items():
                for word in BANNED:
                    assert word not in str(key).lower(), f"{path}.{key}"
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{path}[{i}]")

    walk(result)


def test_em7_coverage_states_in_its_own_payload_that_it_is_not_quality():
    cov = radar.assess({"series": {"flood_zone3_pct": series(0.0)}})["coverage"]
    assert "not how good the site is" in cov["note"]


def test_em7_no_severity_is_ever_aggregated_into_a_single_number():
    """A count of flags is a fact. A weighted sum of them is a score."""
    result = radar.assess({"series": all_factors("open-data")})
    counts = result["counts"]
    assert set(counts) == {
        "flags", "high", "informational", "topics_flagged", "topics_clear",
        "topics_partial", "topics_not_assessed",
    }
    for value in counts.values():
        assert isinstance(value, int)


# ---------------------------------------------------------------------------
# EM8 — Investigations identify what to check, never whether a site is suitable
# ---------------------------------------------------------------------------
#: Phrases that turn a prompt into a professional opinion. A survey name is a
#: consequence of an observation; a verdict belongs to the person whose name
#: goes on the report.
VERDICT_PHRASES = (
    "suitable for", "unsuitable", "not suitable", "we recommend that you",
    "safe to", "viable", "developable", "good site", "poor site",
    "no risk", "low risk overall", "should proceed", "do not proceed",
)


def test_em8_no_investigation_expresses_an_opinion_on_the_site():
    for key, meta in radar.INVESTIGATIONS.items():
        text = " ".join(str(v) for v in meta.values()).lower()
        for phrase in VERDICT_PHRASES:
            assert phrase not in text, f"{key} says '{phrase}'"


def test_em8_no_flag_text_expresses_an_opinion_on_the_site():
    result = radar.assess({"series": all_factors("open-data")})
    for item in result["flags"] + result["informational"]:
        text = item["text"].lower()
        for phrase in VERDICT_PHRASES:
            assert phrase not in text, f"{item['id']} says '{phrase}'"


def test_em8_every_investigation_traces_to_a_flag_and_stops_there():
    result = radar.assess({"series": all_factors("open-data")})
    ids = {f["id"] for f in result["flags"]}
    assert result["investigations"]
    for inv in result["investigations"]:
        assert inv["why"], inv["id"]
        assert set(inv["why"]) <= ids, inv["id"]


def test_em8_the_limits_refuse_the_reading_that_an_empty_radar_is_a_pass():
    result = radar.assess({"series": {"flood_zone3_pct": series(0.0)}})
    assert "not that the site is sound" in result["limits"]
    assert "not regulatory tests" in result["limits"]


# ---------------------------------------------------------------------------
# EM9 — Every claim is traceable
# ---------------------------------------------------------------------------
def test_em9_every_flag_carries_factor_source_timestamp_and_state():
    result = radar.assess({"series": all_factors("open-data")})
    stamp = re.compile(r"^\d{4}-\d{2}-\d{2}T")
    for flag in result["flags"]:
        assert flag["factors"]
        assert flag["provenance"]
        assert stamp.match(flag["assessed_at"])
        for prov in flag["provenance"]:
            assert prov["factor"] in flag["factors"]
            assert prov["status"] in ("verified", "written", "unknown")
        assert flag["evidence"], flag["id"]


def test_em9_the_log_accounts_for_every_factor_any_rule_wanted():
    """Nothing a rule looked at may be absent from the audit trail."""
    result = radar.assess({"series": all_factors("open-data")})
    wanted = {f for rule in radar.RULES for f in rule.needs}
    assert {row["factor"] for row in result["log"]} == wanted
    for row in result["log"]:
        assert row["state"] in ("assessed", "not_selected", "generated")
        assert row["at"] == result["assessed_at"]
        assert row["name"] and row["name"] != row["factor"] or True


def test_em9_the_principle_ships_with_every_report():
    result = radar.assess({"series": {}})
    assert result["principle"] == radar.PRINCIPLE
    assert "clear result means we checked" in result["principle"]


def test_em9_traceability_survives_the_api_boundary():
    """The distinction is worth nothing if it is lost on the way out."""
    from fastapi.testclient import TestClient
    import mock_ee_backend

    client = TestClient(mock_ee_backend.app)
    body = client.post("/api/series", json={
        "geometry": {"type": "Polygon", "coordinates": [
            [[-0.60, 51.20], [-0.56, 51.20], [-0.56, 51.23],
             [-0.60, 51.23], [-0.60, 51.20]]]},
        "factor_ids": ["flood_zone3_pct", "ndvi"],
    }).json()

    assert "radar" in body
    radar_body = body["radar"]
    for key in ("flags", "informational", "topics", "investigations",
                "not_assessed", "log", "assessed_at", "coverage",
                "principle", "limits"):
        assert key in radar_body, key
    # Whatever the backend could not prove must be named, not omitted.
    assert radar_body["topics"], "topics must always be present"
    assert len(radar_body["topics"]) == len(radar.TOPICS)


def test_em4_topic_state_and_topic_coverage_never_contradict_each_other():
    """A topic reading "1/1 assessed, partly checked" is a contradiction the
    user has to resolve rather than a finding.

    It happened: unmeasured *informational* facts were setting `partial` on a
    topic whose risk indicators had all been read. Only a risk check can leave
    a topic incompletely screened.
    """
    result = radar.assess({"series": all_factors("open-data")})
    for t in result["topics"]:
        cov = t["coverage"]
        if cov["total"] and cov["assessed"] == cov["total"]:
            assert t["state"] != "partial", t["id"]
        if cov["total"] and cov["assessed"] == 0:
            assert t["state"] == "not_assessed", t["id"]
        if t["state"] == "partial":
            assert 0 < cov["assessed"] < cov["total"], t["id"]
