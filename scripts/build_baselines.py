#!/usr/bin/env python3
"""
Sample England, so a site's numbers can be compared with somewhere.

    python3 scripts/build_baselines.py                # ~60 points, the real factors
    python3 scripts/build_baselines.py --points 200   # slower, tighter percentiles
    python3 scripts/build_baselines.py --factor crime_density

A value on its own is not an answer. `crime_density 230` means nothing to the
land agent this product is for; "busier than four fifths of England" means
something immediately. That needs a yardstick, and this builds one.

## Why it samples rather than assumes

The fast version of this feature is to run `series.py` over a few hundred
points and call the spread a national average. It would cover all 269 factors
in an afternoon and be worthless: a fabricated yardstick against which a real
measurement is compared produces a percentile that looks authoritative and
means nothing. So this only ever asks the live sources, and only for factors
that have one — everything else gets no baseline, which is the honest answer.

## Needs ordinary internet

Same as `scripts/verify.py`. The development sandbox cannot reach any of these
hosts, so this is a thing you run from Cloud Shell or a laptop. It writes
`data/baselines.json`, which is committed — the sample is data, and rebuilding
it on every deploy would mean the comparison quietly changed under people.

## Cost

One AOI per point, and each real factor is one or more HTTP calls. Sixty points
is roughly ten minutes and is enough to place a value in a tenth. Two hundred
is roughly half an hour and buys a percentile you could quote. The script
prints progress and can be interrupted — it writes what it has.
"""

import argparse
import datetime as dt
import json
import math
import pathlib
import random
import sys
import time
from typing import Any, Dict, List

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import baselines                                       # noqa: E402
import catalog                                         # noqa: E402
import open_data                                       # noqa: E402
import routes_catalog                                  # noqa: E402

OUT = ROOT / "data" / "baselines.json"

# Sampling boxes across England, with a weight each, so the sample is not
# ninety points in the Home Counties. Weighted roughly by land area rather than
# by population: this is a land-analysis tool, and a baseline that
# over-represents cities would make every rural site look extraordinary.
#
# (west, south, east, north, weight)
REGIONS = [
    (-2.75, 50.00, -2.20, 51.05, 3),   # South West — Devon, Dorset
    (-3.60, 50.10, -4.60, 50.80, 2),   # Cornwall
    (-1.90, 50.80, -0.10, 51.40, 3),   # South, Wessex to Sussex
    (-0.60, 51.30, 0.90, 52.10, 3),    # South East and East Anglia
    (-2.70, 51.30, -1.10, 52.60, 3),   # Cotswolds, Severn, west Midlands
    (-1.40, 52.10, 0.40, 53.10, 3),    # east Midlands and Lincolnshire
    (-3.00, 53.00, -1.20, 54.10, 3),   # Pennines, Yorkshire, Lancashire
    (-3.10, 54.10, -1.30, 55.20, 2),   # Cumbria, Northumberland, Durham
]


def sample_points(n: int, seed: int) -> List[tuple]:
    """Points spread over the regions, deterministically.

    Seeded so a rebuild with the same arguments produces the same sample. A
    baseline that moves every time somebody reruns the script is a baseline
    nobody can reason about.
    """
    rng = random.Random(seed)
    total = sum(r[4] for r in REGIONS)
    out: List[tuple] = []
    for west, south, east, north, weight in REGIONS:
        count = max(1, round(n * weight / total))
        lo_x, hi_x = min(west, east), max(west, east)
        for _ in range(count):
            out.append((rng.uniform(south, north), rng.uniform(lo_x, hi_x)))
    rng.shuffle(out)
    return out[:n]


def square(lat: float, lon: float, half_km: float = 0.6) -> dict:
    dlat = half_km / 111.0
    dlon = half_km / (111.0 * max(0.2, abs(math.cos(math.radians(lat)))))
    return {"type": "Polygon", "coordinates": [[
        [lon - dlon, lat - dlat], [lon + dlon, lat - dlat],
        [lon + dlon, lat + dlat], [lon - dlon, lat + dlat],
        [lon - dlon, lat - dlat]]]}


