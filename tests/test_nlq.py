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
