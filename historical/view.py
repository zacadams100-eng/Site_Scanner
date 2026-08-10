"""
The historical block a UI renders.

Metrics for every declared historical metric, whether or not it produced a
flag. That last part is the reason this module exists: a `clear` result raises
no flag, so a UI reading only `radar.flags` would have nothing to draw for the
most reassuring outcome the product can produce — and "we checked and it is
within threshold" is the result worth showing most.

**Nothing here interprets.** It computes metrics — the same call `rules.py`
makes — and leaves a slot for the finding the engine already decided. The
caller fills that slot in, because doing it here would mean this module knowing
what `flagged` means, and one layer down is exactly where that knowledge is not
allowed to spread.

The UI then has, per metric: the numbers, the threshold that was applied, what
kind of threshold that is, and the state the engine reached. It renders those.
It decides none of them — `EVIDENCE_MODEL.md` EM11.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from historical import metrics, rules

#: What the historical page shows, in order. Each entry names the rule whose
#: finding belongs beside it, so the caller can pair numbers with a state
#: without either of them guessing.
SPECS = (
    {
        "id": "vegetation",
        "name": "Vegetation vigour",
        "factor": "ndvi",
        "family": "vegetation",
        "rule": "historical_vegetation_decline",
        "meta": rules.VEGETATION_RULE_META,
    },
)


def report(series: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One entry per declared historical metric.

    `finding` is left as `None` for the caller to fill from the engine's own
    output. A metric with no series at all still appears, with `available`
    false — a missing row is indistinguishable from a clean one, which is the
    same argument that keeps every topic in the radar's coverage strip.
    """
    out: List[Dict[str, Any]] = []
    for spec in SPECS:
        one = series.get(spec["factor"])
        if not one:
            out.append({
                "id": spec["id"],
                "name": spec["name"],
                "factor": spec["factor"],
                "rule": spec["rule"],
                "rule_meta": spec["meta"],
                "available": False,
                "metric": None,
                "finding": None,
            })
            continue
        out.append({
            "id": spec["id"],
            "name": spec["name"],
            "factor": spec["factor"],
            "rule": spec["rule"],
            "rule_meta": spec["meta"],
            "available": True,
            "metric": metrics.change_metric(
                one, name=spec["name"], family=spec["family"],
                factor=spec["factor"]),
            "finding": None,
        })
    return out


def methodology() -> Dict[str, Any]:
    """The frozen definitions, served rather than documented twice.

    A professional may want to check how "change" was defined before quoting a
    figure. Reproducing this list in a UI string would guarantee it eventually
    disagrees with `metrics.py`.
    """
    return {
        "version": metrics.METHOD_VERSION,
        "seasons": {family: list(months)
                    for family, months in metrics.SEASONS.items()},
        "min_observations_per_year": metrics.MIN_OBSERVATIONS_PER_YEAR,
        "period_years": metrics.PERIOD_YEARS,
        "min_year_coverage": metrics.MIN_YEAR_COVERAGE,
        "rules": [
            "Baseline is the first three usable years; recent is the last "
            "three. The two never overlap.",
            "A usable year needs at least three usable observations inside "
            "the metric's seasonal window.",
            "Interpolated observations are excluded — a value carried across "
            "a gap reads as a measurement and is not one.",
            "Annual, baseline and recent values are medians, so one "
            "cloud-contaminated composite cannot move a fifteen-year figure.",
            "Change from a zero baseline is reported as an absolute "
            "difference; a percentage change from zero is undefined.",
        ],
    }
