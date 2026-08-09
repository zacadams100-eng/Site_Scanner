"""How a site compares with the rest of England.

A number on its own is not an answer. `crime_density 230` and `ndvi 0.43` mean
nothing to the land agent this product is for — the useful sentence is "busier
than four fifths of England" or "greener than average for this month", and that
needs a yardstick.

## The rule that shapes this file

**A baseline may only be built from real observations.** The tempting version
is to run `series.py` over a few hundred points and call the result a national
average; it would take an afternoon, cover all 269 factors, and be worthless —
a fabricated yardstick against which a real measurement is compared produces a
percentile that looks authoritative and means nothing at all. Worse than no
comparison, because the reader cannot see it happening.

So a factor gets a baseline when, and only when, it has been sampled from its
live source across England. `scripts/build_baselines.py` does that and writes
`data/baselines.json`. Everything else shows no comparison, which is honest and
also quietly informative — the factors with a yardstick are the factors with
real data behind them.

## What is stored

Percentiles rather than a mean. Most of these distributions are nowhere near
normal: house prices are long-tailed, crime density is zero across most of the
country, and a mean of either describes nowhere. p10/p50/p90 lets the UI say
"in the top tenth" without implying a bell curve nobody has checked for.

The sample size and date are stored with them, because a percentile from 60
points and one from 6,000 are different claims and the difference has to be
visible.
"""

from __future__ import annotations

import bisect
import json
import pathlib
from typing import Any, Dict, List, Optional

BASELINE_FILE = pathlib.Path(__file__).with_name("data") / "baselines.json"

# Below this many sample points, a percentile is noise wearing a number. Sixty
# is enough to place a value in a tenth without pretending to more precision
# than the sample supports.
MIN_SAMPLE = 30

_CACHE: Optional[Dict[str, Any]] = None


def load(path: Optional[pathlib.Path] = None) -> Dict[str, Any]:
    """The stored baselines, or an empty set if none have been built.

    An absent file is the normal state on a fresh clone and must not be an
    error: the app works without comparisons, it just says less.
    """
    global _CACHE
    if path is None and _CACHE is not None:
        return _CACHE

    target = path or BASELINE_FILE
    try:
        data = json.loads(target.read_text())
    except (OSError, ValueError):
        data = {"factors": {}, "built": None, "method": None}

    if path is None:
        _CACHE = data
    return data


def clear_cache() -> None:
    global _CACHE
    _CACHE = None


def percentile_of(value: float, sorted_samples: List[float]) -> int:
    """Where this value falls, 0–100, by rank.

    Rank rather than a fitted distribution, for the same reason the store keeps
    percentiles rather than a mean: nobody has checked these for normality and
    several of them plainly are not.
    """
    if not sorted_samples:
        return 50
    below = bisect.bisect_left(sorted_samples, value)
    above = bisect.bisect_right(sorted_samples, value)
    # Midpoint of the tied range, so a value equal to half the country's zeros
    # does not report as either 0th or 100th percentile.
    rank = (below + above) / 2
    return int(round(100.0 * rank / len(sorted_samples)))


def compare(factor_id: str, value: Optional[float],
            store: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """This site's value against England, or None if there is no yardstick.

    Returning None is the common case and the correct one. Every caller has to
    handle it, which is deliberate: it keeps "we have no baseline for this"
    from being papered over with a default that would read as a real
    comparison.
    """
    if value is None or isinstance(value, str):
        return None

    data = load() if store is None else store
    entry = (data.get("factors") or {}).get(factor_id)
    if not entry:
        return None

    samples = entry.get("samples") or []
    if len(samples) < MIN_SAMPLE:
        return None

    pct = percentile_of(float(value), samples)
    return {
        "percentile": pct,
        "median": entry.get("p50"),
        "p10": entry.get("p10"),
        "p90": entry.get("p90"),
        "n": len(samples),
        "built": data.get("built"),
        # Carried so nothing downstream has to assume where this came from.
        # There is exactly one legitimate value today; the field exists so that
        # a published national statistic could be added later without the UI
        # having to guess which kind it is looking at.
        "basis": entry.get("basis", "sampled"),
        "phrase": phrase(factor_id, pct, entry),
    }


def phrase(factor_id: str, pct: int, entry: Dict[str, Any]) -> str:
    """The comparison as a sentence a non-specialist can read at a glance.

    Bands rather than the raw percentile, because "78th percentile" is a
    statistician's sentence and "higher than most of England" is everyone
    else's. The number is still returned alongside for anyone who wants it.
    """
    if pct >= 90:
        return "higher than 9 in 10 places in England"
    if pct >= 75:
        return "higher than most of England"
    if pct >= 60:
        return "a little above average for England"
    if pct > 40:
        return "about average for England"
    if pct > 25:
        return "a little below average for England"
    if pct > 10:
        return "lower than most of England"
    return "lower than 9 in 10 places in England"


def summary() -> Dict[str, Any]:
    """What the store holds, for `/api/catalog` and the Sources tab."""
    data = load()
    factors = data.get("factors") or {}
    usable = [f for f, e in factors.items()
              if len(e.get("samples") or []) >= MIN_SAMPLE]
    return {
        "built": data.get("built"),
        "method": data.get("method"),
        "factor_count": len(usable),
        "factors": sorted(usable),
    }
