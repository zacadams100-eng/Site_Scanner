"""
The investigation radar.

A flag is judgement-shaped, and people act on conclusions without checking
them. So most of what is tested here is what the radar *refuses* to do: no flag
from generated data, no silent omission of what it could not check, and no
recommendation that cannot be walked back to the number that raised it.

The single most important test in this file is
`test_generated_data_never_raises_a_flag`. If that one ever goes green while
the behaviour is wrong, this module is a liability rather than a feature.
"""

import pytest

import radar


def series(values, *, unit="%", source="open-data", name="Flood Zone 3",
           status="written", publisher="planning.data.gov.uk",
           cadence="monthly", start=(2015, 1)):
    """A series in the shape `/api/series` returns."""
    points, year, month = [], start[0], start[1]
    for v in values:
        points.append({"t": f"{year:04d}-{month:02d}", "value": v,
                       "interpolated": False})
        month += 1
        if month > 12:
            month, year = 1, year + 1
    return {
        "unit": unit, "cadence": cadence, "source": source, "points": points,
        "meta": {"name": name},
        "provenance": {"source": publisher, "endpoint": "planning.data.gov.uk",
                       "status": status},
    }


def const(value, n=48, **kw):
    return series([value] * n, **kw)


def report(**kw):
    return {"series": kw}


def flag_ids(result):
    return {f["id"] for f in result["flags"]}


def topic(result, tid):
    return next(t for t in result["topics"] if t["id"] == tid)


# ---------------------------------------------------------------------------
# The rule that holds the whole feature up
# ---------------------------------------------------------------------------
def test_generated_data_never_raises_a_flag():
    """A demo number must not become a recommendation.

    Same percentage, same rule, only the source differs — and that alone has
    to be the difference between a flag and "not assessed". A caveat protects
    a measurement; it does not protect "commission a flood risk assessment".
    """
    real = radar.assess(report(flood_zone3_pct=const(31.0)))
    assert "flood_zone3" in flag_ids(real)

    fake = radar.assess(report(flood_zone3_pct=const(31.0, source="generated")))
    assert fake["flags"] == []
    assert fake["investigations"] == []
    assert topic(fake, "flood")["state"] == "not_assessed"


def test_generated_data_says_which_factor_and_why():
    result = radar.assess(report(flood_zone3_pct=const(31.0, source="generated")))
    entry = next(u for u in result["not_assessed"] if u["rule"] == "flood_zone3")
    assert entry["reason"] == "demo_data"
    assert entry["factors"] == ["flood_zone3_pct"]
    assert "generated demo data" in entry["text"]


# ---------------------------------------------------------------------------
# Three outcomes, never two
# ---------------------------------------------------------------------------
def test_a_topic_that_was_checked_and_found_nothing_says_clear():
    """The most valuable line in the whole feature.

    "0% of this site is in Flood Zone 3, and we checked" is a real answer.
    Collapsing it into the same silence as "we could not look" throws away the
    only thing that distinguishes a screened site from an unscreened one.

    Both flood checks are loaded, because `clear` means *every* check in the
    topic ran — see test_clear_is_only_produced_where_every_check_in_the_topic_ran.
    """
    result = radar.assess(report(flood_zone3_pct=const(0.0),
                                 flood_zone2_pct=const(0.0)))
    assert result["flags"] == []
    assert topic(result, "flood")["state"] == "clear"


def test_a_topic_nobody_loaded_is_not_assessed_not_clear():
    result = radar.assess(report(ndvi=const(0.6, unit="index",
                                            source="earth-engine")))
    assert topic(result, "flood")["state"] == "not_assessed"
    entry = next(u for u in result["not_assessed"] if u["rule"] == "flood_zone3")
    assert entry["reason"] == "not_selected"
    assert "flood_zone3_pct" in entry["factors"]
    assert "run it again" in entry["text"]


