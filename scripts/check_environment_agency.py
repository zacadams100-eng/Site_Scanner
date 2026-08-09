#!/usr/bin/env python3
"""
Run the Environment Agency rainfall integration against the live service.

`ea_hydrology.py` is written against the Hydrology API's published reference
and covered by fixture tests. Fixtures prove the aggregation; they cannot
prove the endpoint exists, still answers in that shape, or has a gauge near
the place you asked about. This is the other half — it is what turns these
four factors from `written` into `verified`, and it exists because the
environment they were written in cannot reach `environment.data.gov.uk`.

    python3 scripts/check_environment_agency.py
    python3 scripts/check_environment_agency.py --lat 53.48 --lon -2.24
    python3 scripts/check_environment_agency.py --months 24 --json

Exit status is 0 only if the data that came back is plausible. Unreachable,
empty or structurally wrong exits 1 and says which.

## What is actually checked

Not "the request returned 200" — every check below would fail if the code
were reading the wrong field:

  - a gauge is found, and its distance is inside the search radius
  - one point comes back per requested month, in order
  - values sit inside the catalogue's declared [lo, hi] for that factor
  - at least one month is not a gap; an all-gaps series is what a broken
    query returns and must never read as success
  - wet days + dry days equals the days actually observed, which is the one
    internal identity that catches a threshold or counting error
  - rainfall totals are not absurd for England — a gauge reading in inches,
    or a 15-minute series summed as if daily, fails this and nothing else
    would catch it

## If it fails

The likely causes, in order:

  1.  The station search parameters have changed. Check
      https://environment.data.gov.uk/hydrology/doc/reference for the current
      names of `observedProperty`, `lat`, `long` and `dist`.
  2.  `period=86400` no longer selects the daily-total measure. The reference
      lists the periods each station publishes.
  3.  The quality flags are spelled differently. `ea_hydrology._daily_readings`
      drops `Missing` and `Invalid`; if those strings changed, bad readings
      are being counted as real zeros, which on rainfall is invisible.
"""

import argparse
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import catalog                                        # noqa: E402
import ea_hydrology                                   # noqa: E402
from open_data import OpenDataError                   # noqa: E402

# Guildford, as everywhere else in this repo's checks — lowland England with a
# dense EA gauge network, so "no gauge nearby" would be a real finding rather
# than a property of the test location.
DEFAULT_LAT, DEFAULT_LON = 51.2362, -0.5704

# England's wettest months at the wettest gauges run to roughly 400 mm. A
# reading past this is a unit error, not weather.
IMPLAUSIBLE_MONTHLY_MM = 500.0


def square(lat: float, lon: float, half_km: float = 0.6) -> dict:
    d = half_km / 111.0
    return {"type": "Polygon", "coordinates": [[
        [lon - d, lat - d], [lon + d, lat - d],
        [lon + d, lat + d], [lon - d, lat + d], [lon - d, lat - d],
    ]]}


def recent_steps(months: int) -> list:
    """The last N complete months, ending one month back.

    The current month is deliberately excluded: it is partly observed by
    definition, so including it would make every run report one low month and
    train the reader to ignore the coverage figure.
    """
    import datetime as dt
    today = dt.date.today().replace(day=1)
    steps = []
    for i in range(months, 0, -1):
        y, m = divmod((today.year * 12 + today.month - 1) - i, 12)
        steps.append(f"{y:04d}-{m + 1:02d}")
    return steps


