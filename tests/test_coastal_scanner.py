"""
Coastal Scanner — the rules, the thresholds, and what they refuse to claim.

`test_three_scanners.py` proves the three scanners are isolated. This proves
coastal's own checks actually fire, because in the demo backend none of its
factors has a live source and every topic reports `not_assessed` — which is
correct behaviour and completely untested behaviour if nothing ever installs
a real one.

So the thresholds are driven directly here, on both sides of the line.
"""

from __future__ import annotations

import pytest

import radar
import scanners
from coastal.rules import (
    COASTAL_LOW_LYING_INVESTIGATION_THRESHOLD,
    COASTAL_WATER_EXTENT_CHANGE_INVESTIGATION_THRESHOLD,
    build,
)

GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[
        [-0.58, 51.235], [-0.56, 51.235], [-0.56, 51.245],
        [-0.58, 51.245], [-0.58, 51.235],
    ]],
}


def _rules():
    """Coastal's rules as engine rules, exactly as the registry builds them."""
    return {r.id: r for r in build(radar.Rule, radar.Insufficient)}


def _series(**values):
    """A series payload in the shape a rule's `test` receives."""
    return {factor: {"points": [{"t": "2024-06", "value": v}]}
            for factor, v in values.items()}


def _run(rule_id, **values):
    return _rules()[rule_id].test(_series(**values))


# ---------------------------------------------------------------------------
# Low-lying exposure
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("elevation", [0.4, 2.0, 5.0])
def test_low_ground_is_flagged_at_and_below_the_threshold(elevation):
    found = _run("coastal_low_lying", elevation_min=elevation)
    assert found is not None, f"{elevation} m should flag"
    assert "above ordnance datum" in found["text"]
    assert found["evidence"]["elevation_min"] == elevation
    assert "5 m" in found["evidence"]["threshold"]


@pytest.mark.parametrize("elevation", [5.1, 12.0, 240.0])
def test_higher_ground_is_not_flagged(elevation):
    assert _run("coastal_low_lying", elevation_min=elevation) is None


def test_the_low_lying_threshold_is_the_named_constant():
    """The boundary is exactly the constant, so changing the product decision
    is one edit rather than a hunt through prose."""
    at = _run("coastal_low_lying",
              elevation_min=COASTAL_LOW_LYING_INVESTIGATION_THRESHOLD)
    just_above = _run("coastal_low_lying",
                      elevation_min=COASTAL_LOW_LYING_INVESTIGATION_THRESHOLD + 0.01)
    assert at is not None and just_above is None


def test_severity_does_not_climb_as_the_ground_gets_lower():
    """A severity scaling with elevation would be this rule estimating flood
    risk — the exact thing its own `not_evidence_of` says it cannot do."""
    low = _run("coastal_low_lying", elevation_min=0.2)
    higher = _run("coastal_low_lying", elevation_min=4.9)
    assert low["severity"] == higher["severity"] == "medium"


def test_missing_elevation_is_not_assessed_rather_than_clear():
    """No observation must never become 'no problem'."""
    result = _rules()["coastal_low_lying"].test({})
    assert isinstance(result, radar.Insufficient)
    assert "elevation" in str(result.reason or result).lower()


# ---------------------------------------------------------------------------
# Surface water extent change
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("change,word", [(24.0, "gained"), (-31.0, "lost")])
def test_a_material_change_in_water_extent_is_flagged(change, word):
    found = _run("coastal_water_extent_change", water_change=change)
    assert found is not None
    assert word in found["text"]
    assert found["evidence"]["water_change"] == change


@pytest.mark.parametrize("change", [0.0, 4.0, -9.9])
def test_small_movements_are_not_flagged(change):
    assert _run("coastal_water_extent_change", water_change=change) is None


def test_the_change_threshold_is_symmetric():
    """Gain and loss are both worth explaining. A threshold that only fired on
    loss would be a scanner with an opinion about which direction is bad."""
    t = COASTAL_WATER_EXTENT_CHANGE_INVESTIGATION_THRESHOLD
    assert _run("coastal_water_extent_change", water_change=t) is not None
    assert _run("coastal_water_extent_change", water_change=-t) is not None


def test_water_change_is_never_described_as_erosion():
    """The single most tempting false claim this scanner could make."""
    found = _run("coastal_water_extent_change", water_change=30.0)
    blob = (found["text"] + str(found["evidence"])).lower()
    for word in ("erosion rate", "retreat", "shoreline moved", "coastline lost"):
        assert word not in blob, f"claims {word}"


def test_missing_water_change_is_not_assessed():
    result = _rules()["coastal_water_extent_change"].test({})
    assert isinstance(result, radar.Insufficient)


# ---------------------------------------------------------------------------
# Readings carry no threshold
# ---------------------------------------------------------------------------

def test_informational_readings_declare_no_threshold_and_raise_nothing():
    """A reading with a threshold is a flag that forgot to say so."""
    for rule in build(radar.Rule, radar.Insufficient):
        if rule.kind != "info":
            continue
        assert rule.investigations == (), f"{rule.id} raises an investigation"
        meta = getattr(rule, "meta", None) or {}
        assert not meta.get("threshold"), f"{rule.id} carries a threshold"


def test_a_reading_with_no_observation_stays_silent():
    for rule in build(radar.Rule, radar.Insufficient):
        if rule.kind == "info":
            assert rule.test({}) is None


# ---------------------------------------------------------------------------
# What the scanner says it cannot do
# ---------------------------------------------------------------------------

def test_both_flags_state_what_they_do_not_establish():
    # Scoped to the coastal domain. Coastal became a domain of Water, which
    # also carries the flood and surface-water rules Land has always run —
    # those are a different provenance with their own conventions, and sweeping
    # them here would test the wrong thing under this name.
    for rule in scanners.WATER.rules_in("coastal"):
        if rule.kind != "flag":
            continue
        limit = (rule.meta or {}).get("not_evidence_of", "")
        assert len(limit) > 80, f"{rule.id}: limit is too thin to be a boundary"


def test_the_scanner_does_not_claim_to_verify_a_site_is_coastal():
    """There is no coastline dataset in this repository, so 'is this coastal'
    is the operator's judgement. The module says so where someone will read
    it."""
    import coastal.rules as mod
    doc = (mod.__doc__ or "").lower()
    assert "cannot verify" in doc
    assert "shoreline" in doc


def test_coastal_thresholds_are_labelled_product_defined():
    # Scoped to the coastal domain. Coastal became a domain of Water, which
    # also carries the flood and surface-water rules Land has always run —
    # those are a different provenance with their own conventions, and sweeping
    # them here would test the wrong thing under this name.
    for rule in scanners.WATER.rules_in("coastal"):
        if rule.kind != "flag":
            continue
        status = (rule.meta or {}).get("threshold_status", "").lower()
        assert "product-defined" in status
        assert "not a regulatory" in status or "not an erosion" in status