def recent_steps(n: int = 3) -> List[str]:
    today = dt.date.today()
    y, m = today.year, today.month - 3
    while m <= 0:
        m += 12
        y -= 1
    steps = []
    for _ in range(n):
        steps.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return list(reversed(steps))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--points", type=int, default=60)
    ap.add_argument("--seed", type=int, default=20260809)
    ap.add_argument("--factor", action="append", default=None,
                    help="only these factors; repeatable")
    args = ap.parse_args()

    registry: Dict[str, Any] = {}
    open_data.install(registry, {})
    if not registry:
        print("No factors registered — is `requests` installed?", file=sys.stderr)
        return 1

    wanted = args.factor or sorted(registry)
    unknown = [f for f in wanted if f not in registry]
    if unknown:
        print(f"Not real factors, so they cannot have a baseline: {unknown}",
              file=sys.stderr)
        return 1

    points = sample_points(args.points, args.seed)
    steps = recent_steps()
    collected: Dict[str, List[float]] = {f: [] for f in wanted}

    print(f"Sampling {len(points)} points across England for "
          f"{len(wanted)} factors.")
    print("Interrupt at any time — whatever has been gathered is written.\n")

    t0 = time.perf_counter()
    try:
        for i, (lat, lon) in enumerate(points, 1):
            geom = square(lat, lon)
            got = 0
            for factor_id in wanted:
                try:
                    pts = registry[factor_id](geom, steps, 120.0)
                except Exception:                       # noqa: BLE001
                    # A point in the sea, a district with no sales, a source
                    # having a bad minute. One missing sample is not worth
                    # stopping a half-hour run for.
                    continue
                vals = [p["value"] for p in pts
                        if isinstance(p.get("value"), (int, float))]
                if vals:
                    collected[factor_id].append(float(vals[-1]))
                    got += 1
            print(f"  {i:3d}/{len(points)}  {lat:6.3f}, {lon:7.3f}  "
                  f"{got}/{len(wanted)} factors  "
                  f"({time.perf_counter() - t0:.0f}s)", flush=True)
    except KeyboardInterrupt:
        print("\nInterrupted — writing what was gathered.")

    factors: Dict[str, Any] = {}
    for factor_id, values in collected.items():
        if len(values) < baselines.MIN_SAMPLE:
            continue
        ordered = sorted(values)
        factors[factor_id] = {
            "samples": ordered,
            "p10": round(ordered[int(0.10 * (len(ordered) - 1))], 4),
            "p50": round(ordered[int(0.50 * (len(ordered) - 1))], 4),
            "p90": round(ordered[int(0.90 * (len(ordered) - 1))], 4),
            "unit": catalog.FACTOR_BY_ID.get(factor_id, {}).get("unit", ""),
            "basis": "sampled",
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "built": dt.date.today().isoformat(),
        "method": (f"{len(points)} AOIs of 1.2 km sampled across 8 English "
                   f"regions weighted by land area, seed {args.seed}; latest "
                   f"non-gap value per factor"),
        "factors": factors,
    }, indent=1, sort_keys=True))

    print(f"\nWrote {OUT.relative_to(ROOT)}")
    print(f"{len(factors)} factors have a usable baseline "
          f"(at least {baselines.MIN_SAMPLE} samples).")
    thin = [f for f, v in collected.items()
            if 0 < len(v) < baselines.MIN_SAMPLE]
    if thin:
        print(f"Too few samples to be worth quoting: {', '.join(sorted(thin))}")
        print("  Re-run with more --points, or accept that these have no "
              "yardstick.")
    empty = [f for f, v in collected.items() if not v]
    if empty:
        print(f"Returned nothing anywhere: {', '.join(sorted(empty))}")
        print("  That is a finding — check them with scripts/verify.py.")
    print("\nCommit data/baselines.json. The sample is data, and rebuilding it "
          "on every deploy would change the comparison under people.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
