"""
The three-scanner experiment.

**This is a measurement, not a feature.** It answers one question with code
rather than opinion:

    If we introduced a second and third scanner, how much of the existing
    platform could remain completely unchanged?

It does that by running a **coastal** scanner and a **habitat** scanner through
the existing engine — `radar.assess` → `evidence.report` →
`investigation.report` → `brief.build` — with nothing supplied but
configuration: a topic vocabulary, a rule set and a factor series. No new
module, no branch, no scanner class.

Deliberately not a real scanner. The rules here are two lines each and the
thresholds are invented, because inventing a defensible coastal threshold is a
product decision and this file is not the place for one. What is being measured
is whether the *plumbing* carries a domain it has never seen — not whether the
domain is well modelled.

If these tests pass, the platform hypothesis holds at the engine layer and the
remaining seams are the ones named in `docs/MULTI_SCANNER_AUDIT.md`. If they
fail, the failure names the assumption.
"""

import brief
import evidence
import investigation
import radar


# ---------------------------------------------------------------------------
# Scanner 2 — coastal. A vocabulary and two rules, nothing else.
# ---------------------------------------------------------------------------
COASTAL_TOPICS = {
    "shoreline": "Shoreline",
    "inundation": "Inundation",
    "sediment": "Sediment supply",
}

HABITAT_TOPICS = {
    "condition": "Habitat condition",
    "connectivity": "Connectivity",
    "hydrology": "Hydrological context",
}


def _series(value, *, source="earth-engine", name="Mean high water position"):
    """A factor in the shape the engine reads. Identical for every domain —
    which is the first thing this experiment measures."""
    return {
        "source": source,
        "meta": {"name": name},
        "provenance": {"source": "Copernicus / ESA",
                       "endpoint": "earthengine.googleapis.com",
                       "status": "verified"},
        "points": [{"t": "2025-06", "value": value, "valid_fraction": 0.95,
                    "interpolated": False}],
        "annual": [{"year": 2025, "value": value, "months_observed": 12,
                    "months_total": 12}],
    }


def coastal_rules(Rule, Insufficient):
    """Two rules in a domain the repository does not implement.

    Thresholds are invented for the experiment and would be a product decision
    in a real scanner — which is exactly why no real coastal scanner is being
    built here.
    """
    def retreat(series):
        s = series.get("shoreline_position")
        v = (s or {}).get("points", [{}])[-1].get("value")
        if v is None:
            return None
        if v <= -10:
            return {"text": f"Mean high water has retreated {abs(v):.0f} m "
                            "relative to the baseline survey.",
                    "severity": "high",
                    "evidence": {"retreat_m": v},
                    "threshold": "10 m retreat (experiment threshold)"}
        return None

    return [
        Rule(id="shoreline_retreat", topic="shoreline",
             needs=["shoreline_position"], test=retreat,
             investigations=["coastal_process_study"],
             asks="whether the shoreline has retreated",
             meta={"rule": "Shoreline retreat",
                   "threshold_display": "≥ 10 m retreat",
                   "threshold_type": "Experiment threshold",
                   "threshold_status": "invented for an architecture "
                                       "experiment; not a product threshold",
                   "method_version": "coast-x",
                   "not_evidence_of": "It is not evidence of accelerating "
                                      "erosion."}),
        Rule(id="tidal_range_check", topic="inundation",
             needs=["tidal_range"], test=lambda s: None,
             investigations=["coastal_process_study"],
             asks="whether the tidal range supports the observed change"),
    ]


def habitat_rules(Rule, Insufficient):
    def condition(series):
        s = series.get("ndvi")
        v = (s or {}).get("points", [{}])[-1].get("value")
        if v is None:
            return None
        if v <= 0.3:
            return {"text": f"Mean vegetation vigour is {v:.2f} across the "
                            "parcel.",
                    "severity": "medium",
                    "evidence": {"ndvi": v},
                    "threshold": "0.30 (experiment threshold)"}
        return None

    return [
        Rule(id="habitat_condition", topic="condition", needs=["ndvi"],
             test=condition, investigations=["habitat_condition_survey"],
             asks="whether vegetation vigour is low across the parcel",
             meta={"rule": "Habitat condition",
                   "threshold_display": "≤ 0.30",
                   "threshold_type": "Experiment threshold",
                   "threshold_status": "invented for an architecture experiment",
                   "method_version": "hab-x"}),
    ]


# The investigations a scanner names. Injected the same way today's are read —
# see the note in the audit about this being the one seam still global.
EXTRA_INVESTIGATIONS = {
    "coastal_process_study": {
        "name": "Coastal process study",
        "blurb": "Sediment transport, wave climate and the retreat record.",
        "next_step": "Commission a coastal process study covering the frontage.",
    },
    "habitat_condition_survey": {
        "name": "Habitat condition survey",
        "blurb": "Condition assessment against the relevant habitat criteria.",
        "next_step": "Instruct a habitat condition survey, in season.",
    },
}


def _with_investigations(monkeypatch):
    merged = {**radar.INVESTIGATIONS, **EXTRA_INVESTIGATIONS}
    monkeypatch.setattr(radar, "INVESTIGATIONS", merged)


