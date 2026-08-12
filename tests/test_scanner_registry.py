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
def test_eight_scanners_are_registered_in_four_families():
    """The shape of the product is part of what the library says.

    Six flat verticals became eight scanners in four families, and the
    regrouping was not cosmetic: it moved `terrain`, `coastal`, `habitat` and
    `forestry` from top-level products to domains inside the scanner that owns
    their subject, and promoted `planning` from a topic buried in land to a
    scanner of its own.
    """
    assert set(scanners.ids()) == {
        "land", "water", "ecology",
        "planning", "development", "infrastructure",
        "heritage", "market",
    }
    assert {f.id for f in scanners.FAMILIES} == {
        "foundation", "development", "culture", "economics"}


def test_every_scanner_belongs_to_a_registered_family():
    """A family id that names nothing would put a scanner in a section the
    library does not render — it would simply vanish from the front door."""
    known = {f.id for f in scanners.FAMILIES}
    for sid in scanners.ids():
        assert scanners.resolve(sid).family in known


def test_families_partition_the_registry_with_nothing_lost():
    """`families()` is what the library renders. If it dropped a scanner, the
    product would be missing from its own catalogue with no error anywhere."""
    grouped = [s.id for _, ss in scanners.families() for s in ss]
    assert sorted(grouped) == sorted(scanners.ids())
    assert len(grouped) == len(set(grouped)), "a scanner listed in two families"


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

    This test has now been narrowed three times — habitat crossed over as
    scanner #2, coastal as #3, planning as #4 — and that it narrows rather than
    breaks is the point: the registry distinguishes declared from built, and
    the distinction survives scanners moving between the two.
    """
    for sid in ("development", "infrastructure", "heritage", "market"):
        s = scanners.resolve(sid)
        assert s.implemented is False
        assert s.status == "planned"
        assert s.rules == ()
        assert s.topics == {}
        assert s.factors == ()
        # Declared, not absent: it still has domains, and each says what is
        # missing. That is the difference between a roadmap and a silence.
        assert s.domains, f"{sid} declares nothing at all"
        assert all(d.blocked_by for d in s.domains)


def test_ecology_is_built_from_the_habitat_domain_and_scoped():
    """Habitat is a domain of Ecology, not a scanner. Its content is unchanged
    by the move: the same six factors, the same single flagged threshold.

    That the *content* survives a taxonomy change is the thing worth asserting.
    A restructure that quietly dropped a rule would be indistinguishable from
    one that worked, right up until a site was reported clear.
    """
    e = scanners.resolve("ecology")
    assert e.implemented is True
    habitat = {d.id: d for d in e.domains}["habitat"]
    assert habitat.implemented and habitat.package == "habitat.rules"

    for fid in ("ndvi", "ndmi", "evi", "lc_tree_pct", "lc_dominant",
                "water_occurrence"):
        assert e.sees(fid)
    assert "habitat_vegetation_decline" in {r.id for r in e.rules}

    # Regional-resolution sources are excluded on purpose: a 9 km ERA5 pixel
    # over a 20 ha reserve describes a county, not a parcel.
    for regional in ("air_temp_mean", "lst_day", "soil_moisture"):
        assert not e.sees(regional)


def test_water_is_built_from_the_coastal_domain_and_the_flood_topics():
    """Coastal is a domain of Water. Its two flagged checks survive the move,
    and they now sit beside the flood and surface-water rules that were only
    ever reachable through Land."""
    w = scanners.resolve("water")
    assert w.implemented is True
    assert {"coastal_low_lying", "coastal_water_extent_change"} <= \
        {r.id for r in w.rules}
    # The flood rules are the same objects Land runs, selected by topic.
    land_rules = {id(r) for r in scanners.resolve("land").rules}
    flood = [r for r in w.rules if r.topic == "flood"]
    assert flood, "water does not reach the flood rules"
    for r in flood:
        assert id(r) in land_rules, (
            "water holds a copy of a flood rule rather than the rule itself; "
            "two copies are two thresholds waiting to disagree")


def test_planning_was_promoted_from_a_topic_to_a_scanner():
    """Seven planning rules ran inside Land before the taxonomy existed.

    This scanner is not new evidence and must not claim to be — it is the same
    checks, reachable by someone whose question is planning rather than land.
    """
    p = scanners.resolve("planning")
    assert p.implemented is True
    assert p.status == "partial", "applications and policy are not built"
    land_planning = [r for r in scanners.resolve("land").rules
                     if r.topic == "planning"]
    assert {r.id for r in p.rules} == {r.id for r in land_planning}
    assert len(p.rules) == 7


def test_an_unbuilt_scanner_has_no_coverage_rather_than_a_borrowed_one():
    """`None` means no coverage established — distinct from "covers nowhere"
    and from silently inheriting England."""
    for planned in ("development", "infrastructure", "heritage", "market"):
        assert scanners.resolve(planned).coverage is None
        assert scanners.resolve(planned).coverage_name == ""
    for built in ("land", "water", "ecology", "planning"):
        assert scanners.resolve(built).coverage is not None


# ---------------------------------------------------------------------------
# Domains, status and migration
# ---------------------------------------------------------------------------
def test_status_is_derived_from_the_domains_rather_than_asserted():
    """A stored status is a claim someone has to remember to update.

    Derived, it cannot go stale — and it moves in the honest direction: a
    scanner that declares a new domain drops to `partial` the moment it does,
    rather than staying `live` until someone notices.
    """
    assert scanners.resolve("land").status == "live"
    for partial in ("water", "ecology", "planning"):
        s = scanners.resolve(partial)
        assert s.status == "partial"
        assert s.declared_domains, "partial with nothing outstanding"
        assert s.built_domains, "partial with nothing built"
    assert scanners.resolve("heritage").status == "planned"


def test_every_declared_domain_says_what_is_missing():
    """`blocked_by` is required, and it is the whole value of declaring one.

    "Groundwater: coming soon" is not something a professional can plan
    around. "No groundwater source is integrated; the EA publishes aquifer
    designations and source protection zones, neither ingested" tells them to
    look elsewhere for that question today.
    """
    for sid in scanners.ids():
        for d in scanners.resolve(sid).declared_domains:
            assert len(d.blocked_by) > 40, (
                f"{sid}.{d.id} does not say what is actually missing")
            assert d.name and d.subject


def test_retired_scanner_ids_still_resolve_to_the_scanner_that_absorbed_them():
    """A saved permalink, a stored report or an API client written against the
    old vocabulary keeps working. A taxonomy change that breaks every existing
    link is a migration the user pays for."""
    assert scanners.resolve("habitat").id == "ecology"
    assert scanners.resolve("forestry").id == "ecology"
    assert scanners.resolve("coastal").id == "water"
    assert scanners.resolve("terrain").id == "land"
    assert scanners.resolve("COASTAL").id == "water"


def test_an_alias_is_a_door_and_not_a_product():
    """Aliases resolve and are not offered: absent from `ids()`, so absent
    from the library, the catalogue and the error message that lists what to
    send. A retired product that still appears in the catalogue has not been
    retired."""
    for alias in scanners.ALIASES:
        assert alias not in scanners.ids()
        assert scanners.resolve(alias).id != alias


def test_a_domain_absorbed_from_a_scanner_kept_that_scanner_s_subject():
    """The migration is only honest if the subject survived it. Each retired
    id must name a domain that actually exists in its new home."""
    absorbed = {"habitat": "habitat", "coastal": "coastal", "terrain": "terrain",
                "forestry": "woodland"}
    for alias, domain_id in absorbed.items():
        s = scanners.resolve(alias)
        assert domain_id in {d.id for d in s.domains}, (
            f"{alias} was absorbed into {s.id}, which has no {domain_id!r} "
            f"domain — the subject was dropped rather than moved")


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
    r = _series(mock_client, "heritage")
    assert r.status_code == 422
    assert "does not cover" in r.json()["detail"]


def test_an_unknown_scanner_is_a_clear_error(mock_client):
    r = _series(mock_client, "mine")
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "Unknown scanner" in detail
    # Names what to send instead, rather than only what was wrong.
    assert "land" in detail and "ecology" in detail


def test_land_is_unchanged_by_another_scanners_request_between_it(mock_client):
    """The isolation test. Shared mutable configuration would show up here as
    a land report that changed after another scanner ran."""
    before = _series(mock_client).json()
    _series(mock_client, "ecology")           # refused, but it ran the path
    _series(mock_client, "water")
    _series(mock_client, "planning")
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
    assert len(listed) == 8, "eight scanners, so the shape of the product shows"
    assert {i for i, s in listed.items() if s["implemented"]} == \
        {"land", "water", "ecology", "planning"}

    for s in listed.values():
        assert s["name"] and s["subject"], "a card without a subject is a logo"
        assert s["family"] in {f.id for f in scanners.FAMILIES}
        assert s["status"] in {"live", "partial", "planned"}


def test_the_catalogue_carries_the_families_the_library_renders(mock_client):
    """The library's sections come from the registry too. A grouping written
    into a component is a second description of the product, and the
    frontend's copy is the one that gets forgotten."""
    body = mock_client.get("/api/catalog").json()
    families = body["families"]
    assert [f["id"] for f in families] == [f.id for f in scanners.FAMILIES]
    listed = {s["id"] for s in body["scanners"]}
    assert {sid for f in families for sid in f["scanners"]} == listed


def test_the_catalogue_reports_the_coverage_gap_per_scanner(mock_client):
    """A partial scanner has to say which half it is. Otherwise a clear result
    from Water reads as "no water issues" when it means "no *flood, surface
    water or coastal* issues, and groundwater was never asked"."""
    body = mock_client.get("/api/catalog").json()
    water = {s["id"]: s for s in body["scanners"]}["water"]
    assert water["status"] == "partial"
    built = {d["id"] for d in water["domains"] if d["implemented"]}
    unbuilt = {d["id"]: d for d in water["domains"] if not d["implemented"]}
    assert "coastal" in built and "flood" in built
    assert "groundwater" in unbuilt
    assert unbuilt["groundwater"]["blocked_by"], "a gap with no reason given"


def test_a_declared_scanner_is_registered_but_carries_no_content():
    """Registering is not implementing. The declared scanners exist so the
    roadmap has one source of truth, and carry nothing that could be mistaken
    for functionality."""
    for sid in ("development", "infrastructure", "heritage", "market"):
        s = scanners.resolve(sid)
        assert s.implemented is False
        assert (s.topics, s.rules, s.investigations, s.factors) == ({}, (), {}, ())
        assert s.coverage is None
