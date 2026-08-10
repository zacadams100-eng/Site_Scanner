"""
Judgement-shaped factors stay unimplemented.

`docs/FACTOR_CLASSIFICATION.md` classifies the 26 factors whose names read as
conclusions into `MEASUREMENT`, `DERIVED_METRIC` and `JUDGEMENT`. This file
enforces the only part of that classification that is a hard rule.

## Why this exists rather than a rename

A differentiation audit found that `catalog.py` declares five factors that
answer "is this site good for X" — the one question the product exists not to
answer. They are all generated demo data today, so nothing is claimed about any
site, and the temptation is to leave them.

The reason not to leave them is `EM7`. `tests/test_evidence_model.py` bans
`score`, `suitability`, `grade` and others as **payload keys**, and
`radar.assess()` puts factor ids into payload keys. The moment
`solar_farm_suitability` becomes real and a rule reads it, EM7 fails — on a
name that is, from the implementer's point of view, perfectly reasonable. The
obvious fix under deadline is to shorten the banned list, and that is how a
load-bearing invariant quietly dies.

So the collision is prevented from the other side. EM7 is untouched.
"""

import catalog
import radar
import routes_catalog


#: Factors whose definition requires Contour to decide what counts as *good*.
#: Each is declared in `catalog.py` as several inputs "combined" into a 0–1
#: fitness-for-purpose, which is a recommendation however it is packaged.
#:
#: Their inputs already exist separately and really are measurements —
#: `solar_ghi`, `slope_mean`, `grid_headroom`, `flood_zone3_pct`. Showing the
#: components and letting a professional weigh them is the honest form of the
#: same information.
JUDGEMENT_FACTORS = frozenset({
    "solar_farm_suitability",
    "battery_site_suitability",
    "woodland_creation_suitability",
    "warehouse_suitability",
    "data_centre_suitability",
})


def test_the_judgement_set_still_matches_the_catalogue():
    """A guard on the guard.

    If someone adds a sixth `*_suitability` factor, this list silently stops
    covering the catalogue and every assertion below keeps passing while
    protecting less. Failing here is the signal to classify the new factor in
    `docs/FACTOR_CLASSIFICATION.md`, not to extend the set without thinking.
    """
    declared = {f["id"] for f in catalog.FACTORS if "suitability" in f["id"]}
    assert declared == JUDGEMENT_FACTORS, (
        "a suitability-shaped factor appeared that is not classified; see "
        "docs/FACTOR_CLASSIFICATION.md"
    )


def test_no_judgement_factor_is_implemented():
    """They may exist in the catalogue as declared-but-unbuilt. They may not
    return numbers, because a number here is a recommendation."""
    live = JUDGEMENT_FACTORS & set(routes_catalog.REAL_SERIES)
    assert not live, f"a suitability factor went live: {sorted(live)}"


def test_no_rule_reads_a_judgement_factor():
    """The direct route to a finding, closed.

    A rule reading `solar_farm_suitability` would turn a recommendation into a
    flag, an investigation and a line in a professional's report — laundering
    it through the whole evidence chain, which is exactly what makes the
    evidence chain worth having.
    """
    offenders = [(r.id, n) for r in radar.RULES
                 for n in r.needs if n in JUDGEMENT_FACTORS]
    assert not offenders, f"a rule reads a suitability factor: {offenders}"


def test_em7_is_not_the_thing_protecting_us_here():
    """Documents the relationship between the two tests, executably.

    EM7 bans these words in payload keys and would eventually catch a live
    suitability factor — but only *after* someone implemented it, and its
    failure would read as a false positive on a sensible name. This test fails
    earlier and for a reason the implementer can act on.
    """
    from tests.test_evidence_model import BANNED
    assert "suitability" in BANNED, (
        "EM7 no longer bans 'suitability' — if that was deliberate, the "
        "reasoning belongs in EVIDENCE_MODEL.md, not in a quiet edit"
    )
    # And the factors this file guards would indeed trip it, which is why they
    # are stopped before they can.
    assert all(any(b in fid for b in BANNED) for fid in JUDGEMENT_FACTORS)
