"""Natural-language querying.

The stakes here are different from the rest of the API. A wrong number in the
attribute table is visible next to fifteen other numbers; a wrong sentence in
an answer is the only thing the reader sees, and it arrives in the voice of
something that knows. So these tests are weighted towards what the feature
refuses to say.
"""

import catalog
import nlq
import pytest
from fastapi.testclient import TestClient

FIRST, LAST = int(catalog.TIME_START[:4]), int(catalog.TIME_END[:4])

GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[[-0.60, 51.24], [-0.57, 51.24], [-0.57, 51.26],
                     [-0.60, 51.26], [-0.60, 51.24]]],
}


@pytest.fixture(scope="module")
def client():
    import mock_ee_backend
    return TestClient(mock_ee_backend.app)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def test_the_brief_example_resolves_to_tree_cover():
    """The question the improvement brief itself uses as the worked example."""
    got = nlq.interpret("has tree cover dropped near this site since 2019?", FIRST, LAST)
    assert got["factor_ids"][0] == "lc_tree_pct"
    assert got["from_year"] == 2019
    assert got["to_year"] == LAST
    assert got["intent"] == "trend"


@pytest.mark.parametrize("question,expected", [
    ("since 2019", (2019, LAST)),
    ("between 2015 and 2020", (2015, 2020)),
    ("between 2020 and 2015", (2015, 2020)),        # written backwards
    ("in 2022", (2022, 2022)),
    ("over the last 5 years", (LAST - 4, LAST)),
    ("before 2018", (FIRST, 2018)),
    ("has it changed", (FIRST, LAST)),              # no date means "ever"
    ("since 1850", (FIRST, LAST)),                  # clamped to what exists
])
def test_year_ranges(question, expected):
    assert nlq.parse_years(question, FIRST, LAST) == expected


@pytest.mark.parametrize("question,intent", [
    ("has tree cover dropped", "trend"),
    ("what was the average rainfall", "level"),
    ("which year was hottest", "extreme"),
])
def test_intent(question, intent):
    assert nlq.parse_intent(question) == intent


def test_intent_survives_the_stop_list():
    """`average` and `year` are stripped before factor matching because they
    match factor names without meaning anything. Reading intent from the
    filtered words turned every "what was the average..." into a trend."""
    assert nlq.parse_intent("what was the average rainfall") == "level"
    assert nlq.parse_intent("which year was hottest") == "extreme"


def test_question_words_do_not_select_factors():
    """"which year" must not match every factor with "year" in its name."""
    ids = [fid for fid, _ in nlq.match_factors("which year was hottest")]
    assert ids, "expected a temperature factor"
    assert all("temp" in fid for fid in ids), ids


def test_a_typed_word_outranks_a_synonym():
    ids = [fid for fid, _ in nlq.match_factors("tree cover")]
    assert ids[0] == "lc_tree_pct"


# ---------------------------------------------------------------------------
# What it refuses to say
# ---------------------------------------------------------------------------
def test_unmatched_question_answers_nothing():
    got = nlq.interpret("tell me about badgers", FIRST, LAST)
    assert got["factor_ids"] == []
    answer = nlq.ask("tell me about badgers", {}, got)
    assert "could not tell" in answer["answer"]
    # The failure must not read like a finding.
    assert "%" not in answer["answer"]


def test_change_inside_the_noise_floor_is_not_a_trend():
    """A series that wanders by 5 a year and ends 2 higher has not risen."""
    factor = {"id": "x", "name": "Test factor", "unit": "%", "kind": "continuous"}
    annual = [{"year": y, "value": v} for y, v in
              zip(range(2019, 2025), [50, 55, 45, 58, 44, 52])]
    got = nlq.answer_one(factor, {"annual": annual, "source": "earth-engine"},
                         2019, 2024, "trend")
    assert got["verdict"] == "flat"
    assert "no clear trend" in got["text"]


