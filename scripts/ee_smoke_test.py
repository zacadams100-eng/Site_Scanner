#!/usr/bin/env python3
"""
Earth Engine smoke test
=======================
Answers two questions, in order, and stops at the first one that fails:

  1. Do the credentials work at all?
  2. Is reduceRegion at 10 m fast enough for an interactive tool?

It calls the real functions from app.py — ndvi_image, landcover_image,
flood_proxy_image — so a clean run means the backend works, not merely that
Earth Engine is reachable.

Run it before running the app. If something is wrong, the failure here is far
easier to read than a 500 from FastAPI.

    export GOOGLE_APPLICATION_CREDENTIALS_JSON="$(cat service-account-key.json)"
    export EE_PROJECT="your-gcp-project-id"
    python scripts/ee_smoke_test.py

Optional: --lat/--lon to test somewhere other than Guildford, --year to change
the imagery year.
"""

import argparse
import json
import math
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Polygon sizes to time, in hectares. 2 ha is a paddock; 10,000 ha is a
# 10 km x 10 km block, well past what anyone would draw by hand — it's there to
# find where the cliff is.
AREA_STEPS_HA = [2, 25, 100, 500, 2_000, 10_000]

# How long a single /api/stats call can take before the product changes shape.
INTERACTIVE_MS = 2_000     # feels live
TOLERABLE_MS = 10_000      # needs a spinner, still usable


def square_around(lat: float, lon: float, area_ha: float) -> dict:
    """A GeoJSON square of roughly the requested area, centred on lat/lon."""
    side_m = math.sqrt(area_ha * 10_000.0)
    dlat = (side_m / 2.0) / 110_574.0
    dlon = (side_m / 2.0) / (111_320.0 * math.cos(math.radians(lat)))
    return {
        "type": "Polygon",
        "coordinates": [[
            [lon - dlon, lat - dlat],
            [lon + dlon, lat - dlat],
            [lon + dlon, lat + dlat],
            [lon - dlon, lat + dlat],
            [lon - dlon, lat - dlat],
        ]],
    }


class Step:
    """Times a block and prints a one-line verdict."""

    def __init__(self, label):
        self.label = label

    def __enter__(self):
        print(f"  {self.label:<52}", end="", flush=True)
        self.t0 = time.monotonic()
        return self

    def __exit__(self, exc_type, exc, tb):
        ms = (time.monotonic() - self.t0) * 1000
        self.ms = ms
        if exc_type is None:
            print(f"ok   {ms:8.0f} ms")
        else:
            print(f"FAIL {ms:8.0f} ms")
            print(f"\n    {exc_type.__name__}: {exc}\n")
            explain(exc)
        return False


HINTS = [
    ("not signed up",        "This Cloud project isn't registered for Earth Engine.\n"
                             "    Go to code.earthengine.google.com, and register the project\n"
                             "    (you'll be asked to pick commercial or noncommercial)."),
    ("permission",           "The service account can't reach the API. Two usual causes:\n"
                             "    - the Earth Engine API isn't enabled on the project, or\n"
                             "    - the service account lacks the Earth Engine Resource Viewer role."),
    ("api has not been used", "Enable the Earth Engine API on this project in the Cloud console,\n"
                             "    then wait a minute for it to propagate."),
    ("caller does not have",  "IAM role missing on the service account — add Earth Engine\n"
                             "    Resource Viewer (or Writer)."),
    ("invalid_grant",         "The key JSON is malformed, or the system clock is skewed."),
    ("quota",                 "You've hit a rate or compute quota. Wait, or check your EE plan."),
    ("too many pixels",       "maxPixels exceeded — the area is too big for this scale.\n"
                             "    This is a real finding: see the notes at the end."),
    ("timed out",             "Computation timed out. This is the answer to question 2 —\n"
                             "    see the notes at the end."),
    ("computation timed out", "Computation timed out. This is the answer to question 2 —\n"
                             "    see the notes at the end."),
]


