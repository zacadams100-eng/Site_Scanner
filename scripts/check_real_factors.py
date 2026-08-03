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


def show(name, points, unit, limit=6):
    got = [p for p in points if p["value"] is not None]
    gaps = len(points) - len(got)
    print(f"\n  {name}")
    if not got:
        print(f"    no data at all across {len(points)} months")
        return
    shown = got[:limit]
    for p in shown:
        v = p["value"]
        v = f"{v:.3f}" if isinstance(v, float) else str(v)
        print(f"    {p['t']}  {v:>14} {unit:<6} "
              f"coverage {p['valid_fraction'] * 100:>3.0f}%")
    if len(got) > limit:
        print(f"    … {len(got) - limit} more")
    print(f"    {len(got)} values, {gaps} gaps")


def main() -> int:
    year = sys.argv[1] if len(sys.argv) > 1 else None
    steps = ([f"{year}-{m:02d}" for m in range(1, 13)] if year
             else [f"{y}-{m:02d}" for y in range(2019, 2026) for m in range(1, 13)])

    try:
        import ee  # noqa: F401
        from app import init_earth_engine
        init_earth_engine()
    except BaseException as e:
        print(f"✗ Earth Engine would not start: {type(e).__name__}: {e}")
        print("  Run `source ./setup.sh` first.")
        return 1
    print("✓ Earth Engine ready")

    import catalog
    import ee_series

    problems: List[str] = []
    print(f"\nChecking {len(ee_series.REAL_SERIES)} real factors over "
          f"{len(steps)} months, {AREA_HA:.0f} ha of fenland arable.")

    for factor_id, fn in ee_series.REAL_SERIES.items():
        meta = catalog.FACTOR_BY_ID[factor_id]
        t0 = time.perf_counter()
        try:
            points = fn(SITE, steps, AREA_HA)
        except Exception as e:
            problems.append(f"{factor_id} raised: {e}")
            print(f"\n  {meta['name']}\n    ✗ {e}")
            continue
        elapsed = time.perf_counter() - t0

        show(meta["name"], points, meta["unit"])
        print(f"    took {elapsed:.1f}s")

        if meta["kind"] == "categorical":
            allowed = set(catalog.CLASS_VALUES.get(factor_id, []))
            bad = {p["value"] for p in points
                   if p["value"] is not None and p["value"] not in allowed}
            if bad:
                problems.append(
                    f"{factor_id} returned classes the catalogue does not "
                    f"list: {sorted(bad)}")
        elif factor_id == "ndvi":
            problems += check_continuous("NDVI", points, -1.0, 1.0,
                                         "index", expect_seasons=True)
        elif factor_id == "air_temp_mean":
            problems += check_continuous("Air temperature", points, -15.0, 35.0,
                                         "°C", expect_seasons=True)
        else:
            lo = meta.get("lo")
            hi = meta.get("hi")
            problems += check_continuous(
                meta["name"], points,
                lo if lo is not None else -1e9,
                hi if hi is not None else 1e9,
                meta["unit"], expect_seasons=False)

    print("\n" + "=" * 58)
    if problems:
        print(f"✗ {len(problems)} problem(s):")
        for p in problems:
            print(f"  · {p}")
        return 1

    print("✓ Every real factor returned plausible values.")
    print("  Start the backend and draw a small shape:")
    print("      uvicorn app:app --port 8000")
    return 0


if __name__ == "__main__":
    sys.exit(main())
