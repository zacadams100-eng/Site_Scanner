"""Whether a factor is cleared to reach a paying customer.

`catalog.py` already records a licence and an attribution for every base, and
`open_data.py`/`ee_series.py` record whether the numbers have been verified
against a live service. Neither answers the question a commercial product has
to answer before it invoices anybody: **are we allowed to sell this?**

That is a different axis from "is it real". A factor can be verified, accurate
and well-attributed and still be one this product may not put in a customer
report — Earth Engine is registered non-commercial, and Sentinel-2's licence
is recorded as CC BY-SA 3.0 IGO with `commercial="verify"`, where share-alike
on a derived commercial product would be a genuine constraint.

## The four states

`cleared`      the recorded licence appears to permit commercial use, and
               nothing about this project's use of it is outstanding
`conditional`  permitted subject to something unresolved — an unconfirmed
               licence, an attribution condition, a registration tier
`unknown`      nobody has established the position
`blocked`      must not reach a customer-facing output

## What this module does and does not claim

It reports **what the repository asserts**, not what the law says. Every
licence string here came from `catalog.py`, which was written from dataset
documentation by somebody who is not a lawyer, and this environment cannot
reach a single licence page to check any of it (`scripts/verify_licensing.py`
exists to do that from a machine with internet).

So nothing here should be read as "this is legal". The strongest claim
available is "the licence we recorded appears to permit this, and no human has
confirmed it".

## Why `blocked` is enforced in code rather than written in a document

A licensing note in a markdown file does not stop a factor being served. This
does: a blocked base's factors are refused at the API boundary, so the failure
mode is a visible "unavailable" rather than a number in a PDF that should
never have been generated.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

CLEARED = "cleared"
CONDITIONAL = "conditional"
UNKNOWN = "unknown"
BLOCKED = "blocked"

ORDER = {CLEARED: 0, CONDITIONAL: 1, UNKNOWN: 2, BLOCKED: 3}


# Bases whose commercial position is unresolved, with the specific reason.
#
# These are `conditional`, not `blocked` — blocking Sentinel-2 would remove
# NDVI, which is the one factor in this catalogue ever verified by hand, and
# that is a product decision for the owner rather than one to take in an audit.
# `LEGAL_ACTION_PLAN.md` carries it as a launch blocker with the arithmetic.
CONDITIONS: Dict[str, str] = {
    "sentinel2_sr":
        "licence recorded as CC BY-SA 3.0 IGO with commercial='verify'. "
        "Share-alike on a commercial derived product would be a real "
        "constraint. docs/licensing/ has a drafted ESA enquiry, unsent.",
    "sentinel1_sar":
        "same recorded licence and the same open question as sentinel2_sr.",
    "os_ngd_buildings":
        "OS Data Hub terms vary by plan; the free tier's commercial position "
        "for a paid downstream product is not established here.",
    "neso_grid":
        "terms vary by distribution network operator; no single position.",
}

# Bases that must not reach a customer-facing output, with the reason.
#
# Empty today, deliberately. Nothing in this catalogue has been *established*
# as prohibited — the risks are unresolved rather than settled — and marking a
# source blocked on suspicion would take a working factor away on no evidence,
# which is the mirror image of shipping one on no evidence.
BLOCKED_BASES: Dict[str, str] = {}


def _catalog():
    import catalog
    return catalog


def status_for_base(base_id: str) -> str:
    """The commercial-clearance state of one base."""
    catalog = _catalog()
    base = catalog.BASE_BY_ID.get(base_id)
    if base is None:
        return UNKNOWN
    if base_id in BLOCKED_BASES:
        return BLOCKED
    if base_id in CONDITIONS:
        return CONDITIONAL

    commercial = (base.get("commercial") or "").lower()
    if commercial == "yes":
        return CLEARED
    if commercial in ("verify", "conditional"):
        return CONDITIONAL
    return UNKNOWN


def reason_for_base(base_id: str) -> Optional[str]:
    if base_id in BLOCKED_BASES:
        return BLOCKED_BASES[base_id]
    if base_id in CONDITIONS:
        return CONDITIONS[base_id]
    return None


def status_for_factor(factor_id: str) -> str:
    catalog = _catalog()
    factor = catalog.FACTOR_BY_ID.get(factor_id)
    if factor is None:
        return UNKNOWN
    return status_for_base(factor.get("base", ""))


def is_blocked(factor_id: str) -> bool:
    """The one question the request path asks.

    Kept deliberately narrow. A `conditional` factor still serves — the
    condition is a thing for a human to resolve, not a reason to withhold a
    number the product currently depends on — and conflating the two would
    make this switch too blunt to ever be turned on.
    """
    return status_for_factor(factor_id) == BLOCKED


def clearance(factor_id: str) -> Dict[str, Any]:
    """Everything a caller needs to say why a factor is or is not cleared."""
    catalog = _catalog()
    factor = catalog.FACTOR_BY_ID.get(factor_id) or {}
    base_id = factor.get("base", "")
    base = catalog.BASE_BY_ID.get(base_id, {})
    state = status_for_base(base_id)
    return {
        "status": state,
        "base": base_id,
        "licence": base.get("licence"),
        "attribution": base.get("attribution"),
        "reason": reason_for_base(base_id),
        # Said in the payload so nothing downstream reads this as a legal
        # opinion. It is what the repository recorded, unverified.
        "basis": "licence recorded in catalog.py; not checked against the "
                 "publisher's licence page",
    }


def summary() -> Dict[str, Any]:
    """Counts by state, for the audit script and `/api/catalog`."""
    catalog = _catalog()
    by_state: Dict[str, List[str]] = {CLEARED: [], CONDITIONAL: [],
                                      UNKNOWN: [], BLOCKED: []}
    for base in catalog.BASES:
        by_state[status_for_base(base["id"])].append(base["id"])

    factors: Dict[str, int] = {k: 0 for k in by_state}
    for factor in catalog.FACTORS:
        factors[status_for_factor(factor["id"])] += 1

    return {
        "bases": {k: sorted(v) for k, v in by_state.items()},
        "base_counts": {k: len(v) for k, v in by_state.items()},
        "factor_counts": factors,
        "blocked_factor_ids": sorted(
            f["id"] for f in catalog.FACTORS
            if status_for_factor(f["id"]) == BLOCKED),
        "verified_against_publisher": False,
        "note": ("States are derived from licence strings recorded in "
                 "catalog.py. No licence page has been fetched. Run "
                 "scripts/verify_licensing.py from a machine with internet."),
    }