def test_it_never_suggests_adding_a_layer_that_would_come_back_generated():
    """A smaller lie than a false flag, but the same kind.

    Without `real_capable`, a factor that is both unselected and generated
    reports `not_selected` — and the UI offers "add this layer", which leads
    straight to "not assessed — demo data". The button has to know.
    """
    naive = radar.assess(report())
    assert next(u for u in naive["not_assessed"]
                if u["rule"] == "planning_pressure")["reason"] == "not_selected"

    # The server knows `planning_apps` has no real implementation.
    informed = radar.assess(report(), real_capable={"flood_zone3_pct"})
    entry = next(u for u in informed["not_assessed"]
                 if u["rule"] == "planning_pressure")
    assert entry["reason"] == "demo_data"
    # And a factor that *is* real-capable still reads as one click away.
    assert next(u for u in informed["not_assessed"]
                if u["rule"] == "flood_zone3")["reason"] == "not_selected"


def test_a_suggestion_carries_a_readable_name_not_a_column_id():
    result = radar.assess(report(), real_capable={"flood_zone3_pct"})
    entry = next(u for u in result["not_assessed"] if u["rule"] == "flood_zone3")
    assert entry["factor_names"] == ["Flood Zone 3 coverage"]


def test_every_topic_appears_in_every_report():
    """A missing heading is indistinguishable from a clean one."""
    result = radar.assess(report())
    assert {t["id"] for t in result["topics"]} == set(radar.TOPICS)
    assert all(t["state"] == "not_assessed" for t in result["topics"])


def test_terrain_is_honestly_unreachable_today():
    """Every slope factor in the catalogue is generated.

    This is the case the feature was designed around: the radar must name what
    it could not check rather than leaving Terrain off the list. If slope ever
    becomes real this test should be updated, not deleted.
    """
    import catalog
    assert "slope_max" in catalog.FACTOR_BY_ID
    result = radar.assess(report(slope_max=const(22.0, unit="°",
                                                 source="generated")))
    assert topic(result, "terrain")["state"] == "not_assessed"
    entry = next(u for u in result["not_assessed"] if u["rule"] == "steep_ground")
    assert entry["reason"] == "demo_data"
    # And the rule still works the day the data becomes real.
    live = radar.assess(report(slope_max=const(22.0, unit="°",
                                               source="earth-engine")))
    assert "steep_ground" in flag_ids(live)


def test_one_clear_check_never_hides_a_flag():
    result = radar.assess(report(
        flood_zone3_pct=const(0.0),          # clear
        flood_zone2_pct=const(40.0),         # flagged
    ))
    assert topic(result, "flood")["state"] == "flagged"


# ---------------------------------------------------------------------------
# Flags carry their evidence
# ---------------------------------------------------------------------------
def test_a_flag_carries_the_value_and_the_threshold():
    result = radar.assess(report(flood_zone3_pct=const(31.0)))
    flag = result["flags"][0]
    assert flag["evidence"]["flood_zone3_pct"] == 31.0
    assert flag["evidence"]["threshold"] == "any intersection"
    assert "31%" in flag["text"]


def test_a_flag_carries_how_well_the_factor_was_proven():
    """`verified` and `written` are not the same claim and must not look alike."""
    result = radar.assess(report(
        conservation_area_pct=const(12.0, status="verified")))
    prov = result["flags"][0]["provenance"][0]
    assert prov["status"] == "verified"
    assert prov["publisher"] == "planning.data.gov.uk"
    assert prov["source"] == "open-data"


def test_severity_scales_with_the_observation():
    small = radar.assess(report(flood_zone3_pct=const(2.0)))["flags"][0]
    large = radar.assess(report(flood_zone3_pct=const(31.0)))["flags"][0]
    assert small["severity"] == "medium"
    assert large["severity"] == "high"


def test_zero_percent_is_not_a_flag():
    for field in ("sssi_pct", "green_belt_pct", "ancient_woodland_pct",
                  "conservation_area_pct", "scheduled_monument_pct"):
        result = radar.assess(report(**{field: const(0.0)}))
        assert result["flags"] == [], f"{field} flagged at 0%"


# ---------------------------------------------------------------------------
# Investigations trace back
# ---------------------------------------------------------------------------
def test_no_investigation_without_a_flag_that_raised_it():
    result = radar.assess(report(flood_zone3_pct=const(0.0)))
    assert result["investigations"] == []


