"""
The comparison contract, enforced.

`COMPARISON_CONTRACT.md` was written before `comparison.py`. This file is what
stops the document and the code drifting apart.

Comparison is the first feature that actively tempts a developer to break EM7.
The user asks "so which one is best?" in plain language; the answer feels
helpful; and a sortable totals column arrives without anyone deciding to add
ranking. Most of what is tested here is therefore refusal.

The single most important test is
`test_em10_fewer_flags_never_reads_as_a_better_site` — the failure it guards
against misleads in favour of whichever parcel nobody investigated.
"""

import pytest

import comparison
import radar


def series(value, *, source="open-data", name="Flood Zone 3", n=36):
    points, year, month = [], 2018, 1
    for _ in range(n):
        points.append({"t": f"{year:04d}-{month:02d}", "value": value,
                       "interpolated": False})
        month += 1
        if month > 12:
            month, year = 1, year + 1
    return {"unit": "%", "cadence": "monthly", "source": source,
            "points": points, "meta": {"name": name},
            "provenance": {"source": "planning.data.gov.uk",
                           "endpoint": "planning.data.gov.uk",
                           "status": "written"}}


def site(sid, name, factors, real_capable=None):
    """A site with a real radar payload computed over `factors`."""
    payload = radar.assess({"series": factors},
                           real_capable=real_capable or set(factors))
    payload["_series"] = factors
    return {"id": sid, "name": name, "radar": payload}


FLOOD_HEAVY = {"flood_zone3_pct": series(31.0), "flood_zone2_pct": series(44.0),
               "green_belt_pct": series(0.0, name="Green Belt"),
               "sssi_pct": series(0.0, name="SSSI coverage")}
FLOOD_CLEAR = {"flood_zone3_pct": series(0.0), "flood_zone2_pct": series(0.0),
               "green_belt_pct": series(0.0, name="Green Belt"),
               "sssi_pct": series(0.0, name="SSSI coverage")}
BARELY_LOOKED = {"flood_zone3_pct": series(4.0)}


def generated_texts(result):
    """Every sentence the comparison *composes* about these particular sites.

    The fixed disclaimers are excluded and pinned separately instead — see
    `test_em10_the_fixed_disclaimers_are_exactly_the_module_constants`. A
    disclaimer saying "Contour does not rank sites" contains the word `rank`
    while being the opposite of a ranking, and a substring scan cannot tell
    denial from assertion.

    Excluding them is safe only because they are constants that a test pins.
    Every sentence built from site data goes through the strict scan below,
    which is where a violation would actually appear.
    """
    out = [result["coverage_warning"]]
    out += [d["text"] for d in result["differences"]]
    out += [t["note"] for t in result["topics"]]
    return [t for t in out if t]


# ---------------------------------------------------------------------------
# EM10 — comparison describes differences; it never ranks
# ---------------------------------------------------------------------------
#: Judgement, as opposed to quantity. A quantity statement can be checked
#: against a number on the same screen; a judgement cannot be checked against
#: anything.
FORBIDDEN = (
    "best", "worst", "better", "strongest", "weakest", "superior", "inferior",
    "suitable", "unsuitable", "viable", "developable", "recommend",
    "preferred", "prefer", "ideal", "optimal", "winner", "leading",
    "favourable", "unfavourable", "rank", "score", "grade", "rating",
    "top choice", "overall assessment",
)


def test_em10_no_generated_sentence_contains_a_judgement():
    """Scanned across several site shapes, because a judgement word could
    appear only on the branch that fires for uneven coverage."""
    pairs = [
        [site("a", "Site A", FLOOD_HEAVY), site("b", "Site B", FLOOD_CLEAR)],
        [site("a", "Site A", FLOOD_HEAVY), site("c", "Site C", BARELY_LOOKED)],
        [site("b", "Site B", FLOOD_CLEAR), site("c", "Site C", BARELY_LOOKED),
         site("a", "Site A", FLOOD_HEAVY)],
    ]
    for sites in pairs:
        for text in generated_texts(comparison.compare(sites)):
            low = text.lower()
            for word in FORBIDDEN:
                assert word not in low, f"{word!r} in: {text}"


