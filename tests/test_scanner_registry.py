"""
The scanner registry, and the isolation it has to guarantee.

The architecture claim being tested is narrow and checkable: **a scanner is a
configuration, and the engine has no branch that knows which one is running.**

The tests that matter most are the isolation ones. Two scanners in one process
sharing anything mutable is the failure this design exists to prevent, and it
would show up as a land request behaving differently after a habitat request —
which is exactly what `test_land_is_unchanged_by_a_habitat_request_between_it`
asserts.
"""

import pytest

import catalog
import radar
import scanners

GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[
        [-0.58, 51.235], [-0.56, 51.235], [-0.56, 51.245],
        [-0.58, 51.245], [-0.58, 51.235],
    ]],
}


# ---------------------------------------------------------------------------
# R1 — the registry
# ---------------------------------------------------------------------------
def test_six_verticals_are_registered():
    """Six, because the shape of the product is part of what the library says:
    two live and four declared reads as "platform, early", where two cards
    reads as "two tools"."""
    assert set(scanners.ids()) == {"land", "habitat", "coastal", "forestry",
                                   "water", "terrain"}


def test_land_is_built_from_the_existing_configuration_not_copied():
    """A copy would drift, and the first symptom would be a rule that runs in
    tests and not in production. The registry is a lens over what exists."""
    land = scanners.resolve("land")
    assert land.topics is radar.TOPICS
    assert land.investigations is radar.INVESTIGATIONS
    assert tuple(land.rules) == tuple(radar.RULES)
    assert land.coverage is catalog.ENGLAND_BBOX
    assert len(land.factors) == len(catalog.FACTORS)


def test_an_unbuilt_scanner_says_so_rather_than_looking_empty():
    """A scanner with no rules is registered and unbuilt. Saying so is more
    useful than an empty report that reads as a clean subject.

    Coastal only: habitat is scanner #2 and is now built. That this test needed
    narrowing rather than deleting is the point — the registry distinguishes
    declared from built, and one of the three has crossed over.
    """
    s = scanners.resolve("coastal")
    assert s.implemented is False
    assert s.rules == ()
    assert s.topics == {}
    assert s.factors == ()


def test_habitat_is_built_and_scoped():
    """Scanner #2: six factors of twenty-seven, five topics, one flagged rule
    and five informational readings. See HABITAT_SCANNER.md."""
    h = scanners.resolve("habitat")
    assert h.implemented is True
    assert set(h.factors) == {"ndvi", "ndmi", "evi", "lc_tree_pct",
                              "lc_dominant", "water_occurrence"}
    flags = [r for r in h.rules if r.kind == "flag"]
    assert len(flags) == 1, "one defensible threshold, not ten arbitrary ones"
    assert flags[0].id == "habitat_vegetation_decline"

    # Regional-resolution sources are excluded on purpose: a 9 km ERA5 pixel
    # over a 20 ha reserve describes a county, not a parcel.
    for regional in ("air_temp_mean", "lst_day", "soil_moisture"):
        assert not h.sees(regional)


def test_an_unbuilt_scanner_has_no_coverage_rather_than_a_borrowed_one():
    """`None` means no coverage established — distinct from "covers nowhere"
    and from silently inheriting England."""
    assert scanners.resolve("coastal").coverage is None
    assert scanners.resolve("land").coverage is not None
    assert scanners.resolve("habitat").coverage is not None


def test_resolve_defaults_to_land_and_rejects_the_unknown():
    assert scanners.resolve(None).id == "land"
    assert scanners.resolve("LAND").id == "land"
    with pytest.raises(scanners.UnknownScanner):
        scanners.resolve("mine")


def test_a_scanner_is_frozen():
    """Resolved per request and shared across them: a mutable config is a
    cross-request leak waiting to happen."""
    with pytest.raises(Exception):
        scanners.resolve("land").id = "habitat"   # type: ignore[misc]