def test_every_investigation_names_the_flags_behind_it():
    result = radar.assess(report(flood_zone3_pct=const(31.0)))
    ids = flag_ids(result)
    assert result["investigations"]
    for inv in result["investigations"]:
        assert inv["why"], f"{inv['id']} has no cause"
        assert set(inv["why"]) <= ids
        assert len(inv["why_text"]) == len(inv["why"])


def test_converging_evidence_promotes_a_medium_to_high():
    """Two independent observations pointing at the same check is stronger
    than either alone — but only medium is ever promoted."""
    one = radar.assess(report(water_seasonality=const(4.0, unit="months")))
    assert next(i for i in one["investigations"]
                if i["id"] == "ground_investigation")["priority"] == "medium"

    # Seasonally wet ground and a previously-developed signature are
    # independent observations from different sensors that both point at
    # digging a hole and looking.
    two = radar.assess(report(
        water_seasonality=const(4.0, unit="months"),
        ndbi=series([0.3 - 0.004 * i for i in range(72)], unit="index",
                    source="earth-engine"),
        bare_soil_index=series([0.4 - 0.004 * i for i in range(72)],
                               unit="index", source="earth-engine"),
    ))
    ground = next(i for i in two["investigations"]
                  if i["id"] == "ground_investigation")
    assert ground["priority"] == "high"
    assert len(ground["why"]) == 2


def test_a_pile_of_low_flags_never_becomes_high():
    result = radar.assess(report(water_seasonality=const(1.0, unit="months")))
    assert result["flags"][0]["severity"] == "low"
    assert all(i["priority"] != "high" for i in result["investigations"])


def test_investigations_are_ranked_worst_first():
    result = radar.assess(report(
        sssi_pct=const(80.0),                 # high
        conservation_area_pct=const(20.0),    # medium
    ))
    priorities = [i["priority"] for i in result["investigations"]]
    assert priorities == sorted(priorities, key=radar._rank)


def test_every_investigation_id_a_rule_names_actually_exists():
    """A typo here produces a flag whose recommendation silently vanishes."""
    for rule in radar.RULES:
        for inv in rule.investigations:
            assert inv in radar.INVESTIGATIONS, f"{rule.id} -> unknown {inv}"


def test_every_rule_belongs_to_a_declared_topic():
    for rule in radar.RULES:
        assert rule.topic in radar.TOPICS, f"{rule.id} -> unknown {rule.topic}"


def test_every_rule_names_a_real_factor():
    """A rule keyed to a factor id that does not exist can never fire, and
    would report "not assessed — add xyz_pct" for a layer nobody can add."""
    import catalog
    for rule in radar.RULES:
        for fid in rule.needs:
            assert fid in catalog.FACTOR_BY_ID, f"{rule.id} -> unknown {fid}"


# ---------------------------------------------------------------------------
# Behaviour rules
# ---------------------------------------------------------------------------
def test_vegetation_decline_uses_the_same_significance_test_as_findings():
    """Noise must not become a flag.

    A flat series with jitter has a non-zero slope every time. If the radar
    fitted its own line without the t-test, every site would collect a
    vegetation flag — and the Findings tab would disagree with it.
    """
    import itertools
    jitter = list(itertools.islice(
        itertools.cycle([0.60, 0.62, 0.58, 0.61, 0.59]), 96))
    flat = radar.assess(report(ndvi=series(jitter, unit="index",
                                           source="earth-engine", name="NDVI")))
    assert "vegetation_decline" not in flag_ids(flat)

    falling = [0.8 - 0.004 * i for i in range(96)]
    result = radar.assess(report(ndvi=series(falling, unit="index",
                                             source="earth-engine",
                                             name="NDVI")))
    flag = next(f for f in result["flags"] if f["id"] == "vegetation_decline")
    assert flag["evidence"]["ndvi_pct_change"] < 0


def test_vegetation_increase_is_not_a_decline_flag():
    rising = [0.3 + 0.004 * i for i in range(96)]
    result = radar.assess(report(ndvi=series(rising, unit="index",
                                             source="earth-engine")))
    assert "vegetation_decline" not in flag_ids(result)


