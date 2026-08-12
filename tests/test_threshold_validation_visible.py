"""
An unvalidated threshold has to say so where someone acts on it.

Coastal's 5 m screening height and its 10-point change threshold are Contour's
judgements, and no coastal engineer has reviewed either. That was recorded in
docs/SCANNER_SPECIFICATION.md, which is the right place for the reasoning and
the wrong place for the disclosure: the person deciding whether to commission a
flood risk assessment is looking at the evidence drawer, not the repository.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import scanners

ROOT = Path(__file__).resolve().parent.parent

UNVALIDATED = ("coastal_low_lying", "coastal_water_extent_change")


@pytest.mark.parametrize("rule_id", UNVALIDATED)
def test_the_coastal_thresholds_declare_themselves_unvalidated(rule_id):
    rule = next(r for r in scanners.COASTAL.rules if r.id == rule_id)
    meta = rule.meta or {}
    assert meta.get("validation_status") == "unvalidated"
    needed = meta.get("validation_needed", "")
    # It has to say what validating it would take, or it is a shrug rather than
    # a capability note.
    assert len(needed) > 60, f"{rule_id}: no statement of what would validate it"
    assert "coastal engineer" in needed.lower()


@pytest.mark.parametrize("rule_id", UNVALIDATED)
def test_unvalidated_is_not_a_substitute_for_product_defined(rule_id):
    """Two different statements, both required. "Product-defined" says we chose
    it; "unvalidated" says nobody qualified has checked it."""
    meta = next(r for r in scanners.COASTAL.rules if r.id == rule_id).meta or {}
    assert "product-defined" in meta.get("threshold_status", "").lower()
    assert meta.get("validation_status") == "unvalidated"


def test_the_evidence_drawer_renders_it():
    """Asserted against the component, because a metadata field nothing reads
    is documentation with extra steps."""
    drawer = (ROOT / "web" / "src" / "components" / "EvidenceDrawer.tsx").read_text()
    assert "validation_status === 'unvalidated'" in drawer
    assert "validation_needed" in drawer


def test_the_drawer_has_no_affirmative_validated_state():
    """The note renders only on an explicit `unvalidated`.

    A missing field must render nothing. Most rules have not recorded the
    question either way, and a UI that showed "validated" for them would be
    claiming a review nobody did — worse than saying nothing. So there must be
    no branch comparing against a positive value.
    """
    drawer = (ROOT / "web" / "src" / "components" / "EvidenceDrawer.tsx").read_text()
    for positive in ("=== 'validated'", '=== "validated"',
                     "!== 'unvalidated'", '!== "unvalidated"'):
        assert positive not in drawer, \
            f"the drawer branches on {positive}, which would assert a review " \
            "nobody performed"


def test_land_and_habitat_are_not_silently_marked_validated():
    """Only claims that can be defended. Nothing here asserts that any other
    scanner's thresholds have been reviewed."""
    for scanner in (scanners.LAND, scanners.HABITAT):
        for rule in scanner.rules:
            status = (rule.meta or {}).get("validation_status")
            assert status in (None, "unvalidated"), \
                f"{rule.id} claims a validation status it cannot support: {status}"
