"""
Check every factor that claims to be real, in one go.

check_real_ndvi.py proves one factor works. This proves all of them, and each
has its own idea of what "sensible" means — an NDVI of 15 is nonsense, an air
temperature of 15 is a mild afternoon. Guessing from a bare table of numbers
is how the first NDVI run got declared a success while being wrong, so the
expectations are written down here instead.

    cd ~/Site_Scanner
    source ./setup.sh
    python3 scripts/check_real_factors.py

Add a year to test a shorter, faster window while debugging:

    python3 scripts/check_real_factors.py 2024

Exit code is 0 only if every factor passes. Nothing is written or modified —
this reads imagery and prints.
"""

import pathlib
import sys
import time
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# This repository is public and CI logs are public with it. Earth Engine
# embeds the credentials dict in some errors, so nothing prints an
# exception from that path raw.
from redaction import safe_message

# Intensive arable in the Cambridgeshire fens: the strongest seasonal signal
# in England, so a flat result means something is wrong rather than meaning
# the land is simply mixed. See the note in check_real_ndvi.py.
SITE = {
    "type": "Polygon",
    "coordinates": [[
        [0.100, 52.550], [0.120, 52.550],
        [0.120, 52.570], [0.100, 52.570], [0.100, 52.550],
    ]],
}
AREA_HA = 301.0


def summer_winter(points: List[Dict[str, Any]]):
    """Mean of Jun–Aug and of Dec–Feb, ignoring gaps."""
    def mean_of(months):
        vals = [p["value"] for p in points
                if p["value"] is not None and p["t"][5:7] in months]
        return sum(vals) / len(vals) if vals else None
    return mean_of({"06", "07", "08"}), mean_of({"12", "01", "02"})


def check_continuous(name, points, lo, hi, unit, expect_seasons):
    """Range check plus, where it applies, that summer really is warmer."""
    got = [p for p in points if p["value"] is not None]
    if not got:
        return [f"every month of {name} came back empty"]

    problems = []
    values = [p["value"] for p in got]
    if min(values) < lo or max(values) > hi:
        problems.append(
            f"{name} ranges {min(values):.2f} to {max(values):.2f} {unit}, "
            f"outside the plausible {lo} to {hi}")

    if expect_seasons:
        summer, winter = summer_winter(points)
        if summer is not None and winter is not None:
            if summer <= winter:
                problems.append(
                    f"{name} summer ({summer:.2f}) is not above winter "
                    f"({winter:.2f}) — that is backwards")
            elif abs(summer - winter) < 0.1:
                problems.append(
                    f"{name} barely moves between summer and winter "
                    f"({abs(summer - winter):.3f}) — too flat to be real")
    return problems


def summarise(name, unit, points, seconds):
    """One line per factor. With two dozen factors a table each is unreadable,
    and the thing worth seeing at a glance is the range and the gap count."""
    got = [p for p in points if p["value"] is not None]
    gaps = len(points) - len(got)

    if not got:
        print(f"  {name:26} {unit:<8} {'—':>20}   {gaps:>2} gaps   {seconds:>5.1f}s")
        return

    values = [p["value"] for p in got]
    if isinstance(values[0], str):
        distinct = sorted(set(values))
        span = distinct[0] if len(distinct) == 1 else f"{len(distinct)} classes"
        print(f"  {name:26} {unit:<8} {span:>20}   {gaps:>2} gaps   {seconds:>5.1f}s")
        return

    lo, hi = min(values), max(values)
    print(f"  {name:26} {unit:<8} {lo:>9.2f} to {hi:>7.2f}   "
          f"{gaps:>2} gaps   {seconds:>5.1f}s")


# Factors whose seasonality is a genuine correctness signal. A flat NDVI or a
# summer colder than winter means the pipeline is wrong, not that the weather
# was odd — that is exactly the failure the first NDVI run hid behind a tick.
SEASONAL = {"ndvi", "evi", "savi", "msavi", "gndvi", "chlorophyll_index",
            "air_temp_mean", "air_temp_max", "air_temp_min",
            "lst_day", "lst_night", "growing_degree_days"}


