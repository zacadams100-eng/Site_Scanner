"""
The built scanners, and the isolation between them.

`test_scanner_registry.py` covers the registry's shape. This covers the
product claim: that land, water, ecology and planning are four different
assessments of the same ground, sharing one engine and leaking nothing into
each other.

The isolation tests here matter more than any abstraction. Cross-scanner
leakage is the failure mode a shared engine actually has, and it is silent —
an ecology report carrying a planning finding looks like an ecology finding.

## What changed when the taxonomy landed, and why one test inverted

This file used to assert that **no two scanners share a rule id**. That was
true of land/habitat/coastal, where each scanner owned a disjoint rule set, and
it is deliberately false now: Land is the foundation scanner and keeps the
flood, vegetation, ecology and planning rules that Water, Ecology and Planning
also present.

Deleting the test would have thrown away the guarantee it was protecting, which
was never really "disjoint ids" — it was **two scanners must not be able to
disagree**. So it inverted into something stricter: where two scanners carry
one rule, they must carry *the same object*, and the specialists must still be
disjoint from each other. A copied rule is two thresholds waiting to drift, and
the first symptom would be Land and Water reporting different flood answers for
one site.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import mock_ee_backend
import scanners

BUILT = ("land", "water", "ecology", "planning")
#: The specialists. Land is excluded because it deliberately overlaps all of
#: them — it is the sweep, and they are the lenses.
SPECIALISTS = ("water", "ecology", "planning")
DECLARED = ("development", "infrastructure", "heritage", "market")

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


def test_the_specialist_scanners_ask_different_questions():
    """Three names on one rule set would be the failure this whole
    architecture exists to avoid. No two specialists may share a rule id.

    Land is excluded and overlaps all of them on purpose — see the module note.
    """
    by_scanner = {s: {r.id for r in scanners.resolve(s).rules}
                  for s in SPECIALISTS}
    for a in SPECIALISTS:
        for b in SPECIALISTS:
            if a >= b:
                continue
            shared = by_scanner[a] & by_scanner[b]
            assert not shared, f"{a} and {b} share rule ids: {sorted(shared)}"


def test_where_land_overlaps_a_specialist_it_is_the_same_rule_not_a_copy():
    """The guarantee the disjointness test was really protecting.

    Two scanners may present one check. They may never hold two definitions of
    it: a copied rule is a second threshold, and it drifts silently — Land and
    Water would report different flood answers for one site and nothing would
    say which was right.
    """
    land = {r.id: r for r in scanners.LAND.rules}
    overlaps = 0
    for sid in SPECIALISTS:
        for rule in scanners.resolve(sid).rules:
            if rule.id in land:
                overlaps += 1
                assert rule is land[rule.id], (
                    f"{sid} holds a copy of land's {rule.id!r} rather than the "
                    f"rule itself — two thresholds waiting to disagree")
    assert overlaps > 0, (
        "no overlap found at all, so this test is asserting nothing. Land is "
        "supposed to be the sweep that includes the specialists' checks.")


def test_the_coastal_domain_does_not_restate_a_land_flag():
    """The coastal domain's flagged checks act on factors no land flag uses.

    Land already owns Flood Zone 2 and 3, standing water and seasonal water.
    A coastal check that flagged those again would be one check wearing two
    hats — more findings, no more information. This is about *duplicating a
    judgement*, which stays wrong, and is a different thing from Water
    presenting Land's own flood rule, which is the same judgement shown once.
    """
    land_flag_needs = {n for r in scanners.LAND.rules
                       if r.kind == "flag" for n in r.needs}
    coastal_flag_needs = {n for r in scanners.WATER.rules_in("coastal")
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
    # The package-contributed domains. The core rule set predates this
    # convention and does not carry `not_evidence_of` on every flag — that gap
    # is real, recorded in docs/AUTONOMOUS_CHANGELOG.md, and sweeping it in
    # here under this name would turn a known gap into a red suite rather than
    # into work.
    for scanner, domain in (("ecology", "habitat"), ("water", "coastal")):
        for rule in scanners.resolve(scanner).rules_in(domain):
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


def test_the_same_site_gives_a_different_assessment_per_scanner(client):
    """One geometry, four scanners, four genuinely different reports.

    If two of these came back with the same topics the scanners would be
    branding rather than product. Land overlaps each specialist's *rules* on
    purpose; its topic set is still its own, because it is the union of all
    seven and no specialist carries all seven."""
    reports = {s: _assess(client, s) for s in BUILT}
    topic_sets = {s: {t["id"] for t in r["radar"]["topics"]}
                  for s, r in reports.items()}

    for a in BUILT:
        for b in BUILT:
            if a < b:
                assert topic_sets[a] != topic_sets[b], (
                    f"{a} and {b} report the same topics — they are branding, "
                    f"not two assessments")

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


def test_the_library_shows_four_available_and_four_coming(client):
    cat = _catalog(client, "land")
    built = [s for s in cat["scanners"] if s["implemented"]]
    coming = [s for s in cat["scanners"] if not s["implemented"]]
    assert [s["id"] for s in built] == list(BUILT)
    assert [s["id"] for s in coming] == list(DECLARED)
    # A declared scanner reports zeroes rather than an invented count.
    for s in coming:
        assert s["topic_count"] == 0 and s["factor_count"] == 0
        assert s["rule_count"] == 0
        assert s["status"] == "planned"


def test_a_partial_scanner_is_not_offered_as_complete(client):
    """`implemented` alone would let Water present as finished. Three of the
    four built scanners cover part of their subject, and the card has to carry
    which part — a user reading "Water · available" and getting a clear result
    has been told something untrue about what was asked."""
    cat = _catalog(client, "land")
    by_id = {s["id"]: s for s in cat["scanners"]}
    for sid in ("water", "ecology", "planning"):
        s = by_id[sid]
        assert s["implemented"] is True
        assert s["status"] == "partial"
        gaps = [d for d in s["domains"] if not d["implemented"]]
        assert gaps, f"{sid} is partial but names no gap"
        for d in gaps:
            assert d["blocked_by"], f"{sid}.{d['id']} is a gap with no reason"
    assert by_id["land"]["status"] == "live"
