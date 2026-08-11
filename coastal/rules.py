"""
Coastal Scanner rules.

A contributing package on the same `build(Rule, Insufficient)` contract as
`historical.rules` and `habitat.rules`. It never imports the finding engine, so
the engine gains no knowledge of coasts — adding this scanner required no
change to `radar.py`, which is the architectural claim being tested by building
a third domain.

## What this scanner is, and what it is not

It is a **coastal site assessment**: it reads the area you draw and reports
low-lying exposure, tidal and surface-water presence, and change in surface
water extent over the satellite record.

It is **not a shoreline corridor analysis**. `geometry.py` is polygon-oriented
and there is no coastline dataset anywhere in this repository, which has three
consequences stated here rather than buried:

1. **The scanner cannot verify that a site is coastal.** There is no mean-high-
   water line to measure against, so "is this on the coast" is the operator's
   judgement, not the product's. Running it inland produces honest readings of
   an inland site.
2. **It cannot measure shoreline retreat.** That needs a shoreline vector time
   series. Surface water extent change is a different quantity and is reported
   as what it is.
3. **A frontage is assessed as an area, not as a corridor.** Drawing a long thin
   polygon along a frontage works; the engine has no concept of alongshore
   distance, so nothing is reported per-metre-of-frontage.

`docs/SCANNER_SPECIFICATION.md` §Coastal lists the questions a coastal scanner
should answer and cannot yet, each with its specific blocker. Filling them with
invented numbers would produce a scanner that looks complete and claims things
nobody checked.

## Two flagged checks, five readings

Both flags act on factors **no Land rule uses**. That is deliberate: Land
already owns Flood Zone 2 and 3, standing water and seasonal water, and
restating them under a coastal heading would be the same check wearing a
different hat. What Land does not ask is how low the lowest ground is, and
whether the water here has been gaining or losing extent.

## Thresholds are product-defined, and say so

Neither number below is regulatory, statutory or a scientific consensus. They
are Contour's decisions about when something is worth a professional looking
at, they are named constants, and every finding that acts on one restates it
next to the measurement.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Tuple

#: Site ground at or below this height (metres above ordnance datum) is
#: reported as low-lying coastal exposure.
#:
#: **PRODUCT-DEFINED.** Not a regulatory level, not a design flood level, and
#: not a prediction of inundation. Five metres is the height at which a coastal
#: flood risk assessment stops being a formality and starts being a live
#: question for most English frontages — it is a screening line for prompting
#: expert attention, chosen to be legible and defensible rather than derived.
#:
#: What would replace it: a site-specific extreme sea level from the Environment
#: Agency's coastal design levels, plus a defence standard for the frontage.
#: Neither is in this repository. Until they are, this is a screening trigger
#: and is labelled as one everywhere it appears.
COASTAL_LOW_LYING_INVESTIGATION_THRESHOLD = 5.0

#: Change in surface water extent, in percentage points, at or beyond which the
#: change is reported.
#:
#: **PRODUCT-DEFINED.** The JRC Global Surface Water record measures where water
#: was detected between 1984 and the present. A change of this size over four
#: decades is large enough to be a real signal rather than classification noise,
#: and small enough not to miss a gradual trend. It is a reporting threshold,
#: not a rate of erosion and not a prediction.
COASTAL_WATER_EXTENT_CHANGE_INVESTIGATION_THRESHOLD = 10.0

#: What the scanner investigates. Coastal's own vocabulary — the engine reads
#: these ids and attaches no meaning to them.
TOPICS: Dict[str, str] = {
    "exposure": "Low-lying exposure",
    "tidal": "Tidal and surface water",
    "change": "Surface water change",
    "form": "Coastal landform",
}

#: The follow-up a flagged check prompts. Both are real professional
#: instructions naming a deliverable, not "investigate the coast".
INVESTIGATIONS: Dict[str, Dict[str, str]] = {
    "coastal_flood_risk": {
        "name": "Coastal flood risk assessment",
        "blurb": "Site-specific extreme sea levels, the defence standard for "
                 "this frontage, and residual risk over the development "
                 "lifetime.",
        "next_step": "Commission a coastal flood risk assessment against the "
                     "Environment Agency's design sea levels for this "
                     "frontage.",
    },
    "coastal_process_review": {
        "name": "Coastal process and morphology review",
        "blurb": "What is driving the change in water extent here — "
                 "accretion, erosion, managed realignment, or a change in "
                 "how the area drains.",
        "next_step": "Review the Shoreline Management Plan policy unit for "
                     "this frontage and commission a coastal process review.",
    },
}

#: Every factor this scanner exposes. Seven, and only the seven its questions
#: are built on — a scanner that shows every available number is a data browser.
FACTORS: Tuple[str, ...] = (
    "elevation_min", "elevation_mean", "water_change", "water_occurrence",
    "water_seasonality", "lc_water_pct", "slope_mean",
)

LOW_LYING_META: Dict[str, Any] = {
    "rule": "Coastal low-lying exposure",
    "threshold": COASTAL_LOW_LYING_INVESTIGATION_THRESHOLD,
    "threshold_display": "≤ 5 m above ordnance datum",
    "threshold_type": "Contour reporting threshold",
    "threshold_status": "product-defined; not a regulatory level, a design "
                        "flood level, or a prediction of inundation",
    "purpose": "Identifies sites low enough that coastal flood exposure is a "
               "live question for a professional, rather than a formality.",
    "not_evidence_of": (
        "It is not evidence that the site floods, or will flood. It says "
        "nothing about the defence standard protecting this frontage, about "
        "extreme sea levels here, or about how either changes over a "
        "development lifetime. A defended site at 2 m and an undefended site "
        "at 2 m read identically to this check and are not the same risk."
    ),
    "measure": "lowest ground elevation within the drawn area",
    "direction": "low",
}

WATER_CHANGE_META: Dict[str, Any] = {
    "rule": "Coastal surface water extent change",
    "threshold": COASTAL_WATER_EXTENT_CHANGE_INVESTIGATION_THRESHOLD,
    "threshold_display": "≥ 10 percentage points, gain or loss",
    "threshold_type": "Contour reporting threshold",
    "threshold_status": "product-defined; not an erosion rate and not a "
                        "regulatory trigger",
    "purpose": "Identifies frontages where the extent of detected surface "
               "water has moved enough to be worth explaining.",
    "not_evidence_of": (
        "It is not shoreline retreat and must not be read as an erosion "
        "rate. The JRC record measures where water was detected, not where "
        "the shoreline was: a change can be accretion, erosion, managed "
        "realignment, a new drainage regime, or a change in how the "
        "classifier handled a tidal flat. Which of those it is, is the "
        "question this hands to a coastal engineer."
    ),
    "measure": "change in surface water occurrence over the JRC record",
    "direction": "either",
}


def _latest(series_by_factor, factor):
    """Most recent non-null observation for a factor, or None."""
    one = series_by_factor.get(factor)
    points = [p for p in (one or {}).get("points", []) if p.get("value") is not None]
    return points[-1] if points else None


def _low_lying(series_by_factor, insufficient):
    """Flag a site whose lowest ground sits at or below the screening height."""
    point = _latest(series_by_factor, "elevation_min")
    if point is None:
        return insufficient("no elevation observation for this area")
    low = point["value"]
    if low > COASTAL_LOW_LYING_INVESTIGATION_THRESHOLD:
        return None
    return {
        "text": (
            f"The lowest ground in this area is {low:.1f} m above ordnance "
            f"datum, at or below the {COASTAL_LOW_LYING_INVESTIGATION_THRESHOLD:.0f} m "
            "screening height. Coastal flood exposure needs establishing "
            "against the design sea levels for this frontage."
        ),
        # Deliberately not scaled by how low it is. A severity that climbs as
        # the number falls would be this rule estimating flood risk, which is
        # exactly what it states it cannot do.
        "severity": "medium",
        "evidence": {
            "elevation_min": low,
            "threshold": "5 m above ordnance datum (Contour reporting "
                         "threshold)",
            "as_of": point["t"],
            "basis": "lowest observed ground elevation in the drawn area",
        },
    }


def _water_extent_change(series_by_factor, insufficient):
    """Flag a material gain or loss in detected surface water extent."""
    point = _latest(series_by_factor, "water_change")
    if point is None:
        return insufficient("no surface water change observation for this area")
    change = point["value"]
    if abs(change) < COASTAL_WATER_EXTENT_CHANGE_INVESTIGATION_THRESHOLD:
        return None
    direction = "gained" if change > 0 else "lost"
    return {
        "text": (
            f"Detected surface water extent has {direction} "
            f"{abs(change):.0f} percentage points over the observation record "
            f"(as of {point['t']}). What is driving that — accretion, "
            "erosion, realignment or drainage — is a question for a coastal "
            "process review."
        ),
        "severity": "medium",
        "evidence": {
            "water_change": change,
            "threshold": "10 percentage points (Contour reporting threshold)",
            "as_of": point["t"],
            "basis": "JRC Global Surface Water change over the observation "
                     "record",
        },
    }


def _reading(rule_class, rule_id, topic, factor, label, asks, fmt=str):
    """An informational reading: a measurement with no threshold.

    No threshold is not an omission — none of these has a line this repository
    can defend drawing, and inventing one to make a card look actionable is the
    failure this product exists to prevent. Bound by the same real-data rule as
    a flag: a generated reading is still a fabricated fact about a real place.
    """
    def test(series_by_factor):
        point = _latest(series_by_factor, factor)
        if point is None:
            return None
        return {
            "text": f"{label}: {fmt(point['value'])} ({point['t']})",
            "evidence": {factor: point["value"], "as_of": point["t"],
                         "basis": "most recent observation"},
        }

    return rule_class(rule_id, topic, [factor], test, (), asks, kind="info")


def build(rule_class: Callable[..., Any],
          insufficient: Callable[[str], Any]) -> Tuple[Any, ...]:
    """Coastal's rules, as engine rules."""
    return (
        rule_class(
            "coastal_low_lying", "exposure", ["elevation_min"],
            lambda s: _low_lying(s, insufficient),
            ["coastal_flood_risk"],
            "how low the lowest ground in this area sits",
            meta=LOW_LYING_META,
        ),
        rule_class(
            "coastal_water_extent_change", "change", ["water_change"],
            lambda s: _water_extent_change(s, insufficient),
            ["coastal_process_review"],
            "whether the extent of detected surface water has moved",
            meta=WATER_CHANGE_META,
        ),
        _reading(rule_class, "coastal_elevation_min", "exposure",
                 "elevation_min", "Lowest ground",
                 "what the lowest ground elevation is",
                 fmt=lambda v: f"{v:.1f} m"),
        _reading(rule_class, "coastal_elevation_mean", "exposure",
                 "elevation_mean", "Mean ground elevation",
                 "what the mean ground elevation is",
                 fmt=lambda v: f"{v:.1f} m"),
        _reading(rule_class, "coastal_water_occurrence", "tidal",
                 "water_occurrence", "Surface water occurrence",
                 "how often surface water is detected here",
                 fmt=lambda v: f"{v:.0f}%"),
        _reading(rule_class, "coastal_water_seasonality", "tidal",
                 "water_seasonality", "Water seasonality",
                 "how many months of the year water is present",
                 fmt=lambda v: f"{v:.0f} months"),
        _reading(rule_class, "coastal_slope", "form", "slope_mean",
                 "Mean gradient",
                 "how steeply the ground rises from the water",
                 fmt=lambda v: f"{v:.1f}°"),
    )