# ---------------------------------------------------------------------------
# The measurement
# ---------------------------------------------------------------------------
def test_a_coastal_scanner_runs_on_the_existing_engine(monkeypatch):
    """Scanner 2, through `radar.assess`, with only configuration supplied."""
    _with_investigations(monkeypatch)
    rules = coastal_rules(radar.Rule, radar.Insufficient)

    result = radar.assess(
        {"series": {"shoreline_position": _series(-14.0)}},
        real_capable={"shoreline_position"},
        topic_names=COASTAL_TOPICS,
        rules=rules,
    )

    # The engine produced a coastal radar without knowing what a shoreline is.
    assert {t["id"] for t in result["topics"]} == set(COASTAL_TOPICS)
    assert "shoreline_retreat" in {f["id"] for f in result["flags"]}

    shoreline = next(t for t in result["topics"] if t["id"] == "shoreline")
    assert shoreline["state"] == "flagged"

    # And the states the whole product rests on still behave: the second rule
    # could not run, so its topic is not assessed rather than clear.
    inundation = next(t for t in result["topics"] if t["id"] == "inundation")
    assert inundation["state"] == "not_assessed"


def test_the_coastal_flag_raises_a_coastal_investigation(monkeypatch):
    _with_investigations(monkeypatch)
    result = radar.assess(
        {"series": {"shoreline_position": _series(-14.0)}},
        real_capable={"shoreline_position"},
        topic_names=COASTAL_TOPICS,
        rules=coastal_rules(radar.Rule, radar.Insufficient),
    )
    raised = [i for i in result["investigations"] if i["id"] == "coastal_process_study"]
    assert raised and raised[0]["name"] == "Coastal process study"


def test_the_whole_downstream_chain_carries_a_second_scanner(monkeypatch):
    """The real measurement: radar → evidence → investigation → brief, with no
    module changed and no branch taken."""
    _with_investigations(monkeypatch)
    series = {"shoreline_position": _series(-14.0)}
    result = radar.assess({"series": series}, real_capable={"shoreline_position"},
                          topic_names=COASTAL_TOPICS,
                          rules=coastal_rules(radar.Rule, radar.Insufficient))

    entries = evidence.report(result, series)
    assert entries, "the evidence explorer must cover a coastal factor"
    shoreline = next(e for e in entries if e["factor"] == "shoreline_position")
    assert shoreline["state"] == "flagged"
    # EM12 holds in a domain the clause vocabulary was never written for.
    assert shoreline["claims"]["not_established"]
    assert any("accelerating erosion" in c
               for c in shoreline["claims"]["not_established"])

    work = investigation.report(result, entries)
    entry = investigation.find(work, "coastal_process_study")
    assert entry and entry["raised_by"][0]["rule"] == "Shoreline retreat"
    assert entry["chains"], "the evidence chain assembles for a coastal rule"

    doc = brief.build({"radar": result, "evidence": entries,
                       "area_ha": 12.0, "centroid": {"lng": 0.9, "lat": 51.4}},
                      site_name="Frontage, section 4")
    assert doc["findings"], "the brief carries a coastal finding"
    assert doc["findings"][0]["not_established"]
    assert doc["coverage"]["relevant"] > 0


def test_a_habitat_scanner_runs_on_the_same_engine(monkeypatch):
    """Scanner 3, to prove the second was not a coincidence of one shape."""
    _with_investigations(monkeypatch)
    result = radar.assess(
        {"series": {"ndvi": _series(0.21, name="NDVI (vegetation vigour)")}},
        real_capable={"ndvi"},
        topic_names=HABITAT_TOPICS,
        rules=habitat_rules(radar.Rule, radar.Insufficient),
    )
    assert {t["id"] for t in result["topics"]} == set(HABITAT_TOPICS)
    assert "habitat_condition" in {f["id"] for f in result["flags"]}
    assert any(i["id"] == "habitat_condition_survey"
               for i in result["investigations"])


def test_two_scanners_do_not_leak_into_each_other(monkeypatch):
    """Each assessment sees only its own vocabulary. Shared module state would
    show up here as a coastal topic in a habitat radar."""
    _with_investigations(monkeypatch)
    coastal = radar.assess(
        {"series": {"shoreline_position": _series(-14.0)}},
        topic_names=COASTAL_TOPICS,
        rules=coastal_rules(radar.Rule, radar.Insufficient))
    habitat = radar.assess(
        {"series": {"ndvi": _series(0.21)}},
        topic_names=HABITAT_TOPICS,
        rules=habitat_rules(radar.Rule, radar.Insufficient))

    assert {t["id"] for t in coastal["topics"]}.isdisjoint(
        {t["id"] for t in habitat["topics"]})


def test_the_default_scanner_is_unchanged_by_the_seam():
    """The land scanner must behave exactly as before when nothing is
    injected — the whole point of a default."""
    plain = radar.assess({"series": {}})
    assert {t["id"] for t in plain["topics"]} == set(radar.TOPICS)
    assert plain["principle"] and plain["limits"]


def test_no_score_appears_in_a_second_scanner(monkeypatch):
    """EM7 is a property of the engine, so it must hold for a domain the
    engine has never seen."""
    _with_investigations(monkeypatch)
    result = radar.assess(
        {"series": {"shoreline_position": _series(-14.0)}},
        topic_names=COASTAL_TOPICS,
        rules=coastal_rules(radar.Rule, radar.Insufficient))

    blob = repr(result).lower()
    for banned in ("'score'", "'rating'", "'grade'", "'suitability'", "'overall'"):
        assert banned not in blob
