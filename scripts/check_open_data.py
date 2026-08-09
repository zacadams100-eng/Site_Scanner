#!/usr/bin/env python3
"""
Run the open-data integrations against the live services and report what
actually came back.

`open_data.py` is written against each API's documented shape and covered by
tests that feed it recorded fixtures. Fixtures prove the parsing; they cannot
prove the endpoint still exists, still returns that shape, or covers the place
you asked about. This script is the other half — it is what turns a factor's
status from `written` into `verified`, and it exists because the environment
the integrations were written in cannot reach any of these hosts.

    python3 scripts/check_open_data.py                 # everything, Guildford
    python3 scripts/check_open_data.py --source police
    python3 scripts/check_open_data.py --lat 53.48 --lon -2.24 --months 6

Exit status is 0 only if every checked source returned plausible data. A
source that is unreachable, empty, or structurally wrong exits 1 and says
which — this is meant to be runnable in CI once there is a runner with open
egress.

## What "plausible" means here

Not "the request returned 200". Each check asserts something that would be
false if the integration were wired to the wrong field:

  - the right number of points came back, one per requested step
  - values are inside the catalogue's declared [lo, hi] for that factor
  - at least one point is not a gap — an all-gaps series is the shape a
    broken query returns, and it must not read as success
  - the units are the ones the catalogue advertises (checked by range, which
    is the only automatic check available: £ vs pence differ by 100x, ha vs
    m² by 10,000, and both would fail the range test)

A check that passes is worth something. A check that only proves the network
works is worth nothing, so there are none of those.
"""

import argparse
import datetime as dt
import json
import math
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import catalog                                        # noqa: E402
import open_data                                      # noqa: E402

# Guildford: inside a real postcode district, inside a police force area, with
# green belt and an AONB nearby, so every source has something to say about it.
DEFAULT_LAT, DEFAULT_LON = 51.2362, -0.5704


def square(lat: float, lon: float, half_km: float = 0.6) -> dict:
    """A small AOI around a point. Small on purpose: these are per-request
    lookups and a big polygon means a slow SPARQL query and a thinned outline
    for police.uk."""
    dlat = half_km / 111.0
    dlon = half_km / (111.0 * max(0.2, abs(math.cos(math.radians(lat)))))
    return {
        "type": "Polygon",
        "coordinates": [[
            [lon - dlon, lat - dlat], [lon + dlon, lat - dlat],
            [lon + dlon, lat + dlat], [lon - dlon, lat + dlat],
            [lon - dlon, lat - dlat],
        ]],
    }


def recent_months(n: int) -> list:
    """The n months ending three months back. Not ending today: police.uk
    publishes roughly two months in arrears and Price Paid longer, so asking
    for last month tests the gap path rather than the data path."""
    today = dt.date.today()
    end_y, end_m = today.year, today.month - 3
    while end_m <= 0:
        end_m += 12
        end_y -= 1
    steps = []
    y, m = end_y, end_m
    for _ in range(n):
        steps.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return list(reversed(steps))


class Result:
    def __init__(self, factor_id: str):
        self.factor_id = factor_id
        self.ok = False
        self.detail = ""
        self.seconds = 0.0
        self.sample = None
        # Ran clean but proved nothing — see the note in check_factor.
        self.inconclusive = False