# ---------------------------------------------------------------------------
# The engine has no scanner branch
# ---------------------------------------------------------------------------
def test_no_shared_module_branches_on_a_scanner_id():
    """`if scanner == "habitat"` in the engine would mean the abstraction had
    failed and a fork had begun. Checked structurally, across every shared
    module rather than only the one being edited."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    shared = ["radar.py", "evidence.py", "investigation.py", "brief.py",
              "claims.py", "comparison.py", "insights.py"]
    for name in shared:
        text = (root / name).read_text(encoding="utf-8").lower()
        for sid in ("habitat", "coastal"):
            assert f'== "{sid}"' not in text, f"{name} branches on {sid}"
            assert f"== '{sid}'" not in text, f"{name} branches on {sid}"
            assert f'scanner_id == "{sid}"' not in text


def test_the_engine_does_not_import_the_registry():
    """One-way knowledge. The registry composes the engine; the engine must not
    reach back for a scanner, which is what would let a branch creep in."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    for name in ("radar.py", "evidence.py", "investigation.py", "brief.py",
                 "claims.py"):
        text = (root / name).read_text(encoding="utf-8")
        assert "import scanners" not in text, f"{name} imports the registry"


# ---------------------------------------------------------------------------
# R4 — identity in the API, and isolation between requests
# ---------------------------------------------------------------------------
def _series(client, scanner=None, factors=("ndvi",)):
    body = {"geometry": GEOMETRY, "factor_ids": list(factors)}
    if scanner is not None:
        body["scanner"] = scanner
    return client.post("/api/series", json=body)


def test_a_request_without_a_scanner_still_works(mock_client):
    """Every existing client predates scanner identity and means land."""
    assert _series(mock_client).status_code == 200


def test_land_is_explicit_and_identical_to_the_default(mock_client):
    default = _series(mock_client).json()
    named = _series(mock_client, "land").json()
    assert {t["id"] for t in default["radar"]["topics"]} == \
           {t["id"] for t in named["radar"]["topics"]}


def test_an_unbuilt_scanner_is_refused_with_a_reason(mock_client):
    """Not an empty 200. A report with no findings from a scanner that cannot
    assess anything is indistinguishable from a clean subject."""
    r = _series(mock_client, "coastal")
    assert r.status_code == 422
    assert "does not cover" in r.json()["detail"]


def test_an_unknown_scanner_is_a_clear_error(mock_client):
    r = _series(mock_client, "mine")
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "Unknown scanner" in detail
    # Names what to send instead, rather than only what was wrong.
    assert "land" in detail and "habitat" in detail


def test_land_is_unchanged_by_a_habitat_request_between_it(mock_client):
    """The isolation test. Shared mutable configuration would show up here as
    a land report that changed after another scanner ran."""
    before = _series(mock_client).json()
    _series(mock_client, "habitat")           # refused, but it ran the path
    _series(mock_client, "coastal")
    after = _series(mock_client).json()

    assert before["radar"]["topics"] == after["radar"]["topics"]
    assert before["radar"]["coverage"]["relevant"] == \
           after["radar"]["coverage"]["relevant"]
    assert [f["id"] for f in before["radar"]["flags"]] == \
           [f["id"] for f in after["radar"]["flags"]]


def test_switching_scanners_needs_no_monkeypatching(mock_client):
    """The measurement that made this work necessary: the multi-scanner
    experiment had to monkeypatch `radar.INVESTIGATIONS` to run a second
    domain. Nothing here patches anything."""
    r = _series(mock_client, "land")
    assert r.status_code == 200
    assert radar.INVESTIGATIONS is scanners.resolve("land").investigations


# ---------------------------------------------------------------------------
# The scanner library's contract with the frontend
# ---------------------------------------------------------------------------
def test_the_catalogue_lists_every_scanner_with_its_availability(mock_client):
    """One source of truth. The library renders this list; a frontend roadmap
    array would drift, and the first symptom would be a card offering a
    scanner the API refuses."""
    body = mock_client.get("/api/catalog").json()
    listed = {s["id"]: s for s in body["scanners"]}

    assert set(listed) == set(scanners.ids())
    assert len(listed) == 6, "six verticals, so the shape of the product shows"
    assert {i for i, s in listed.items() if s["implemented"]} == {"land", "habitat"}

    for s in listed.values():
        assert s["name"] and s["subject"], "a card without a subject is a logo"


def test_a_declared_scanner_is_registered_but_carries_no_content():
    """Registering is not implementing. The four future verticals exist so the
    roadmap has one source of truth, and carry nothing that could be mistaken
    for functionality."""
    for sid in ("coastal", "forestry", "water", "terrain"):
        s = scanners.resolve(sid)
        assert s.implemented is False
        assert (s.topics, s.rules, s.investigations, s.factors) == ({}, (), {}, ())
        assert s.coverage is None
