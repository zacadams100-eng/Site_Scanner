"""
Temporal metrics over a satellite series.

Implements the frozen methodology in `HISTORICAL_EVIDENCE_MODEL.md` and nothing
beyond it. Deliberately boring: the interesting decisions were made in the
document, and the job here is to be a faithful, checkable transcription of them.

## What this returns, and what it must never return

A metric describes **what happened**:

    name · baseline · recent · change · change_type · usable_years
    baseline_years · recent_years · observation_coverage · year_coverage
    season · method_version · source

It must never contain `flagged`, `clear`, `severity`, `risk`, `investigation`
or a suitability conclusion. Those belong to a rule and to the engine that
already exists — see `EVIDENCE_MODEL.md` EM11 and
`tests/test_historical_metrics.py::test_he7_a_metric_never_contains_a_finding`.

## The two traps in the methodology

**The seasonal window belongs to the metric, not to the module.** Vegetation
reads April–September; land surface temperature reads June–August; built
surface reads every month. A shared window would be wrong for at least one of
them, and the convenient future simplification — "they can all use the growing
season" — silently changes what every LST figure means. `SEASONS` is keyed by
metric family for exactly that reason, and a test feeds December observations
to each family to prove they disagree.

**First three *usable* years, not first three calendar years.** A site with
observations in 2011, 2012, 2013, 2015, 2018 and 2021 has a baseline of
2011–2013 and a recent period of 2015–2021. Reaching for `years[:3]` on the
calendar range gives a baseline built partly from years with no data.
"""

from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: Bump when any definition below changes. Recorded in every result so a figure
#: read in three months is reproducible, and so results computed under an older
#: methodology stay identifiable rather than being silently reinterpreted.
METHOD_VERSION = "hist-1"

#: Months each metric family is read in, from the frozen methodology. Keyed by
#: family precisely so that no caller can accidentally share one window.
SEASONS: Dict[str, Tuple[int, ...]] = {
    # The English growing season. A December NDVI is a real observation of not
    # much, and including it makes every site look like it collapses annually.
    "vegetation": (4, 5, 6, 7, 8, 9),
    # Summer heat is the question. An annual mean mixes it with winter and
    # hides it.
    "lst": (6, 7, 8),
    # Not seasonal in the same way, and narrowing the window would halve an
    # already sparse signal.
    "surface": tuple(range(1, 13)),
}

#: Usable observations a year needs before it counts as a usable year. For
#: `lst` the window is three months, so this requires all three.
MIN_OBSERVATIONS_PER_YEAR = 3

#: Years in each of the baseline and recent periods. Three, not one: a
#: single-year baseline makes the result a function of whichever year happened
#: to be wet.
PERIOD_YEARS = 3

#: Share of years in the analysis period that must be usable before a change
#: metric carries enough evidence for a rule to evaluate it (HE5).
MIN_YEAR_COVERAGE = 0.6

#: Sources that count as observation. Same list the rest of the codebase uses.
REAL_SOURCES = ("earth-engine", "open-data")


def _month(period: str) -> int:
    return int(period[5:7])


def _year(period: str) -> int:
    return int(period[:4])


def _usable_points(series: Dict[str, Any],
                   season: Sequence[int]) -> List[Tuple[int, float]]:
    """(year, value) for observations inside the window that are real.

    Interpolated values are excluded, matching `insights._real_points`. A value
    carried across a gap reads as a measurement and is not one — and a baseline
    built from carried-forward values is a baseline of an assumption.
    """
    out: List[Tuple[int, float]] = []
    points = series.get("points")
    if not isinstance(points, list):
        return out
    for p in points:
        if not isinstance(p, dict):
            continue
        if p.get("value") is None or p.get("interpolated"):
            continue
        t = p.get("t")
        if not isinstance(t, str) or len(t) < 7:
            continue
        try:
            month, year, value = _month(t), _year(t), float(p["value"])
        except (TypeError, ValueError):
            continue
        if month in season:
            out.append((year, value))
    return out