def test_previously_developed_needs_both_indices_to_agree():
    """One index alone moves with drought and harvest."""
    built_falls = [0.3 - 0.004 * i for i in range(72)]
    bare_flat = [0.2] * 72

    one = radar.assess(report(
        ndbi=series(built_falls, unit="index", source="earth-engine"),
        bare_soil_index=series(bare_flat, unit="index", source="earth-engine"),
    ))
    assert "previously_developed" not in flag_ids(one)

    both = radar.assess(report(
        ndbi=series(built_falls, unit="index", source="earth-engine"),
        bare_soil_index=series([0.4 - 0.004 * i for i in range(72)],
                               unit="index", source="earth-engine"),
    ))
    assert "previously_developed" in flag_ids(both)


def test_a_rule_needing_two_factors_will_not_run_on_one():
    """Answering from half the inputs is worse than not answering."""
    result = radar.assess(report(
        ndbi=series([0.3 - 0.004 * i for i in range(72)], unit="index",
                    source="earth-engine")))
    entry = next(u for u in result["not_assessed"]
                 if u["rule"] == "previously_developed")
    assert entry["reason"] == "not_selected"
    assert entry["factors"] == ["bare_soil_index"]


# ---------------------------------------------------------------------------
# It must not take the report down with it
# ---------------------------------------------------------------------------
def test_a_broken_series_does_not_break_the_radar():
    result = radar.assess(report(
        flood_zone3_pct={"points": "not a list", "source": "open-data"},
        sssi_pct=const(40.0),
    ))
    assert "sssi" in flag_ids(result)


def test_empty_and_malformed_reports_are_survivable():
    for bad in (None, {}, {"series": None}, {"series": {}}):
        result = radar.assess(bad)
        assert result["flags"] == []
        assert result["counts"]["flags"] == 0


def test_limits_say_an_empty_radar_is_not_a_clean_bill_of_health():
    result = radar.assess(report(flood_zone3_pct=const(0.0)))
    assert "not that the site is sound" in result["limits"]
    assert "not regulatory tests" in result["limits"]


def test_counts_add_up():
    result = radar.assess(report(
        flood_zone3_pct=const(31.0),
        sssi_pct=const(0.0),
    ))
    counts = result["counts"]
    assert counts["flags"] == len(result["flags"])
    assert counts["high"] == sum(1 for f in result["flags"]
                                 if f["severity"] == "high")
    assert (counts["topics_flagged"] + counts["topics_clear"]
            + counts["topics_partial"]
            + counts["topics_not_assessed"]) == len(radar.TOPICS)


# ---------------------------------------------------------------------------
# `clear` is a claim, and it has to be earned
# ---------------------------------------------------------------------------
def test_generated_data_can_never_produce_a_clear():
    """The load-bearing invariant.

    "Generated data indicates no flood risk" is not the same claim as "we
    checked the Environment Agency's dataset and found none", and the two must
    never render as the same green tick. `clear` requires real *and* assessed
    *and* below threshold; anything else is `not_assessed`.
    """
    for value in (0.0, 0.5, 4.9):
        result = radar.assess(report(
            flood_zone3_pct=const(value, source="generated"),
            flood_zone2_pct=const(value, source="generated"),
        ))
        assert topic(result, "flood")["state"] == "not_assessed", value
        assert result["coverage"]["clear"] == 0


def test_clear_is_only_produced_where_every_check_in_the_topic_ran():
    """A topic with two checks where only one ran is not a clear topic."""
    partial = radar.assess(report(flood_zone3_pct=const(0.0)))
    assert topic(partial, "flood")["state"] == "partial"

    whole = radar.assess(report(flood_zone3_pct=const(0.0),
                                flood_zone2_pct=const(0.0)))
    assert topic(whole, "flood")["state"] == "clear"


