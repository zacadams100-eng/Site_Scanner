"""
Habitat Scanner rules.

A contributing package, built to the same `build(Rule, Insufficient)` contract
as `historical.rules` — it never imports the finding engine, so the direction
of knowledge stays one way and the engine gains no knowledge of ecology.

## One flagged check, five informational readings

That is the whole scanner, and the thinness is the point. `HABITAT_SCANNER.md`
§6 lists the questions a habitat scanner should answer and cannot yet —
fragmentation, land-cover change, burn history — each with the specific reason.
Filling them with invented thresholds would produce a scanner that looks
complete and claims things nobody checked.

## The threshold is imported, never restated

`VEGETATION_CHANGE_INVESTIGATION_THRESHOLD` comes from `historical.rules`.
Two scanners holding two copies of one number is how they drift, and the first
symptom would be the app and the brief disagreeing about what crossed.

## Why no ERA5 or MODIS factor appears here

Both are implemented and both work. ERA5-Land is 9 km and MODIS LST is 1 km,
and a 9 km pixel over a 20 ha reserve describes a large part of a county. They
are regional context presented as site evidence, which is a false precision
this product exists to avoid.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Tuple

from historical import metrics
from historical.rules import VEGETATION_CHANGE_INVESTIGATION_THRESHOLD

#: What the scanner investigates. Habitat's own vocabulary — the engine reads
#: these ids and attaches no meaning to them.
TOPICS: Dict[str, str] = {
    "condition": "Vegetation condition",
    "moisture": "Moisture condition",
    "cover": "Land cover context",
    "water": "Surface water context",
    "structure": "Vegetation structure",
}

#: The follow-up a flagged condition change prompts. The same check Land names,
#: because it genuinely is the same check — an ecologist walking the parcel.
INVESTIGATIONS: Dict[str, Dict[str, str]] = {
    "ecology_survey": {
        "name": "Preliminary ecological appraisal",
        "blurb": "Habitat survey, protected species scoping, and the baseline "
                 "a BNG calculation is built on.",
        "next_step": "Instruct a preliminary ecological appraisal, ideally in "
                     "season.",
    },
}

#: Every factor this scanner exposes. Deliberately six of twenty-seven: a
#: scanner that shows every available number is a data browser, and one that
#: shows the numbers behind its questions is an evidence tool.
FACTORS: Tuple[str, ...] = (
    "ndvi", "ndmi", "evi", "lc_tree_pct", "lc_dominant", "water_occurrence",
)

#: Restated on every flag, so the reader sees the difference between the
#: measurement and Contour's decision to surface it.
RULE_META: Dict[str, Any] = {
    "rule": "Habitat vegetation condition change",
    "threshold": VEGETATION_CHANGE_INVESTIGATION_THRESHOLD,
    "threshold_display": "≥ 20% decline",
    "threshold_type": "Contour reporting threshold",
    "threshold_status": "product-defined; not a regulatory or scientific "
                        "standard",
    "purpose": "Identifies changes large enough to warrant an ecologist "
               "looking at the parcel. Not a condition assessment.",
    "not_evidence_of": (
        "It is not evidence of habitat deterioration or of unfavourable "
        "condition. A spectral index responds to management, grazing, cutting "
        "and season as readily as to harm, and condition is assessed on the "
        "ground against defined criteria."
    ),
    "method_version": metrics.METHOD_VERSION,
    "measure": "percentage change in median NDVI from the historical baseline",
    "direction": "decline",
}


def _condition_change(series_by_factor, insufficient):
    """Flag a vegetation decline at or beyond the reporting threshold.

    Identical arithmetic to the land scanner's historical rule, and
    deliberately so: it is the same measurement over the same series under the
    same frozen methodology. What differs is the topic it belongs to and what
    the finding is said not to establish.

    Trusts `meets_minimum_evidence` rather than reconstructing sufficiency, so
    a series with too few usable years produces "not assessed" rather than a
    confident number from three observations.
    """
    one = series_by_factor.get("ndvi")
    if not one:
        return None
    metric = metrics.change_metric(one, name="NDVI", family="vegetation")
    if not metric.get("meets_minimum_evidence"):
        return insufficient(metric.get("shortfall")
                            or "too few usable years to compare periods")
    change = metric.get("change_pct")
    if change is None or change > VEGETATION_CHANGE_INVESTIGATION_THRESHOLD:
        return None
    return {
        "text": (
            f"Vegetation vigour has declined {abs(change):.0f}% relative to "
            f"the historical baseline ({metric['baseline']:.2f} in "
            f"{metric['baseline_years'][0]}–{metric['baseline_years'][-1]} to "
            f"{metric['recent']:.2f} in {metric['recent_years'][0]}–"
            f"{metric['recent_years'][-1]}). A change of this size is worth an "
            "ecologist establishing the cause of."
        ),
        "severity": "medium",
        # The threshold belongs *inside* `evidence`: `radar.py:998` reads
        # `found["evidence"]["threshold"]` and ignores a top-level key. Declared
        # at the top level it simply vanished, and the flag reached the
        # workspace with no threshold at all — silent, and the kind of thing
        # only running the chain finds.
        "evidence": {
            "change_pct": change,
            "threshold": "20% decline (Contour reporting threshold)",
            "baseline": metric["baseline"],
            "baseline_period": f"{metric['baseline_years'][0]}–"
                               f"{metric['baseline_years'][-1]}",
            "recent": metric["recent"],
            "recent_period": f"{metric['recent_years'][0]}–"
                             f"{metric['recent_years'][-1]}",
            "years_observed": f"{metric['years_usable']} of "
                              f"{metric['years_total']}",
            "method_version": metric["method_version"],
        },
    }


def _reading(rule_class, rule_id, topic, factor, label, asks, fmt=str):
    """An informational reading: a measurement with no threshold.

    No threshold is not an omission. `HABITAT_SCANNER.md` §5 records that none
    of these has a defensible line to draw from anything in this repository,
    and the alternative — inventing one to make a card look actionable — is
    the failure this product is built to prevent.

    Bound by the same real-data rule as a flag: a generated informational
    reading is still a fabricated fact about a real place (EM3).
    """
    def test(series_by_factor):
        one = series_by_factor.get(factor)
        points = [p for p in (one or {}).get("points", [])
                  if p.get("value") is not None]
        if not points:
            return None
        last = points[-1]
        return {
            "text": f"{label}: {fmt(last['value'])} ({last['t']})",
            "evidence": {factor: last["value"], "as_of": last["t"],
                         "basis": "most recent observation"},
        }

    return rule_class(rule_id, topic, [factor], test, (), asks, kind="info")


def build(rule_class: Callable[..., Any],
          insufficient: Callable[[str], Any]) -> Tuple[Any, ...]:
    """Habitat's rules, as engine rules."""
    return (
        rule_class(
            "habitat_vegetation_decline", "condition", ["ndvi"],
            lambda s: _condition_change(s, insufficient),
            ["ecology_survey"],
            "whether vegetation vigour has declined against its historical "
            "baseline",
            meta=RULE_META,
        ),
        _reading(rule_class, "habitat_ndvi", "condition", "ndvi",
                 "Mean vegetation vigour (NDVI)",
                 "what the most recent vegetation reading is",
                 fmt=lambda v: f"{v:.2f}"),
        _reading(rule_class, "habitat_moisture", "moisture", "ndmi",
                 "Canopy and soil moisture (NDMI)",
                 "what the most recent moisture reading is",
                 fmt=lambda v: f"{v:.2f}"),
        _reading(rule_class, "habitat_structure", "structure", "evi",
                 "Vegetation index, dense-canopy corrected (EVI)",
                 "what the dense-canopy-corrected index reads",
                 fmt=lambda v: f"{v:.2f}"),
        _reading(rule_class, "habitat_tree_cover", "cover", "lc_tree_pct",
                 "Tree cover", "how much of the parcel is tree cover",
                 fmt=lambda v: f"{v:.0f}%"),
        _reading(rule_class, "habitat_land_cover", "cover", "lc_dominant",
                 "Dominant land cover", "what the parcel is mostly covered by"),
        _reading(rule_class, "habitat_water", "water", "water_occurrence",
                 "Surface water occurrence",
                 "how often surface water is detected here",
                 fmt=lambda v: f"{v:.0f}%"),
    )