def test_em10_the_fixed_disclaimers_are_exactly_the_module_constants():
    """The disclaimers are exempt from the substring scan, so they are pinned.

    Without this, "Contour does not rank sites" could be edited into something
    that ranks and the exemption would hide it.
    """
    result = comparison.compare([site("a", "Site A", FLOOD_HEAVY),
                                 site("b", "Site B", FLOOD_CLEAR)])
    assert result["limits"] == comparison.LIMITS
    assert result["principle"] == radar.PRINCIPLE
    for s in result["sites"]:
        assert s["coverage_note"] == radar.COVERAGE_NOTE
    # And each says the thing it exists to say.
    assert "does not rank sites" in comparison.LIMITS
    assert "may simply have been examined less" in comparison.LIMITS
    assert "not how good the site is" in radar.COVERAGE_NOTE


def test_em10_the_payload_exposes_no_score_key_at_any_depth():
    result = comparison.compare([site("a", "Site A", FLOOD_HEAVY),
                                 site("b", "Site B", FLOOD_CLEAR)])
    banned = ("score", "rating", "grade", "rank", "overall", "suitability",
              "winner", "best")

    def walk(node, path="compare"):
        if isinstance(node, dict):
            for key, value in node.items():
                for word in banned:
                    assert word not in str(key).lower(), f"{path}.{key}"
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{path}[{i}]")

    walk(result)


def test_em10_sites_come_back_in_the_order_supplied():
    """Any ordering by count is a ranking, whatever it is called."""
    a, b, c = (site("a", "Site A", FLOOD_HEAVY),
               site("b", "Site B", FLOOD_CLEAR),
               site("c", "Site C", BARELY_LOOKED))
    for order in ([a, b, c], [c, a, b], [b, c, a]):
        result = comparison.compare(order)
        assert [s["id"] for s in result["sites"]] == [s["id"] for s in order]


def test_em10_no_composite_number_is_produced_per_site():
    """If a calculation's output is one figure per site that rises as the site
    gets "better", it is a score whatever it is called."""
    result = comparison.compare([site("a", "Site A", FLOOD_HEAVY),
                                 site("b", "Site B", FLOOD_CLEAR)])
    allowed = {"id", "name", "flags", "high", "informational", "observed",
               "relevant", "not_assessed", "share", "coverage_note"}
    for s in result["sites"]:
        assert set(s) == allowed, set(s) - allowed


# ---------------------------------------------------------------------------
# The trap: fewer flags can mean less looked at
# ---------------------------------------------------------------------------
def test_em10_fewer_flags_never_reads_as_a_better_site():
    """The most important test in this file.

    Site C has zero flags because almost nothing was assessed. A comparison
    that reports counts without coverage misleads in favour of whichever parcel
    nobody investigated — the worst possible direction for a tool people use to
    decide where to spend money.
    """
    heavy = site("a", "Site A", FLOOD_HEAVY)
    thin = site("c", "Site C", BARELY_LOOKED)
    result = comparison.compare([heavy, thin])

    assert result["coverage_warning"], "unequal coverage must warn, unprompted"
    warning = result["coverage_warning"].lower()
    assert "site c" in warning
    assert "less was looked at" in warning


def test_em10_every_flag_count_travels_with_its_coverage():
    result = comparison.compare([site("a", "Site A", FLOOD_HEAVY),
                                 site("c", "Site C", BARELY_LOOKED)])
    for s in result["sites"]:
        # A count is meaningless without the denominator beside it.
        assert "observed" in s and "relevant" in s and "share" in s
        assert s["coverage_note"]

    # And any sentence mentioning flags names the coverage in the same breath.
    for diff in result["differences"]:
        if diff["kind"] == "flags":
            assert "observed" in diff["text"], diff["text"]