# ---------------------------------------------------------------------------
# Coverage — a measure of what we looked at, never a score
# ---------------------------------------------------------------------------
def test_coverage_counts_what_the_rules_wanted_not_the_whole_catalogue():
    result = radar.assess(report(flood_zone3_pct=const(31.0)))
    cov = result["coverage"]
    import catalog
    assert cov["relevant"] < len(catalog.FACTORS)
    assert cov["assessed"] == 1
    assert cov["not_assessed"] == cov["relevant"] - 1
    assert 0 < cov["share"] < 1


def test_coverage_splits_not_assessed_by_cause():
    result = radar.assess(report(), real_capable={"flood_zone3_pct"})
    cov = result["coverage"]
    assert cov["not_selected"] >= 1
    assert cov["generated"] >= 1
    assert cov["not_selected"] + cov["generated"] == cov["not_assessed"]


def test_coverage_says_in_its_own_payload_that_it_is_not_a_score():
    """The temptation to collapse this into "Site health: 72/100" is the most
    commercially attractive wrong turn available to this product."""
    cov = radar.assess(report(flood_zone3_pct=const(0.0)))["coverage"]
    assert "not how good the site is" in cov["note"]
    assert "we simply know more about it" in cov["note"]


def test_there_is_no_overall_score_anywhere_in_the_payload():
    result = radar.assess(report(flood_zone3_pct=const(31.0)))
    banned = ("score", "rating", "grade", "suitability", "overall")
    flat = repr(sorted(result.keys())) + repr(sorted(result["coverage"].keys()))
    for word in banned:
        assert word not in flat.lower(), f"payload exposes a {word}"


# ---------------------------------------------------------------------------
# Informational findings
# ---------------------------------------------------------------------------
def test_informational_findings_are_not_flags():
    """A radar that can only ever deliver bad news is one people stop opening."""
    result = radar.assess(report(
        ndvi=const(0.48, unit="index", source="earth-engine", name="NDVI")))
    assert result["flags"] == []
    assert result["investigations"] == []
    info = next(i for i in result["informational"] if i["id"] == "info_ndvi")
    assert "0.48" in info["text"]
    assert "severity" not in info


def test_informational_data_obeys_the_same_real_data_rule():
    """A generated informational finding is still a fabricated fact about a
    real place — it merely omits the step where someone acts on it."""
    result = radar.assess(report(
        ndvi=const(0.48, unit="index", source="generated")))
    assert result["informational"] == []


def test_an_informational_finding_never_makes_a_topic_flagged():
    result = radar.assess(report(
        elevation_mean=const(61.0, unit="m", source="earth-engine")))
    assert topic(result, "terrain")["state"] != "flagged"


# ---------------------------------------------------------------------------
# The assessment log
# ---------------------------------------------------------------------------
def test_the_log_records_every_factor_and_what_became_of_it():
    result = radar.assess(report(flood_zone3_pct=const(31.0)),
                          real_capable={"flood_zone3_pct", "flood_zone2_pct"})
    by_id = {r["factor"]: r for r in result["log"]}
    assert by_id["flood_zone3_pct"]["state"] == "assessed"
    assert by_id["flood_zone3_pct"]["publisher"] == "planning.data.gov.uk"
    assert by_id["flood_zone2_pct"]["state"] == "not_selected"
    assert by_id["slope_max"]["state"] == "generated"
    # Every row is timestamped, so a report read in three months can be
    # understood rather than trusted.
    assert all(r["at"] == result["assessed_at"] for r in result["log"])


def test_the_log_records_status_only_where_something_was_assessed():
    """`verified` on a factor nobody read is a claim about nothing."""
    result = radar.assess(report(flood_zone3_pct=const(31.0)))
    for row in result["log"]:
        if row["state"] != "assessed":
            assert row["status"] is None


def test_investigations_carry_a_next_step_and_their_evidence():
    result = radar.assess(report(flood_zone3_pct=const(31.0)))
    inv = next(i for i in result["investigations"]
               if i["id"] == "flood_risk_assessment")
    assert inv["next_step"].startswith("Commission")
    assert inv["evidence_factors"] == ["flood_zone3_pct"]


def test_every_investigation_has_a_next_step():
    for key, meta in radar.INVESTIGATIONS.items():
        assert meta.get("next_step"), f"{key} has no next step"