def test_a_change_beyond_the_noise_floor_is_reported():
    factor = {"id": "x", "name": "Test factor", "unit": "%", "kind": "continuous"}
    annual = [{"year": y, "value": v} for y, v in
              zip(range(2019, 2025), [50, 49, 48, 47, 46, 20])]
    got = nlq.answer_one(factor, {"annual": annual, "source": "earth-engine"},
                         2019, 2024, "trend")
    assert got["verdict"] == "trend"
    assert got["change"] < 0
    assert "fell" in got["text"]


def test_no_observations_in_range_says_so():
    factor = {"id": "x", "name": "Test factor", "unit": "%", "kind": "continuous"}
    annual = [{"year": 2011, "value": 5.0}, {"year": 2012, "value": None}]
    got = nlq.answer_one(factor, {"annual": annual, "source": "earth-engine"},
                         2020, 2024, "trend")
    assert got["verdict"] == "no-data"
    assert "No observations" in got["text"]


def test_one_year_is_not_a_trend():
    factor = {"id": "x", "name": "Test factor", "unit": "%", "kind": "continuous"}
    annual = [{"year": 2020, "value": 5.0}]
    got = nlq.answer_one(factor, {"annual": annual, "source": "earth-engine"},
                         2020, 2024, "trend")
    assert got["verdict"] == "no-data"
    assert "nothing to compare" in got["text"]


def test_generated_data_is_labelled_in_the_answer():
    """The rule the whole project runs on: a number from series.py never
    appears without saying it is not an observation."""
    interpretation = nlq.interpret("has tree cover dropped since 2019", FIRST, LAST)
    fid = interpretation["factor_ids"][0]
    annual = [{"year": y, "value": float(y - 2000)} for y in range(2019, 2026)]
    answer = nlq.ask("has tree cover dropped since 2019",
                     {fid: {"annual": annual, "source": "generated"}},
                     interpretation)
    assert "demo data" in answer["answer"]


def test_observed_data_carries_no_demo_caveat():
    interpretation = nlq.interpret("has tree cover dropped since 2019", FIRST, LAST)
    fid = interpretation["factor_ids"][0]
    annual = [{"year": y, "value": float(y - 2000)} for y in range(2019, 2026)]
    answer = nlq.ask("has tree cover dropped since 2019",
                     {fid: {"annual": annual, "source": "earth-engine"}},
                     interpretation)
    assert "demo data" not in answer["answer"]


