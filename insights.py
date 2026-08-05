"""
Reading a report so the user does not have to.

A site report is twelve factors over 180 months — 2,160 numbers. The charts are
good, but they put the work of noticing on the user, and the thing people
actually want to know is "is there anything here I should care about?".

This answers that. It looks at each series and produces plain sentences about
what it found, ranked so the most notable comes first:

    Vegetation vigour fell 23% over the window, most of it between
    2022-06 and 2023-08.
    Crime density in July 2024 was 2.4 standard deviations above its usual
    July — the highest July in the record.
    34% of this site is green belt.

## What this is not

It is not a model, and it does not predict. Every statement is arithmetic over
observations that are already on screen, and every one carries the numbers it
came from so a user can check it against the chart rather than trust it.

## Three rules it will not break

**Generated data never produces a claim about the world.** Two thirds of the
catalogue is demo data. An insight from a generated series says so in its own
text, every time — not in a footnote, not in a tooltip. The alternative is an
application that invents a confident sentence about a place from numbers it
made up, which is the single worst thing this codebase could do.

**Carried-forward values never produce a trend.** A census figure held across
144 months would otherwise read as a perfectly flat, perfectly significant
series, and an annual figure stepping once a year looks like a step change
every January. Interpolated points are excluded from trend and change-point
analysis, and a series that is mostly carried forward is described rather than
analysed.

**A short or gappy series produces nothing.** Fewer than 12 real observations
is not enough for a seasonal baseline and barely enough for a trend, so those
tests do not run rather than running on sand.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Below this many real observations, most of the tests below are noise.
MIN_POINTS = 12
#: A trend has to clear this |t| to be reported. ~95% two-tailed for n > 30.
TREND_T = 2.0
#: An anomaly has to be this many standard deviations from its seasonal norm.
ANOMALY_SD = 2.0
#: A step change has to move the mean by this many pooled SDs.
STEP_SD = 1.5


class Insight(dict):
    """One finding. A dict so it serialises straight into the response.

    Fields: `factor`, `kind`, `text`, `notability` (0-1), `source`, plus
    whatever numbers that kind of finding rests on.
    """


def _real_points(series: Dict[str, Any]) -> List[Tuple[int, str, float]]:
    """(index, period, value) for points that are actual observations.

    Gaps and carried-forward values are both excluded — see the module
    docstring for why interpolation has to be kept out of trend analysis.
    """
    out = []
    for i, p in enumerate(series.get("points") or []):
        if p.get("value") is None or p.get("interpolated"):
            continue
        try:
            out.append((i, p["t"], float(p["value"])))
        except (TypeError, ValueError):
            continue
    return out


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs)


def _stdev(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _fmt(value: float, unit: str) -> str:
    """A number the way this project writes numbers.

    Units come from the catalogue and are things like `£`, `%`, `per km²/month`
    and `index`, so the formatting has to be led by the unit rather than by the
    magnitude alone.
    """
    if unit == "£":
        return f"£{value:,.0f}"
    if unit == "%":
        return f"{value:.1f}%"
    if abs(value) >= 1000:
        return f"{value:,.0f} {unit}".strip()
    if abs(value) >= 10:
        return f"{value:.1f} {unit}".strip()
    return f"{value:.3g} {unit}".strip()


def _label(series: Dict[str, Any]) -> str:
    meta = series.get("meta") or {}
    return meta.get("name") or series.get("factor_id", "This factor")


def _caveat(series: Dict[str, Any]) -> str:
    """The suffix that keeps a sentence honest.

    Generated data is the one that matters. It is appended to the sentence
    itself rather than carried alongside it, because a caveat in a separate
    field is a caveat that some future layout will drop.
    """
    if series.get("source") == "generated":
        return " (demo data — generated, not observed)"
    return ""


# ---------------------------------------------------------------------------
# The individual tests
# ---------------------------------------------------------------------------
def trend(series: Dict[str, Any]) -> Optional[Insight]:
    """Least-squares slope over the window, reported only if significant.

    The t-statistic is what stops this narrating noise. A 180-point series of
    pure randomness will produce a non-zero slope every time; without a
    significance test, every factor in every report would get a confident
    sentence about a trend that is not there.
    """
    points = _real_points(series)
    if len(points) < MIN_POINTS:
        return None

    xs = [float(i) for i, _, _ in points]
    ys = [v for _, _, v in points]
    n = len(xs)
    mx, my = _mean(xs), _mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    intercept = my - slope * mx

    if n <= 2:
        return None
    residuals = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    sse = sum(r * r for r in residuals)
    sst = sum((y - my) ** 2 for y in ys)

    if sse <= 0:
        # A perfect straight line. This is the strongest trend a series can
        # have, and treating a zero residual as a failed regression — which is
        # what a naive divide-by-SSE guard does — silently drops exactly the
        # clearest cases. Common in practice: a carried-forward annual figure
        # that steps by a constant, or a stored value with few decimals.
        if slope == 0:
            return None
        t_stat, r2 = float("inf"), 1.0
    else:
        se = math.sqrt(sse / (n - 2) / sxx)
        if se == 0:
            return None
        t_stat = slope / se
        if abs(t_stat) < TREND_T:
            return None
        r2 = 1 - sse / sst if sst else 0.0

    first, last = points[0], points[-1]
    # The fitted line's endpoints, not the first and last observations. On a
    # seasonal series those two are a March and a November, and quoting them
    # produces "rose 122%" for a temperature series with no trend at all —
    # a sentence that is arithmetically true and completely misleading.
    fitted_first = intercept + slope * xs[0]
    fitted_last = intercept + slope * xs[-1]
    change = fitted_last - fitted_first
    pct = (change / abs(fitted_first) * 100.0) if fitted_first else None
    direction = "rose" if slope > 0 else "fell"
    unit = series.get("unit", "")

    if pct is not None and abs(pct) >= 1:
        magnitude = f"{direction} {abs(pct):.0f}%"
    else:
        magnitude = f"{direction} by {_fmt(abs(change), unit)}"

    # A significant slope is not the same as a dominant one. With 124 points a
    # trend explaining 4% of the variance still clears the t-test, and stating
    # it without this qualifier invites a reader to treat month-to-month noise
    # as a direction of travel.
    qualifier = ("" if r2 >= 0.25 else
                 " — though month-to-month variation is larger than the trend")

    return Insight(
        factor=series.get("factor_id"),
        kind="trend",
        text=(f"{_label(series)} {magnitude} between {first[1]} and "
              f"{last[1]}, from about {_fmt(fitted_first, unit)} to "
              f"{_fmt(fitted_last, unit)}{qualifier}.{_caveat(series)}"),
        # A strong, well-fitted trend over a long window is the most notable
        # thing a series can show; r² keeps a significant-but-scattered slope
        # from outranking a clean one.
        notability=(min(1.0, abs(t_stat) / 12.0) if math.isfinite(t_stat) else 1.0)
                   * (0.4 + 0.6 * max(0.0, r2)),
        source=series.get("source"),
        slope_per_step=slope,
        change=change,
        pct_change=pct,
        r2=round(r2, 3),
        t=round(t_stat, 2) if math.isfinite(t_stat) else None,
        n=n,
    )


def seasonal_anomaly(series: Dict[str, Any]) -> Optional[Insight]:
    """The most recent month against the same month in other years.

    Comparing July to June would call every summer an anomaly, so the baseline
    is per calendar month. Needs at least three prior years of that month to
    have a standard deviation worth dividing by.
    """
    points = _real_points(series)
    if len(points) < MIN_POINTS or series.get("cadence") != "monthly":
        return None

    latest = points[-1]
    month = latest[1][5:7]
    history = [v for _, t, v in points[:-1] if t[5:7] == month]
    if len(history) < 3:
        return None

    base, sd = _mean(history), _stdev(history)
    if sd == 0:
        return None
    z = (latest[2] - base) / sd
    if abs(z) < ANOMALY_SD:
        return None

    unit = series.get("unit", "")
    month_name = ("January February March April May June July August September "
                  "October November December").split()[int(month) - 1]
    direction = "above" if z > 0 else "below"
    extreme = ""
    if (z > 0 and latest[2] >= max(history)) or (z < 0 and latest[2] <= min(history)):
        extreme = f" — the {'highest' if z > 0 else 'lowest'} {month_name} in the record"

    return Insight(
        factor=series.get("factor_id"),
        kind="anomaly",
        text=(f"{_label(series)} in {month_name} {latest[1][:4]} was "
              f"{_fmt(latest[2], unit)}, {abs(z):.1f} standard deviations "
              f"{direction} the usual {month_name} of "
              f"{_fmt(base, unit)}{extreme}.{_caveat(series)}"),
        notability=min(1.0, abs(z) / 4.0),
        source=series.get("source"),
        z=round(z, 2),
        baseline=base,
        latest=latest[2],
        period=latest[1],
    )


def step_change(series: Dict[str, Any]) -> Optional[Insight]:
    """The single split that most separates the series into a before and after.

    A crude change-point: try every split with enough points either side and
    keep the one with the largest standardised difference of means. Crude is
    the right level here — the claim is "something changed around then", not a
    date to the month.
    """
    points = _real_points(series)
    if len(points) < 2 * MIN_POINTS:
        return None

    levels = [v for _, _, v in points]
    # How well a straight line explains the series. A smooth rise has a large
    # difference of means between its halves and no step in it at all, so
    # without this comparison every trending factor also collects a spurious
    # "shifted up around 2018" — wrong, and specific enough to be believed.
    line_sse = sum(r * r for r in _residuals(levels))

    best = None
    margin = MIN_POINTS // 2
    for split in range(margin, len(levels) - margin):
        left, right = levels[:split], levels[split:]
        ml, mr = _mean(left), _mean(right)
        step_sse = (sum((v - ml) ** 2 for v in left)
                    + sum((v - mr) ** 2 for v in right))
        sd_l, sd_r = _stdev(left), _stdev(right)
        pooled = math.sqrt((sd_l ** 2 * (len(left) - 1)
                            + sd_r ** 2 * (len(right) - 1))
                           / max(1, len(levels) - 2))
        if pooled == 0:
            continue
        effect = abs(mr - ml) / pooled
        if best is None or step_sse < best[4]:
            best = (effect, split, ml, mr, step_sse)

    # Two levels must explain the series substantially better than one line
    # does, not merely as well. A pure ramp fails this outright.
    if best is None or best[0] < STEP_SD or best[4] > 0.5 * line_sse:
        return None

    effect, split = best[0], best[1]
    # Report the real levels, not the detrended ones: "shifted up from 10% to
    # 18%" is what a user can check against the chart.
    before, after = _mean(levels[:split]), _mean(levels[split:])
    unit = series.get("unit", "")
    direction = "up" if after > before else "down"
    return Insight(
        factor=series.get("factor_id"),
        kind="step",
        text=(f"{_label(series)} shifted {direction} around "
              f"{points[split][1]}: {_fmt(before, unit)} before, "
              f"{_fmt(after, unit)} after.{_caveat(series)}"),
        notability=min(1.0, effect / 4.0),
        source=series.get("source"),
        at=points[split][1],
        before=before,
        after=after,
        effect_size=round(effect, 2),
    )


def _residuals(values: Sequence[float]) -> List[float]:
    """Values with their least-squares line removed."""
    n = len(values)
    xs = list(range(n))
    mx, my = _mean(xs), _mean(values)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return list(values)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, values)) / sxx
    intercept = my - slope * mx
    return [y - (intercept + slope * x) for x, y in zip(xs, values)]


def coverage_note(series: Dict[str, Any]) -> Optional[Insight]:
    """A static designation, stated rather than analysed.

    A green-belt percentage is a fact about the site, not a time series, and
    running a trend over it would be absurd. This is what a factor gets when
    every one of its points is the same carried-forward value.
    """
    all_points = series.get("points") or []
    points = [p for p in all_points if p.get("value") is not None]
    if not points:
        return None
    # A designation applies to every month of the window. A series that is
    # mostly gaps and happens to repeat one value where it does have data is a
    # broken measurement, not a constant fact about the site.
    if len(points) < 0.75 * len(all_points):
        return None
    values = {p["value"] for p in points}
    if len(values) != 1:
        return None
    value = points[0]["value"]
    if not isinstance(value, (int, float)):
        return None

    unit = series.get("unit", "")
    if unit == "%" and value <= 0:
        return None                     # "0% of this site is a national park"

    return Insight(
        factor=series.get("factor_id"),
        kind="static",
        text=f"{_label(series)}: {_fmt(float(value), unit)}.{_caveat(series)}",
        # Real, useful, and never the most interesting thing in a report.
        notability=0.35 if unit == "%" and value >= 10 else 0.2,
        source=series.get("source"),
        value=value,
    )


def gaps(series: Dict[str, Any]) -> Optional[Insight]:
    """How much of the window has no observation at all.

    Reported because a chart with a missing third looks similar to a complete
    one at a glance, and a conclusion drawn from it should not.
    """
    points = series.get("points") or []
    if len(points) < MIN_POINTS:
        return None
    missing = sum(1 for p in points if p.get("value") is None)
    share = missing / len(points)
    if share < 0.25:
        return None
    return Insight(
        factor=series.get("factor_id"),
        kind="coverage",
        text=(f"{_label(series)} has no data for {missing} of {len(points)} "
              f"months ({share * 100:.0f}%) — read its chart with that in "
              f"mind.{_caveat(series)}"),
        notability=0.3 + 0.4 * share,
        source=series.get("source"),
        missing=missing,
        total=len(points),
    )


TESTS = (trend, seasonal_anomaly, step_change, coverage_note, gaps)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
def for_series(series: Dict[str, Any]) -> List[Insight]:
    """Every finding for one factor."""
    found = []
    for test in TESTS:
        try:
            result = test(series)
        except Exception:                          # noqa: BLE001
            # An insight is a nicety. A bad number in one series must never
            # take down a report the user has already paid for.
            continue
        if result:
            found.append(result)

    # A factor that is one repeated value is a designation, not a series;
    # anything else the tests found about it is an artefact of that.
    if any(f["kind"] == "static" for f in found):
        found = [f for f in found if f["kind"] in ("static", "coverage")]
    return found


def summarise(report: Dict[str, Any], limit: int = 8) -> Dict[str, Any]:
    """Findings across a whole report, most notable first.

    Real observations outrank generated ones at equal notability. Demo data
    should not lead a report that also contains something real — it is still
    listed, still labelled, just not first.
    """
    series = (report or {}).get("series") or {}
    findings: List[Insight] = []
    for factor_id, one in series.items():
        if not isinstance(one, dict):
            continue
        findings.extend(for_series({**one, "factor_id": factor_id}))

    def rank(f: Insight) -> tuple:
        real = 1 if f.get("source") in ("earth-engine", "open-data") else 0
        return (real, f.get("notability", 0.0))

    findings.sort(key=rank, reverse=True)

    real_count = sum(1 for f in findings
                     if f.get("source") in ("earth-engine", "open-data"))
    return {
        "insights": findings[:limit],
        "counts": {
            "total": len(findings),
            "shown": min(limit, len(findings)),
            "from_real_data": real_count,
            "from_generated_data": len(findings) - real_count,
        },
    }