def test_the_principle_travels_with_every_report():
    result = radar.assess(report())
    assert result["principle"] == radar.PRINCIPLE
    assert "clear result means we checked" in result["principle"]


# ---------------------------------------------------------------------------
# The capability registry — the UI must never have to guess
# ---------------------------------------------------------------------------
def test_capabilities_never_claims_more_than_the_process_can_do():
    """`implemented`, `real` and `verified` answer three different questions.

    Conflating them is how "add this layer" started promising checks that could
    not be delivered. A deployment with no Earth Engine credentials implements
    27 factors and can prove none of them.
    """
    from fastapi.testclient import TestClient
    import mock_ee_backend

    body = TestClient(mock_ee_backend.app).get("/api/capabilities").json()
    rows = {r["factor"]: r for r in body["factors"]}

    import catalog
    assert len(rows) == len(catalog.FACTORS)

    for row in rows.values():
        # A factor cannot be verified unless it is real.
        if row["verified"]:
            assert row["real"], row["factor"]
        # Nothing generated may claim a live status.
        if not row["real"]:
            assert row["status"] == "generated", row["factor"]
        # An investigation-capable factor must be radar-capable.
        if row["supports_investigation"]:
            assert row["supports_radar"], row["factor"]

    assert body["summary"]["provable"] <= body["summary"]["total"]
    assert body["summary"]["radar_provable"] <= body["summary"]["radar_factors"]


def test_capabilities_agrees_with_the_radar_about_which_factors_it_reads():
    from fastapi.testclient import TestClient
    import mock_ee_backend

    body = TestClient(mock_ee_backend.app).get("/api/capabilities").json()
    claimed = {r["factor"] for r in body["factors"] if r["supports_radar"]}
    actual = {f for rule in radar.RULES for f in rule.needs}
    assert claimed == actual


def test_converging_evidence_requires_different_factors_not_just_two_rules():
    """Two methods on one measurement is not converging evidence.

    A trend test and a baseline-change test over the same NDVI series both
    raise an ecological appraisal, and promoting on that counts the same
    evidence twice. It is indistinguishable from genuine convergence in the
    payload, which is why the condition is on the factors rather than on the
    flag count.

    Driven through `_investigations` directly: the two real NDVI rules measure
    percentage change differently and cannot both land on `medium` for any
    input, so an end-to-end version of this test would be asserting a
    coincidence of two severity mappings rather than the promotion rule.
    """
    def flag(fid, factor):
        return {"id": fid, "severity": "medium", "factors": [factor],
                "text": f"{fid} fired", "investigations": ["ecology_survey"]}

    same = radar._investigations([flag("vegetation_decline", "ndvi"),
                                  flag("historical_vegetation_decline", "ndvi")])
    survey = next(i for i in same if i["id"] == "ecology_survey")
    assert len(survey["why"]) == 2, "both flags must still be listed"
    assert survey["priority"] == "medium", "same factor is not convergence"
    assert survey["evidence_factors"] == ["ndvi"]

    different = radar._investigations([flag("standing_water", "water_occurrence"),
                                       flag("tpo", "tpo_density")])
    survey = next(i for i in different if i["id"] == "ecology_survey")
    assert survey["priority"] == "high", "independent factors do converge"


def test_both_ndvi_rules_can_fire_without_inflating_each_other():
    """The end-to-end half: two rules on one factor, and the investigation's
    priority is theirs rather than a product of there being two of them."""
    falling = [0.60 - 0.0016 * i for i in range(132)]
    ndvi = series(falling, unit="index", source="earth-engine", name="NDVI")
    result = radar.assess(report(ndvi=ndvi))

    raised = [f for f in result["flags"]
              if "ecology_survey" in f["investigations"]]
    assert len(raised) == 2, [f["id"] for f in raised]

    survey = next(i for i in result["investigations"]
                  if i["id"] == "ecology_survey")
    assert survey["evidence_factors"] == ["ndvi"]
    # High because one of the two flags is high on its own merits, not because
    # two flags pointed at the same survey.
    assert survey["priority"] == min((f["severity"] for f in raised),
                                     key=radar._rank)