def check_factor(factor_id, meta, points, catalog) -> List[str]:
    """Plausibility for one factor, using what the catalogue already declares."""
    if meta["kind"] == "categorical":
        allowed = set(catalog.CLASS_VALUES.get(factor_id, []))
        bad = {p["value"] for p in points
               if p["value"] is not None and p["value"] not in allowed}
        if bad:
            return [f"{factor_id} returned classes the catalogue does not "
                    f"list: {sorted(bad)}"]
        return []

    lo = meta.get("lo")
    hi = meta.get("hi")
    return check_continuous(
        meta["name"], points,
        lo if lo is not None else -1e9,
        hi if hi is not None else 1e9,
        str(meta["unit"]),
        expect_seasons=factor_id in SEASONAL,
    )


def main() -> int:
    year = sys.argv[1] if len(sys.argv) > 1 else None
    steps = ([f"{year}-{m:02d}" for m in range(1, 13)] if year
             else [f"{y}-{m:02d}" for y in range(2019, 2026) for m in range(1, 13)])

    try:
        import ee  # noqa: F401
        from app import init_earth_engine
        init_earth_engine()
    except BaseException as e:
        print(f"✗ Earth Engine would not start: {safe_message(e)}")
        print("  Run `source ./setup.sh` first.")
        return 1
    print("✓ Earth Engine ready")

    import catalog
    import ee_series

    print(f"\nChecking {len(ee_series.REAL_SERIES)} real factors over "
          f"{len(steps)} months, {AREA_HA:.0f} ha of fenland arable.")

    # Grouped by base, because that is how the queries are actually batched.
    # Every factor after the first in a group is served from one shared pass,
    # which is why their timings collapse to nothing — that is the sharing
    # working, not a measurement error.
    by_base: Dict[str, List[str]] = {}
    for factor_id in ee_series.REAL_SERIES:
        by_base.setdefault(catalog.FACTOR_BY_ID[factor_id]["base"], []).append(factor_id)

    problems: List[str] = []
    for base_id, factor_ids in by_base.items():
        print(f"\n{catalog.BASE_BY_ID[base_id]['name']}")
        print(f"  {'factor':26} {'unit':<8} {'range':>20}   gaps    time")
        print("  " + "-" * 68)

        for factor_id in factor_ids:
            meta = catalog.FACTOR_BY_ID[factor_id]
            t0 = time.perf_counter()
            try:
                points = ee_series.REAL_SERIES[factor_id](SITE, steps, AREA_HA)
            except Exception as e:
                problems.append(f"{factor_id} raised: {safe_message(e)}")
                print(f"  {meta['name']:26} ✗ {safe_message(e)}")
                continue
            summarise(meta["name"], str(meta["unit"]), points,
                      time.perf_counter() - t0)

            # A source that published nothing in this window is not a fault.
            # WorldCover only ever released 2020 and 2021, so checking 2024
            # finds nothing and should say so rather than fail.
            if not ee_series.covers(factor_id, steps):
                start, end = ee_series.FACTOR_COVERAGE[factor_id]
                note = f"(published {start} to {end or 'now'})"
                print(f"  {'':26} {'':8} {note:>20}")
                continue

            problems += check_factor(factor_id, meta, points, catalog)

    print("\n" + "=" * 74)
    if problems:
        print(f"✗ {len(problems)} problem(s):")
        for p in problems:
            print(f"  · {p}")
        return 1

    print(f"✓ All {len(ee_series.REAL_SERIES)} factors returned plausible values.")
    print("  Start the backend and draw a small shape:")
    print("      uvicorn app:app --port 8000")
    return 0


if __name__ == "__main__":
    sys.exit(main())