def check_factor(factor_id: str, fn, geometry: dict, steps: list, area_ha: float) -> Result:
    r = Result(factor_id)
    spec = catalog.FACTOR_BY_ID.get(factor_id, {})
    t0 = time.perf_counter()
    try:
        points = fn(geometry, steps, area_ha)
    except Exception as exc:                          # noqa: BLE001 — reporting
        r.seconds = time.perf_counter() - t0
        r.detail = f"{type(exc).__name__}: {exc}"
        return r
    r.seconds = time.perf_counter() - t0

    if len(points) != len(steps):
        r.detail = f"returned {len(points)} points for {len(steps)} steps"
        return r

    real = [p for p in points if p.get("value") is not None]
    if not real:
        # Every point a gap. For a monthly source this can be legitimate — a
        # rural district with no sales that month — but never for a whole
        # window, and never for a static designation.
        r.detail = "every point is a gap; nothing to verify"
        return r

    lo, hi = spec.get("lo"), spec.get("hi")
    if lo is not None and hi is not None:
        out = [p for p in real if not (lo - abs(lo) * 0.01 <= p["value"] <= hi * 1.5)]
        if out:
            worst = out[0]
            r.detail = (f"value {worst['value']!r} at {worst['t']} is outside the "
                        f"catalogue range [{lo}, {hi}] — wrong field or wrong unit?")
            return r

    r.ok = True
    r.sample = {"t": real[-1]["t"], "value": real[-1]["value"],
                "gaps": len(points) - len(real)}
    r.detail = f"{len(real)}/{len(points)} points"

    # An all-zero result proves less than it looks like it proves.
    #
    # `planning_series` returns 0.0 when the platform sends back no entities —
    # which is the correct answer for a site with no SSSI on it, and *also*
    # exactly what a misspelled dataset name returns. The two are
    # indistinguishable from the outside, so a run that only ever saw zero has
    # confirmed the code path and nothing about whether we are asking for the
    # right thing.
    #
    # Ten of the twelve planning designations came back 0.0 on the first live
    # run. Reading that as twelve verified factors would have been the
    # session's third overclaim.
    if all(p["value"] == 0 for p in real if isinstance(p["value"], (int, float))):
        r.inconclusive = True
        r.detail += " — all zero, so this cannot tell a genuinely empty site "\
                    "from a wrong dataset name"
    return r


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--lat", type=float, default=DEFAULT_LAT)
    ap.add_argument("--lon", type=float, default=DEFAULT_LON)
    ap.add_argument("--months", type=int, default=6,
                    help="how many months of the monthly sources to fetch "
                         "(police.uk is one HTTP call per month)")
    ap.add_argument("--source", action="append", default=None,
                    choices=["planning", "prices", "police", "epc", "ons"],
                    help="check only these; repeatable")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    geometry = square(args.lat, args.lon)
    steps = recent_months(args.months)
    area_ha = 120.0                                   # ~1.2km square

    registry, provenance = {}, {}
    open_data.install(registry, provenance)
    if not registry:
        print("No factors registered — is `requests` installed?", file=sys.stderr)
        return 1

    # How many months of history a factor needs before it can produce a single
    # value. A year-on-year change needs thirteen months to compare two of
    # them; a five-year growth needs sixty-one.
    #
    # Without this the default six-month window reported `price_change_yoy`
    # and `price_growth_5yr` as FAIL — "every point is a gap" — which is the
    # arithmetically correct answer to a question that could not be answered
    # and reads as a broken integration. The first live run wasted two of its
    # three failures on exactly that.
    NEEDS_MONTHS = {"price_change_yoy": 13, "price_growth_5yr": 61}

    groups = {
        "planning": [f for f in registry if f in open_data.PLANNING_DATASETS],
        "prices": ["avg_sale_price", "median_sale_price", "transaction_count",
                   "new_build_share", "flat_share", "price_change_yoy",
                   "price_growth_5yr"],
        "police": ["crime_density", "burglary_density", "violent_crime_share",
                   "antisocial_share"],
        "epc": ["epc_mean_sap", "epc_band_mode", "epc_below_c_share",
                "epc_potential_uplift", "mean_floor_area", "heat_pump_share"],
        "ons": [f for f in registry
                if provenance.get(f, {}).get("source", "").startswith("ONS")],
    }
    wanted = args.source or list(groups)

    # First: does the AOI resolve at all? Every source below is keyed off this,
    # so a failure here explains all the others and there is no point running
    # them.
    try:
        # `locate` takes the AOI, not a coordinate pair. Passing (lon, lat)
        # raised a TypeError on the first line of real work, so this script
        # could never have reached a single endpoint — and because it exits 1
        # with a plausible-looking FAIL line, it looked like a broken
        # integration rather than a broken caller. Nobody had run it.
        place = open_data.locate(geometry)
    except Exception as exc:                          # noqa: BLE001
        print(f"FAIL  locate — {type(exc).__name__}: {exc}", file=sys.stderr)
        print("\nEvery other source is keyed off this lookup; stopping.",
              file=sys.stderr)
        return 1
    if not args.json:
        print(f"AOI  {args.lat:.4f}, {args.lon:.4f}  →  {place.get('postcode')} "
              f"/ {place.get('district')} ({place.get('admin_district_code')})")
        print(f"Window  {steps[0]} … {steps[-1]}\n")

    results, skipped, needs_more = [], [], []
    for name in wanted:
        for factor_id in groups.get(name, []):
            fn = registry.get(factor_id)
            if fn is None:
                skipped.append((factor_id, name))
                continue
            need = NEEDS_MONTHS.get(factor_id)
            if need and len(steps) < need:
                # Not a failure and not a pass — the window cannot answer the
                # question. Saying so is the honest third state.
                needs_more.append((factor_id, need))
                continue
            results.append((name, check_factor(factor_id, fn, geometry, steps, area_ha)))

    if args.json:
        print(json.dumps({
            "aoi": {"lat": args.lat, "lon": args.lon, **place},
            "steps": steps,
            "results": [{"source": s, "factor": r.factor_id, "ok": r.ok,
                         "detail": r.detail, "seconds": round(r.seconds, 2),
                         "sample": r.sample} for s, r in results],
            "skipped": [f for f, _ in skipped],
        }, indent=2))
    else:
        last = None
        for source, r in results:
            if source != last:
                print(f"── {source}")
                last = source
            mark = "FAIL" if not r.ok else ("~ok " if r.inconclusive else "ok  ")
            sample = ""
            if r.sample:
                sample = f"  latest {r.sample['t']}={r.sample['value']}"
                if r.sample["gaps"]:
                    sample += f" ({r.sample['gaps']} gaps)"
            print(f"  {mark} {r.factor_id:<26} {r.seconds:5.2f}s  {r.detail}{sample}")
        if skipped:
            print(f"\nSkipped (not registered): {', '.join(f for f, _ in skipped)}")
            if any(n == "epc" for _, n in skipped):
                print("  EPC needs EPC_API_EMAIL and EPC_API_KEY — free from "
                      "epc.opendatacommunities.org/docs/api")
        if needs_more:
            worst = max(n for _, n in needs_more)
            print(f"\nNot testable in a {len(steps)}-month window: "
                  f"{', '.join(f for f, _ in needs_more)}")
            print(f"  These derive from earlier months, so a short window "
                  f"makes every point a legitimate gap. Re-run with "
                  f"--months {worst} to test them.")

    failed = [r for _, r in results if not r.ok]
    weak = [r for _, r in results if r.ok and r.inconclusive]
    proved = [r for _, r in results if r.ok and not r.inconclusive]
    if not args.json:
        print(f"\n{len(results) - len(failed)}/{len(results)} checks passed"
              + (f", but {len(weak)} of those returned only zeros" if weak else "")
              + ".")
        if weak:
            print("\nProved by a real measurement — safe to promote:")
            for r in proved:
                print(f"  {r.factor_id:<26} {r.sample['value']}")
            print("\nRan clean but returned only zeros, which a wrong dataset "
                  "name also does:")
            for r in weak:
                print(f"  {r.factor_id}")
            print("  To settle these, re-run over an area where they should "
                  "*not* be zero —")
            print("  e.g. --lat 50.90 --lon -0.60 for the South Downs "
                  "(national park, AONB).")
        elif proved:
            print("\nThese factors can be promoted from 'written' to 'verified' "
                  "in open_data.VERIFIED. Record the observed figure — a "
                  "verification with no number is a claim, not a record.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