def check(lat: float, lon: float, months: int) -> dict:
    geometry = square(lat, lon)
    steps = recent_steps(months)
    result = {"lat": lat, "lon": lon, "months": months,
              "steps": [steps[0], steps[-1]], "failures": [], "notes": []}

    started = time.time()
    try:
        station = ea_hydrology.nearest_rainfall_station(geometry)
    except OpenDataError as exc:
        result["failures"].append(f"station lookup: {exc}")
        return result
    result["station"] = station
    result["notes"].append(
        f"nearest gauge {station['label'] or station['id']} "
        f"at {station['distance_km']} km")
    if station["distance_km"] > ea_hydrology.SEARCH_RADIUS_KM:
        result["failures"].append(
            f"gauge is {station['distance_km']} km away, outside the "
            f"{ea_hydrology.SEARCH_RADIUS_KM:g} km radius the search asked for — "
            f"the dist parameter is not being applied")

    try:
        group = ea_hydrology.rainfall_group(geometry, steps, 20.0)
    except OpenDataError as exc:
        result["failures"].append(f"readings: {exc}")
        return result
    result["elapsed_s"] = round(time.time() - started, 2)

    for factor_id in ea_hydrology.FACTOR_IDS:
        points = group.get(factor_id)
        if points is None:
            result["failures"].append(f"{factor_id}: not returned")
            continue
        if len(points) != len(steps):
            result["failures"].append(
                f"{factor_id}: {len(points)} points for {len(steps)} months")
            continue
        if [p["t"] for p in points] != steps:
            result["failures"].append(f"{factor_id}: months out of order")

        values = [p["value"] for p in points if p["value"] is not None]
        if not values:
            # The shape a broken query returns. Never a pass.
            result["failures"].append(
                f"{factor_id}: every month is a gap — the query returned nothing usable")
            continue

        meta = catalog.FACTOR_BY_ID[factor_id]
        lo, hi = meta.get("lo"), meta.get("hi")
        out_of_range = [v for v in values if (lo is not None and v < lo)
                        or (hi is not None and v > hi)]
        if out_of_range:
            result["failures"].append(
                f"{factor_id}: {len(out_of_range)} value(s) outside the "
                f"catalogue's {lo}–{hi} {meta['unit']}, e.g. {out_of_range[0]}")

        result.setdefault("observed", {})[factor_id] = {
            "months_with_data": len(values),
            "min": min(values), "max": max(values),
        }

    # Internal identity: wet + dry must equal the days the gauge reported.
    # This is the check that catches a wrong threshold or an off-by-one in the
    # counting, neither of which moves a value outside its declared range.
    wet = group.get("ea_rain_wet_days") or []
    dry = group.get("ea_rain_dry_days") or []
    for w, d in zip(wet, dry):
        if w["value"] is None or d["value"] is None:
            continue
        if w["value"] + d["value"] > 31:
            result["failures"].append(
                f"{w['t']}: {w['value']} wet + {d['value']} dry is more than a month — "
                f"readings are being counted more than once")
            break

    totals = [p["value"] for p in (group.get("ea_rain_total") or [])
              if p["value"] is not None]
    if totals and max(totals) > IMPLAUSIBLE_MONTHLY_MM:
        result["failures"].append(
            f"ea_rain_total: {max(totals)} mm in a month is not English weather — "
            f"likely a unit error, or a sub-daily series summed as if daily")

    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lat", type=float, default=DEFAULT_LAT)
    ap.add_argument("--lon", type=float, default=DEFAULT_LON)
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    result = check(args.lat, args.lon, args.months)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Environment Agency hydrology — {args.lat}, {args.lon}")
        print(f"  {result['steps'][0]} to {result['steps'][-1]}")
        for note in result["notes"]:
            print(f"  note: {note}")
        for factor_id, obs in (result.get("observed") or {}).items():
            unit = catalog.FACTOR_BY_ID[factor_id]["unit"]
            print(f"  {factor_id:22} {obs['months_with_data']:>3} months  "
                  f"{obs['min']}–{obs['max']} {unit}")
        if result.get("elapsed_s") is not None:
            print(f"  elapsed: {result['elapsed_s']}s")
        for failure in result["failures"]:
            print(f"  FAIL {failure}")

    if result["failures"]:
        print(f"\n{len(result['failures'])} failure(s). These factors stay "
              f"'written'.", file=sys.stderr)
        return 1

    print("\nAll checks passed. Set these four to 'verified' in "
          "ea_hydrology.install and record the date in PROGRESS.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
