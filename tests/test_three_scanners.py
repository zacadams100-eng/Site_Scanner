"""
The three launch scanners, and the isolation between them.

`test_scanner_registry.py` covers the registry's shape. This covers the
product claim: that land, habitat and coastal are three different assessments
of the same ground, sharing one engine and leaking nothing into each other.

The isolation tests here matter more than any abstraction. Cross-scanner
leakage is the failure mode a shared engine actually has, and it is silent —
a habitat report carrying a land finding looks like a habitat finding.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import mock_ee_backend
import scanners

BUILT = ("land", "habitat", "coastal")
DECLARED = ("forestry", "water", "terrain")

#: One site, used for every assessment below. The whole point is that the
#: ground does not change while the lens does.
SITE = {
    "type": "Polygon",
    "coordinates": [[[-0.62, 51.22], [-0.62, 51.28], [-0.54, 51.28],
                     [-0.54, 51.22], [-0.62, 51.22]]],
}


@pytest.fixture(scope="module")
def client():
    with TestClient(mock_ee_backend.app) as c:
        yield c


def _catalog(client, scanner):
    r = client.get(f"/api/catalog?scanner={scanner}")
    assert r.status_code == 200, r.text
    return r.json()


def _assess(client, scanner):
    """Run a full assessment of SITE with one scanner."""
    cat = _catalog(client, scanner)
    factors = [f["id"] for f in cat["factors"]][:12]
    r = client.post("/api/series", json={
        "geometry": SITE, "factor_ids": factors, "scanner": scanner})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Three real scanners
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("scanner", BUILT)
def test_each_launch_scanner_is_actually_built(scanner):
    """Registered is not implemented. Each of the three must carry the four
    things that make a scanner a product rather than a name: topics, rules,
    factors and coverage."""
    s = scanners.resolve(scanner)
    assert s.implemented
    assert s.topics, f"{scanner} has no topics"
    assert s.rules, f"{scanner} has no rules"
    assert s.factors, f"{scanner} exposes no factors"
    assert s.coverage is not None, f"{scanner} claims no coverage"
    assert s.coverage_name, f"{scanner} coverage is unnamed"


@pytest.mark.parametrize("scanner", DECLARED)
def test_the_roadmap_scanners_stay_unbuilt(scanner):
    """Building three must not quietly promote a fourth."""
    s = scanners.resolve(scanner)
    assert not s.implemented
    assert s.rules == ()
    assert s.coverage is None


def test_the_three_scanners_ask_different_questions():
    """Three names on one rule set would be the failure this whole
    architecture exists to avoid. No two scanners may share a rule id."""
    by_scanner = {s: {r.id for r in scanners.resolve(s).rules} for s in BUILT}
    for a in BUILT:
        for b in BUILT:
            if a >= b:
                continue
            shared = by_scanner[a] & by_scanner[b]
            assert not shared, f"{a} and {b} share rule ids: {sorted(shared)}"


def test_coastal_does_not_restate_a_land_check():
    """Coastal's flagged checks act on factors no land rule uses.

    Land already owns Flood Zone 2 and 3, standing water and seasonal water.
    A coastal scanner that flagged those again would be one check wearing two
    hats — more findings, no more information."""
    land_flag_needs = {n for r in scanners.LAND.rules
                       if r.kind == "flag" for n in r.needs}
    coastal_flag_needs = {n for r in scanners.COASTAL.rules
                          if r.kind == "flag" for n in r.needs}
    assert coastal_flag_needs
    overlap = coastal_flag_needs & land_flag_needs
    assert not overlap, f"coastal flags reuse land's flag factors: {sorted(overlap)}"


def test_every_scanner_exposes_the_factors_its_rules_need():
    """A rule needing a factor the scanner does not expose can never run, and
    reports 'not assessed' forever without saying why."""
    for scanner in BUILT:
        s = scanners.resolve(scanner)
        for rule in s.rules:
            for need in rule.needs:
                assert s.sees(need), \
                    f"{scanner}: rule {rule.id} needs {need}, not exposed"


def test_every_investigation_a_rule_raises_actually_exists():
    """A rule pointing at an investigation id nobody defined produces a
    finding whose follow-up is a blank."""
    for scanner in BUILT:
        s = scanners.resolve(scanner)
        for rule in s.rules:
            for inv in rule.investigations:
                assert inv in s.investigations, \
                    f"{scanner}: rule {rule.id} raises unknown investigation {inv}"


def test_every_flagged_rule_states_its_threshold_and_its_limits():
    """A flag without a stated threshold is an opinion, and one without
    `not_evidence_of` is a claim with no boundary. Both are the specific
    failure this product is built to prevent."""
    for scanner in ("habitat", "coastal"):
        for rule in scanners.resolve(scanner).rules:
            if rule.kind != "flag":
                continue
            meta = getattr(rule, "meta", None) or {}
            assert meta.get("threshold") is not None, f"{rule.id}: no threshold"
            assert meta.get("threshold_display"), f"{rule.id}: threshold not shown"
            assert meta.get("not_evidence_of"), f"{rule.id}: no stated limit"
            status = (meta.get("threshold_status") or "").lower()
            assert "product-defined" in status, \
                f"{rule.id}: threshold not labelled product-defined"


def test_no_threshold_is_presented_as_regulatory():
    """A product decision described as a legal limit is the one claim this
    codebase must never make."""
    banned = ("statutory", "regulatory requirement", "legal limit",
              "planning requirement", "scientific consensus")
    for scanner in ("habitat", "coastal"):
        for rule in scanners.resolve(scanner).rules:
            meta = getattr(rule, "meta", None) or {}
            blob = " ".join(str(v) for v in meta.values()).lower()
            for phrase in banned:
                # "not a regulatory" is the disclaimer, not the claim.
                assert f"is a {phrase}" not in blob, f"{rule.id}: claims {phrase}"


# ---------------------------------------------------------------------------
# Isolation — the tests that matter more than any abstraction
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("middle", ["habitat", "coastal"])
def test_land_is_identical_before_and_after_another_scanner(client, middle):
    """LAND → X → LAND. The second land assessment must equal the first.

    Shared mutable configuration shows up here and nowhere else, because the
    symptom is not an error — it is a report that is quietly different the
    second time."""
    before = _assess(client, "land")
    _assess(client, middle)
    after = _assess(client, "land")

    assert before["radar"]["topics"] == after["radar"]["topics"]
    assert [f["id"] for f in before["radar"]["flags"]] == \
           [f["id"] for f in after["radar"]["flags"]]
    assert before["radar"]["coverage"] == after["radar"]["coverage"]


def test_the_same_site_gives_three_different_assessments(client):
    """One geometry, three scanners, three genuinely different reports.

    If two of these came back with the same topics the scanners would be
    branding rather than product."""
    reports = {s: _assess(client, s) for s in BUILT}
    topic_sets = {s: {t["id"] for t in r["radar"]["topics"]}
                  for s, r in reports.items()}

    assert topic_sets["land"] != topic_sets["habitat"]
    assert topic_sets["land"] != topic_sets["coastal"]
    assert topic_sets["habitat"] != topic_sets["coastal"]

    # And each reports only its own scanner's topics.
    for scanner, topics in topic_sets.items():
        declared = set(scanners.resolve(scanner).topics)
        assert topics <= declared, \
            f"{scanner} reported topics it does not declare: {topics - declared}"


def test_no_finding_leaks_between_scanners(client):
    """A rule id from one scanner appearing in another's report is the leak
    this architecture is built to make impossible."""
    for scanner in BUILT:
        report = _assess(client, scanner)
        own = {r.id for r in scanners.resolve(scanner).rules}
        for finding in report["radar"]["flags"]:
            assert finding["id"] in own, \
                f"{scanner} reported {finding['id']}, which is not its rule"


def test_an_unassessed_topic_is_never_reported_as_clear(client):
    """The distinction the whole evidence model rests on: a check that could
    not run is not a check that passed."""
    for scanner in BUILT:
        radar_block = _assess(client, scanner)["radar"]
        for topic in radar_block["topics"]:
            if topic["state"] != "not_assessed":
                continue
            # Not assessed means nothing was checked and nothing was cleared.
            assert topic["checked"] == [], \
                f"{scanner}/{topic['id']}: not assessed but reports checks cleared"
            assert topic["coverage"]["assessed"] == 0, \
                f"{scanner}/{topic['id']}: not assessed but claims coverage"
            # And it says why, per check, rather than going quiet.
            for check in topic["checks"]:
                assert check["assessed"] is False
                assert check.get("reason"), \
                    f"{scanner}/{topic['id']}: unassessed check gives no reason"


# ---------------------------------------------------------------------------
# API identity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("scanner", BUILT)
def test_the_api_returns_the_scanner_it_was_asked_for(client, scanner):
    cat = _catalog(client, scanner)
    assert cat["scanner"]["id"] == scanner
    assert cat["scanner"]["implemented"] is True
    assert cat["scanner"]["name"] == scanners.resolve(scanner).name
    assert cat["coverage"]["name"] == scanners.resolve(scanner).coverage_name
    # A scanner sees only its own factors.
    declared = set(scanners.resolve(scanner).factors)
    assert {f["id"] for f in cat["factors"]} <= declared


def test_the_library_shows_three_available_and_three_coming(client):
    cat = _catalog(client, "land")
    built = [s for s in cat["scanners"] if s["implemented"]]
    coming = [s for s in cat["scanners"] if not s["implemented"]]
    assert [s["id"] for s in built] == list(BUILT)
    assert [s["id"] for s in coming] == list(DECLARED)
    # A declared scanner reports zeroes rather than an invented count.
    for s in coming:
        assert s["topic_count"] == 0 and s["factor_count"] == 0