def test_rephrase_without_a_key_returns_the_computed_answer(monkeypatch):
    """No key is the deployed case, so it is the one that must not degrade."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    computed = {"answer": "Tree cover fell 4%.", "findings": [{"label": "x"}]}
    assert nlq.rephrase(computed) == computed


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------
def test_ask_endpoint_answers_from_the_series(client):
    r = client.post("/api/ask", json={
        "geometry": GEOMETRY,
        "question": "has tree cover dropped near this site since 2019?",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["answered_from"] == "series"
    assert body["understood"]["from_year"] == 2019
    assert body["findings"], "expected at least one finding"
    # Every figure quoted must come back with the series it came from, so the
    # answer can be checked against the table rather than trusted.
    for fid in body["understood"]["factor_ids"]:
        assert fid in body["series"]


def test_ask_endpoint_offers_help_when_nothing_matches(client):
    r = client.post("/api/ask", json={"geometry": GEOMETRY,
                                      "question": "tell me about badgers"})
    assert r.status_code == 200
    body = r.json()
    assert body["findings"] == []
    assert body["suggestions"]


def test_ask_endpoint_rejects_a_bad_geometry(client):
    r = client.post("/api/ask", json={"geometry": {"type": "Polygon", "coordinates": []},
                                      "question": "has tree cover dropped"})
    assert r.status_code in (400, 422)


def test_ask_endpoint_rejects_an_empty_question(client):
    r = client.post("/api/ask", json={"geometry": GEOMETRY, "question": ""})
    assert r.status_code == 422


def test_ask_only_fetches_the_years_asked_for(client):
    """Asking about 2024 should not pay for 2011 onwards."""
    r = client.post("/api/ask", json={"geometry": GEOMETRY,
                                      "question": "what was tree cover in 2024"})
    body = r.json()
    fid = body["understood"]["factor_ids"][0]
    years = {a["year"] for a in body["series"][fid]["annual"]}
    assert years == {2024}


# ---------------------------------------------------------------------------
# Partial years at the endpoints
#
# A trend is the difference between two endpoints, so a short endpoint is the
# one place a coverage gap turns straight into a reported change. Worse, the
# noise floor cannot catch it: a stable series has a noise floor of zero, so
# any artefact clears it. The steadier the factor, the more reliably a missing
# autumn gets narrated as a trend.
# ---------------------------------------------------------------------------

FACTOR = {"id": "air_temp", "name": "Air temperature", "unit": "°C",
          "kind": "continuous"}


def seasonal_year(year, months, amplitude=8.0, base=10.0):
    """One annual row from a sine with its minimum in January."""
    import math
    vals = [base + amplitude * -math.cos((m - 1) / 12 * 2 * math.pi) for m in months]
    return {"year": year, "value": round(sum(vals) / len(vals), 4),
            "min": min(vals), "max": max(vals),
            "months_observed": len(months), "months_total": 12, "confidence": 0.9}


def ask(annual, lo=2019, hi=2026, intent="trend"):
    return nlq.answer_one(FACTOR, {"annual": annual, "source": "earth-engine"},
                          lo, hi, intent)


def test_a_part_observed_final_year_does_not_invent_a_trend():
    # Seven identical years and a current year holding January to August — the
    # warm half. Before this guard the answer was "rose 9%" for a series with
    # no trend whatsoever.
    annual = [seasonal_year(y, range(1, 13)) for y in range(2019, 2026)]
    annual.append(seasonal_year(2026, range(1, 9)))
    got = ask(annual)
    assert got["verdict"] == "flat"
    assert "rose" not in got["text"]
    assert "2026 was left out" in got["text"]


def test_the_excluded_year_is_named_not_silently_dropped():
    # The user can see 2026 in the attribute table. An answer that quietly
    # ignores it is the same two-views-disagreeing problem this project
    # refuses everywhere else.
    annual = [seasonal_year(y, range(1, 13)) for y in range(2019, 2026)]
    annual.append(seasonal_year(2026, range(1, 9)))
    assert "2026" in ask(annual)["text"]


def test_a_complete_final_year_is_not_excluded():
    annual = [seasonal_year(y, range(1, 13)) for y in range(2019, 2027)]
    assert "left out" not in ask(annual)["text"]


def test_a_uniformly_short_series_is_still_answerable():
    # THE case an absolute twelve-month threshold breaks. Sentinel-2 never sees
    # a January, so every NDVI year has nine or ten months; refusing those
    # would decline every question about vegetation in the catalogue.
    annual = [seasonal_year(y, range(3, 12)) for y in range(2019, 2027)]
    got = ask(annual)
    assert got["verdict"] in {"flat", "trend"}
    assert "left out" not in got["text"]


def test_a_year_short_relative_to_its_own_series_is_excluded():
    # Same nine-month NDVI shape, but the last year has only five. Short
    # against twelve is not the test; short against its neighbours is.
    annual = [seasonal_year(y, range(3, 12)) for y in range(2019, 2026)]
    annual.append(seasonal_year(2026, range(3, 8)))
    assert "2026 was left out" in ask(annual)["text"]


def test_one_month_of_slack_absorbs_an_ordinary_cloudy_winter():
    # An eleven-month year among twelves is not a different set of seasons,
    # and excluding it would make the caveat routine enough to ignore.
    annual = [seasonal_year(y, range(1, 13)) for y in range(2019, 2026)]
    annual.append(seasonal_year(2026, range(1, 12)))
    assert "left out" not in ask(annual)["text"]


def test_several_excluded_years_are_listed_together():
    annual = [seasonal_year(2019, range(1, 6))]
    annual += [seasonal_year(y, range(1, 13)) for y in range(2020, 2026)]
    annual.append(seasonal_year(2026, range(1, 6)))
    text = ask(annual)["text"]
    assert "2019 and 2026 were left out" in text


def test_a_short_year_is_kept_out_of_the_mean_too():
    # Not just the endpoints: a partial year anywhere in the range drags the
    # average toward whichever seasons it happens to hold.
    annual = [seasonal_year(y, range(1, 13)) for y in range(2019, 2026)]
    annual.insert(3, seasonal_year(2022, range(5, 9)))       # high summer only
    del annual[4]
    got = ask(annual, intent="level")
    assert got["mean"] == pytest.approx(10.0, abs=0.01)


def test_the_filter_can_never_discard_everything():
    # The threshold is the range's own median, so the median-coverage rows
    # always survive their own test. This is why answer_one has no "everything
    # was too short" branch — it would be unreachable. If this invariant ever
    # breaks, that branch has to come back.
    for months in ([1], [1, 2], [1, 12], [3, 3, 3], [1, 5, 12, 12]):
        rows = [seasonal_year(2019 + i, range(1, m + 1))
                for i, m in enumerate(months)]
        assert nlq._comparable(rows), months


def test_one_comparable_year_left_is_not_a_trend():
    annual = [seasonal_year(y, range(1, 13)) for y in (2019,)]
    annual.append(seasonal_year(2026, range(1, 4)))
    got = ask(annual)
    assert got["verdict"] == "no-data"
    assert "2026" in got["text"]


def test_a_response_without_coverage_still_answers():
    # Older cached responses and any source that does not report coverage.
    # Dropping every row would turn a missing field into "no data", which is a
    # worse answer than the slightly-too-confident one it replaced.
    annual = [{"year": y, "value": v} for y, v in
              zip(range(2019, 2025), [50, 49, 48, 47, 46, 20])]
    got = nlq.answer_one(FACTOR, {"annual": annual, "source": "earth-engine"},
                         2019, 2024, "trend")
    assert got["verdict"] == "trend"
    assert "left out" not in got["text"]


def test_the_extreme_answer_carries_the_caveat_too():
    # "Highest year on record" is exactly the claim a warm-half year wins.
    annual = [seasonal_year(y, range(1, 13)) for y in range(2019, 2026)]
    annual.append(seasonal_year(2026, range(5, 9)))
    got = ask(annual, intent="extreme")
    assert got["high_year"] != 2026
    assert "2026 was left out" in got["text"]


# ---------------------------------------------------------------------------
# The rewrite guard
#
# The system prompt tells the model not to alter a number and not to drop a
# caveat. An instruction is not an enforcement. `_rewrite_is_faithful` is the
# enforcement, and these are the cases that decide whether it is worth having.
# ---------------------------------------------------------------------------
def test_an_invented_number_discards_the_rewrite():
    """The single failure the whole architecture is arranged to prevent. The
    model is never asked what a figure is; if one appears anyway, the rewrite
    is not used."""
    assert not nlq._rewrite_is_faithful(
        "Tree cover has fallen since 2019.",
        "Tree cover has fallen 18% since 2019.")


def test_dropping_a_number_is_allowed():
    """A summary legitimately says less. Only invention is forbidden."""
    assert nlq._rewrite_is_faithful(
        "NDVI rose 12% since 2019.", "NDVI rose since 2019.")


def test_a_faithful_rewrite_is_kept():
    assert nlq._rewrite_is_faithful(
        "NDVI rose 12% since 2019.",
        "Vegetation vigour increased by 12% from 2019 onwards.")


def test_a_dropped_demo_caveat_discards_the_rewrite():
    """insights.py puts the caveat *inside* the sentence so no layout can drop
    it. A rewrite is a layout that can. A fluent sentence that has quietly
    shed the word "demo" is worse than a clumsy one that kept it."""
    assert not nlq._rewrite_is_faithful(
        "Tree cover fell 4% (demo data — generated, not observed).",
        "Tree cover fell 4% over the period.")


def test_a_caveat_carried_through_in_other_words_is_kept():
    assert nlq._rewrite_is_faithful(
        "Tree cover fell 4% (demo data).",
        "Tree cover fell 4%. Note that this is demo data.")


def test_the_guard_runs_on_the_real_path(monkeypatch):
    """The check has to be wired in, not merely defined. A guard nobody calls
    is a comment."""
    import inspect
    src = inspect.getsource(nlq)
    assert "_rewrite_is_faithful(answer[" in src, \
        "the rephrase path must gate on the guard"