def _period_years(series: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    """First and last year the series covers, from its own points."""
    years = []
    for p in series.get("points") or []:
        if isinstance(p, dict) and isinstance(p.get("t"), str) and len(p["t"]) >= 7:
            try:
                years.append(_year(p["t"]))
            except ValueError:
                continue
    return (min(years), max(years)) if years else (None, None)


def usable_years(series: Dict[str, Any], family: str) -> Dict[int, float]:
    """Year → annual value, for years with enough observations in the window.

    The annual value is the **median** of that year's usable observations, not
    the mean: one cloud-contaminated composite should not move a year, and one
    year should not move a fifteen-year baseline.
    """
    season = SEASONS[family]
    by_year: Dict[int, List[float]] = {}
    for year, value in _usable_points(series, season):
        by_year.setdefault(year, []).append(value)
    return {year: statistics.median(values)
            for year, values in sorted(by_year.items())
            if len(values) >= MIN_OBSERVATIONS_PER_YEAR}


def coverage(series: Dict[str, Any], family: str) -> Dict[str, Any]:
    """How much of the period was actually observed (HE3).

    Two figures, and they are not interchangeable. A series that is excellent
    2011–2014, poor 2015–2018 and excellent 2019–2026 has high observation
    coverage and mediocre year coverage, and it is the second that decides
    whether a fifteen-year change statement is defensible.
    """
    season = SEASONS[family]
    points = series.get("points") or []
    possible = sum(1 for p in points
                   if isinstance(p, dict) and isinstance(p.get("t"), str)
                   and len(p["t"]) >= 7 and _month(p["t"]) in season)
    observed = len(_usable_points(series, season))
    first, last = _period_years(series)
    total_years = (last - first + 1) if first is not None else 0
    years = usable_years(series, family)
    return {
        "observations_usable": observed,
        "observations_possible": possible,
        "observation_coverage": round(observed / possible, 3) if possible else 0.0,
        "years_usable": len(years),
        "years_total": total_years,
        "year_coverage": round(len(years) / total_years, 3) if total_years else 0.0,
        "first_year": first,
        "last_year": last,
    }


def change_metric(series: Dict[str, Any], *, name: str, family: str,
                  factor: str = "") -> Dict[str, Any]:
    """Baseline, recent and change, per the frozen methodology.

    Returns a metric — never a finding. `meets_minimum_evidence` says whether a
    rule may evaluate it (HE5); it is a statement about the evidence, not about
    the site, and `shortfall` says in plain words what was missing.

    Generated input produces no derived values at all (HE2). The alternative —
    computing a full fifteen-year trend from fabricated numbers and labelling
    it — is the most convincing wrong thing this product could draw, and a
    label on a chart is not a defence against it.
    """
    source = series.get("source")
    real = source in REAL_SOURCES
    cov = coverage(series, family)
    result: Dict[str, Any] = {
        "name": name,
        "factor": factor or series.get("factor_id", ""),
        "family": family,
        "season": list(SEASONS[family]),
        "source": source,
        "real": real,
        "provenance": series.get("provenance"),
        "unit": series.get("unit", ""),
        "method_version": METHOD_VERSION,
        **cov,
        "baseline": None,
        "recent": None,
        "baseline_years": [],
        "recent_years": [],
        "annual_values": {},
        "change": None,
        "change_pct": None,
        "change_type": None,
        "meets_minimum_evidence": False,
        "shortfall": "",
    }

    if not real:
        result["shortfall"] = (
            "The series is generated demo data, so no historical metric was "
            "derived from it.")
        return result

    years = usable_years(series, family)
    result["annual_values"] = {str(y): round(v, 6) for y, v in years.items()}
    ordered = sorted(years)

    # First three *usable* years, not first three calendar years. And the two
    # periods must not overlap, so six usable years are needed before a change
    # statement exists at all.
    if len(ordered) < PERIOD_YEARS * 2:
        result["shortfall"] = (
            f"{len(ordered)} usable year{'' if len(ordered) == 1 else 's'}; "
            f"{PERIOD_YEARS * 2} required for a baseline and a recent period.")
        return result

    baseline_years = ordered[:PERIOD_YEARS]
    recent_years = ordered[-PERIOD_YEARS:]
    baseline = statistics.median(years[y] for y in baseline_years)
    recent = statistics.median(years[y] for y in recent_years)

    result["baseline_years"] = baseline_years
    result["recent_years"] = recent_years
    result["baseline"] = round(baseline, 6)
    result["recent"] = round(recent, 6)
    result["change"] = round(recent - baseline, 6)

    if baseline == 0:
        # A percentage change from zero is an infinity dressed as a statistic.
        # The absolute difference is the whole of what can be said.
        result["change_type"] = "absolute"
    else:
        result["change_type"] = "relative"
        result["change_pct"] = round((recent - baseline) / abs(baseline) * 100, 3)

    if cov["year_coverage"] < MIN_YEAR_COVERAGE:
        result["shortfall"] = (
            f"{cov['years_usable']} of {cov['years_total']} years adequately "
            f"observed ({cov['year_coverage'] * 100:.0f}%); "
            f"{MIN_YEAR_COVERAGE * 100:.0f}% required.")
        return result

    result["meets_minimum_evidence"] = True
    return result