def explain(exc):
    text = str(exc).lower()
    for needle, hint in HINTS:
        if needle in text:
            print(f"    → {hint}\n")
            return
    print("    → No specific hint for this one. The message above is Earth Engine's.\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", type=float, default=51.24, help="centre latitude (default: Guildford)")
    ap.add_argument("--lon", type=float, default=-0.57, help="centre longitude")
    ap.add_argument("--year", type=int, default=2024)
    args = ap.parse_args()

    print("\nEarth Engine smoke test")
    print("=" * 68)

    # --- Phase 0: environment, before importing anything -------------------
    print("\nEnvironment")
    key = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    project = os.environ.get("EE_PROJECT")
    if not key:
        print("  GOOGLE_APPLICATION_CREDENTIALS_JSON is not set.")
        print('  export GOOGLE_APPLICATION_CREDENTIALS_JSON="$(cat service-account-key.json)"')
        return 1
    if not project:
        print("  EE_PROJECT is not set.")
        print('  export EE_PROJECT="your-gcp-project-id"')
        return 1
    try:
        parsed = json.loads(key)
    except json.JSONDecodeError as e:
        print(f"  The key isn't valid JSON: {e}")
        print("  Did you export the file path instead of its contents?")
        return 1
    print(f"  service account   {parsed.get('client_email', '(no client_email in key!)')}")
    print(f"  key project       {parsed.get('project_id', '(none)')}")
    print(f"  EE_PROJECT        {project}")
    if parsed.get("project_id") and parsed["project_id"] != project:
        print("  note: the key's project and EE_PROJECT differ. That can be correct,")
        print("        but it's a common mistake — check it's deliberate.")

    # --- Phase 1: auth ------------------------------------------------------
    print("\n1. Credentials")
    try:
        with Step("importing app.py (runs init_earth_engine)") as s:
            import app
        init_ms = s.ms
    except Exception:
        print("  Stopping: nothing else can work until this does.")
        return 1

    import ee

    try:
        with Step("trivial server-side compute"):
            assert ee.Number(1).add(1).getInfo() == 2
    except Exception:
        print("  Stopping: authenticated, but compute isn't reaching the servers.")
        return 1

    # --- Phase 2: the datasets app.py actually uses -------------------------
    print("\n2. Datasets")
    ok = True
    for label, thunk in [
        ("Sentinel-2 composite band names",
         lambda: app.sentinel2_composite(args.year).bandNames().getInfo()),
        ("ESA WorldCover",
         lambda: app.landcover_image(args.year).bandNames().getInfo()),
        ("flood proxy (JRC water + SRTM)",
         lambda: app.flood_proxy_image().bandNames().getInfo()),
    ]:
        try:
            with Step(label):
                thunk()
        except Exception:
            ok = False
    if not ok:
        print("  One or more datasets are unreachable. Fix that before timing anything.")
        return 1

    # --- Phase 3: tile URLs, i.e. what /api/tile/* does ---------------------
    print("\n3. Tile URLs  (what /api/tile/* does — this is the map layer path)")
    tile_ms = {}
    for label, thunk in [
        ("NDVI getMapId", lambda: ee.Image(app.ndvi_image(args.year)).getMapId(
            {"min": -0.1, "max": 0.9})),
        ("land cover getMapId", lambda: ee.Image(app.landcover_image(args.year)).getMapId(
            {"min": 10, "max": 100})),
    ]:
        try:
            with Step(label) as s:
                thunk()
            tile_ms[label] = s.ms
        except Exception:
            pass

    # --- Phase 4: the actual question ---------------------------------------
    print(f"\n4. reduceRegion at 10 m  (what /api/stats does — {args.year})")
    print("     this is the number that decides whether the product works\n")
    print(f"  {'area':>10}  {'NDVI':>10}  {'land cover':>11}  {'flood':>9}  {'total':>9}")
    print(f"  {'-'*10}  {'-'*10}  {'-'*11}  {'-'*9}  {'-'*9}")

    results = []
    for area_ha in AREA_STEPS_HA:
        geom_json = square_around(args.lat, args.lon, area_ha)
        geom = ee.Geometry(geom_json)
        row = {"area_ha": area_ha}
        total = 0.0
        failed = None

        for name, image, scale, band in [
            ("ndvi", app.ndvi_image(args.year), 10, "NDVI"),
            ("landcover", app.landcover_image(args.year), 10, "Map"),
            ("flood", app.flood_proxy_image(), 30, "flood_proxy"),
        ]:
            reducer = (ee.Reducer.frequencyHistogram() if name == "landcover"
                       else ee.Reducer.mean())
            t0 = time.monotonic()
            try:
                image.reduceRegion(
                    reducer=reducer, geometry=geom, scale=scale, maxPixels=1e9
                ).get(band).getInfo()
                ms = (time.monotonic() - t0) * 1000
                row[name] = ms
                total += ms
            except Exception as e:
                row[name] = None
                failed = e
                break

        if failed is not None:
            print(f"  {area_ha:>8,} ha  ** failed: {type(failed).__name__} **")
            explain(failed)
            results.append(row)
            break

        row["total"] = total
        results.append(row)
        print(f"  {area_ha:>8,} ha  {row['ndvi']:>8.0f}ms  {row['landcover']:>9.0f}ms  "
              f"{row['flood']:>7.0f}ms  {total:>7.0f}ms")

    # --- Verdict -------------------------------------------------------------
    print("\n" + "=" * 68)
    print("What this means\n")

    usable = [r for r in results if r.get("total")]
    if not usable:
        print("  No size completed. Earth Engine is reachable but can't do the work —")
        print("  read the error above; it's the finding, not a bug to route around.")
        return 1

    interactive = [r["area_ha"] for r in usable if r["total"] <= INTERACTIVE_MS]
    tolerable = [r["area_ha"] for r in usable if r["total"] <= TOLERABLE_MS]
    biggest = max(r["area_ha"] for r in usable)

    if interactive:
        print(f"  Feels live (under {INTERACTIVE_MS/1000:.0f}s) up to {max(interactive):,} ha.")
    else:
        print(f"  Nothing came back under {INTERACTIVE_MS/1000:.0f}s — even the smallest shape")
        print("  needs a loading state.")
    if tolerable:
        print(f"  Usable with a spinner (under {TOLERABLE_MS/1000:.0f}s) up to {max(tolerable):,} ha.")
    if biggest < AREA_STEPS_HA[-1]:
        print(f"  Fell over above {biggest:,} ha.")

    slowest = max(usable, key=lambda r: r["total"])
    parts = {k: slowest[k] for k in ("ndvi", "landcover", "flood") if slowest.get(k)}
    if parts:
        worst = max(parts, key=parts.get)
        share = parts[worst] / slowest["total"] * 100
        print(f"\n  At {slowest['area_ha']:,} ha the cost is dominated by {worst} "
              f"({share:.0f}% of the total).")
        if worst == "ndvi":
            print("  That's the Sentinel-2 median composite — a year of imagery reduced")
            print("  per request. It is the first thing to attack if this is too slow:")
            print("    - narrow the date window (a season, not a year)")
            print("    - raise scale from 10 m to 20 m for the headline number")
            print("    - or precompute composites into an EE asset once per year")

    print("\n  Caching helps repeat views of the same site, not the first look.")
    print("  If the first look is too slow, that's a product-shape problem, not a")
    print("  performance-tuning one — and better to know now.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