def test_em10_equal_coverage_produces_no_spurious_warning():
    """The control. A warning that always fires is a warning nobody reads."""
    result = comparison.compare([site("a", "Site A", FLOOD_HEAVY),
                                 site("b", "Site B", FLOOD_CLEAR)])
    assert result["coverage_warning"] == ""


# ---------------------------------------------------------------------------
# What may be compared
# ---------------------------------------------------------------------------
def test_a_factor_only_one_site_observed_is_never_a_value_difference():
    """"Site A has more flood risk than Site B" when B was never checked is
    the specific error this layer exists to make impossible."""
    result = comparison.compare([site("a", "Site A", FLOOD_HEAVY),
                                 site("c", "Site C", BARELY_LOOKED)])
    compared = {d.get("factor") for d in result["differences"]
                if d["kind"] == "value"}
    # Site C observed only flood_zone3_pct, so nothing else may be compared.
    assert compared <= {"flood_zone3_pct"}


def test_a_value_difference_requires_every_site_to_have_observed_it():
    result = comparison.compare([site("a", "Site A", FLOOD_HEAVY),
                                 site("b", "Site B", FLOOD_CLEAR)])
    values = [d for d in result["differences"] if d["kind"] == "value"]
    assert values, "sites observing the same factors should produce values"
    for diff in values:
        assert len(diff["sites"]) == 2


def test_generated_data_is_never_compared():
    """EM1–EM3 do not stop applying because there are two sites."""
    fake = {k: series(v.get("points")[0]["value"], source="generated")
            for k, v in FLOOD_HEAVY.items()}
    result = comparison.compare([{"id": "a", "name": "Site A",
                                  "radar": {**radar.assess({"series": fake}),
                                            "_series": fake}},
                                 site("b", "Site B", FLOOD_CLEAR)])
    assert [d for d in result["differences"] if d["kind"] == "value"] == []


def test_a_missing_value_is_never_read_as_zero():
    """A comparison that reads a missing value as 0 produces "Site B has 0%
    flood risk" for a site whose flood layer was never loaded."""
    payload = radar.assess({"series": BARELY_LOOKED})
    payload["_series"] = BARELY_LOOKED
    assert comparison._observed_level(payload, "green_belt_pct") is None
    assert comparison._observed_level(payload, "flood_zone3_pct") == 4.0


# ---------------------------------------------------------------------------
# Topic comparison
# ---------------------------------------------------------------------------
def test_a_topic_is_comparable_only_when_both_sites_assessed_it_fully():
    result = comparison.compare([site("a", "Site A", FLOOD_HEAVY),
                                 site("b", "Site B", FLOOD_CLEAR)])
    flood = next(t for t in result["topics"] if t["id"] == "flood")
    assert flood["comparable"] is True
    assert flood["note"] == ""

    uneven = comparison.compare([site("a", "Site A", FLOOD_HEAVY),
                                 site("c", "Site C", BARELY_LOOKED)])
    flood = next(t for t in uneven["topics"] if t["id"] == "flood")
    assert flood["comparable"] is False
    assert "different amounts of evidence" in flood["note"]


def test_every_topic_appears_for_every_site():
    """A topic missing from one column is indistinguishable from a clear one."""
    result = comparison.compare([site("a", "Site A", FLOOD_HEAVY),
                                 site("b", "Site B", FLOOD_CLEAR),
                                 site("c", "Site C", BARELY_LOOKED)])
    assert len(result["topics"]) == len(radar.TOPICS)
    for row in result["topics"]:
        assert [c["id"] for c in row["sites"]] == ["a", "b", "c"]


def test_the_limits_and_principle_travel_with_the_comparison():
    result = comparison.compare([site("a", "Site A", FLOOD_HEAVY),
                                 site("b", "Site B", FLOOD_CLEAR)])
    assert result["principle"] == radar.PRINCIPLE
    assert "does not rank sites" in result["limits"]
    assert "may simply have been examined less" in result["limits"]


def test_comparison_survives_thin_and_malformed_input():
    for bad in ([], [{"id": "a", "name": "A"}],
                [{"id": "a", "name": "A", "radar": {}},
                 {"id": "b", "name": "B", "radar": None}]):
        result = comparison.compare(bad)
        assert "sites" in result and "topics" in result
        assert result["differences"] == [] or all(
            d.get("text") for d in result["differences"])


# ---------------------------------------------------------------------------
# The API boundary
# ---------------------------------------------------------------------------
def _client():
    from fastapi.testclient import TestClient
    import mock_ee_backend
    return TestClient(mock_ee_backend.app)


def _square(west):
    return {"type": "Polygon", "coordinates": [[
        [west, 51.20], [west + 0.04, 51.20], [west + 0.04, 51.23],
        [west, 51.23], [west, 51.20]]]}


def _body(n=2, factors=("flood_zone3_pct", "ndvi")):
    return {"sites": [{"id": f"s{i}", "name": f"Site {i}",
                       "geometry": _square(-0.60 + 0.1 * i)} for i in range(n)],
            "factor_ids": list(factors)}


def test_the_compare_endpoint_returns_the_contract_shape():
    body = _client().post("/api/compare", json=_body()).json()
    for key in ("sites", "topics", "differences", "coverage_warning",
                "principle", "limits"):
        assert key in body, key
    assert len(body["topics"]) == len(radar.TOPICS)


def test_the_compare_endpoint_never_leaks_the_private_series_channel():
    """`_series` is several megabytes of points and an implementation channel
    between two server modules, not part of the response."""
    import json
    raw = json.dumps(_client().post("/api/compare", json=_body()).json())
    assert "_series" not in raw


def test_the_compare_endpoint_refuses_fewer_than_two_and_more_than_four():
    client = _client()
    assert client.post("/api/compare", json=_body(1)).status_code == 422
    assert client.post("/api/compare", json=_body(5)).status_code == 422
    assert client.post("/api/compare", json=_body(4)).status_code == 200


def test_the_compare_endpoint_names_the_site_that_failed():
    """"That area is outside England" against four geometries is a message the
    user cannot act on."""
    body = _body()
    body["sites"][1]["geometry"] = _square(30.0)      # not England
    body["sites"][1]["name"] = "Somewhere in Poland"
    response = _client().post("/api/compare", json=body)
    assert response.status_code == 400
    assert "Somewhere in Poland" in response.json()["detail"]


def test_the_compare_endpoint_rejects_unknown_factors():
    body = _body()
    body["factor_ids"] = ["flood_zone3_pct", "not_a_factor"]
    assert _client().post("/api/compare", json=body).status_code == 422


def test_the_compare_endpoint_preserves_the_order_supplied():
    body = _body(3)
    body["sites"].reverse()
    result = _client().post("/api/compare", json=body).json()
    assert [s["id"] for s in result["sites"]] == [s["id"] for s in body["sites"]]


def test_uneven_evidence_is_only_claimed_when_the_sites_actually_differ():
    """Three sites all at 0/2 are not unevenly evidenced — they are uniformly
    unevidenced, and labelling that "uneven evidence" asserts a difference that
    is not there."""
    result = comparison.compare([site("a", "Site A", FLOOD_HEAVY),
                                 site("b", "Site B", FLOOD_CLEAR)])
    # Neither site loaded any surface-water factor: equal, and equally absent.
    water = next(t for t in result["topics"] if t["id"] == "water")
    assert water["uneven"] is False
    assert water["assessed_for_none"] is True
    assert "nothing to compare" in water["note"]

    # Flood: both assessed both indicators. Even, complete, comparable.
    flood = next(t for t in result["topics"] if t["id"] == "flood")
    assert flood["comparable"] is True
    assert flood["uneven"] is False
    assert flood["note"] == ""


def test_uneven_is_claimed_when_one_site_assessed_more_than_another():
    result = comparison.compare([site("a", "Site A", FLOOD_HEAVY),
                                 site("c", "Site C", BARELY_LOOKED)])
    flood = next(t for t in result["topics"] if t["id"] == "flood")
    assert flood["uneven"] is True
    assert flood["comparable"] is False
    assert "not assessed to the same depth" in flood["note"]
