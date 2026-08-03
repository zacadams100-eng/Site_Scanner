"""
Run this in Cloud Shell to check the real NDVI path end to end.

It does not start the web server — it calls Earth Engine directly, so if
something is wrong you find out whether it is Earth Engine or FastAPI without
guessing.

    cd ~/Site_Scanner          # wherever you cloned it
    source setup.sh            # installs deps, loads your key — must be `source`
    python3 scripts/check_real_ndvi.py

What success looks like: a table of months with NDVI values, mostly between
about 0.2 and 0.8, higher in summer than winter, and some winter months
showing "no data" because England is cloudy. Blank winters are correct
behaviour, not a failure.

Pass a year to test a shorter window, which is much faster while debugging:

    python3 scripts/check_real_ndvi.py 2024
"""

import pathlib
import sys
import time

# This file lives in scripts/, so Python puts scripts/ on the import path
# rather than the repo root, and `import app` fails. Same fix as
# ee_smoke_test.py — put the repo root first.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# A small field near Guildford. Small on purpose: reduceRegion over a county
# times out, and you want to know the pipeline works before you stress it.
FIELD = {
    "type": "Polygon",
    "coordinates": [[
        [-0.580, 51.235], [-0.560, 51.235],
        [-0.560, 51.245], [-0.580, 51.245], [-0.580, 51.235],
    ]],
}
AREA_HA = 155.0


def main() -> int:
    year = sys.argv[1] if len(sys.argv) > 1 else None
    steps = ([f"{year}-{m:02d}" for m in range(1, 13)] if year
             else [f"{y}-{m:02d}" for y in range(2023, 2026) for m in range(1, 13)])

    # A broad catch on purpose: a broken earthengine-api install fails deep in
    # a native dependency and prints a Rust panic before the Python error. A
    # clear sentence is worth more here than the stack trace.
    try:
        import ee  # noqa: F401
    except BaseException as e:
        print(f"✗ Could not import earthengine-api: {type(e).__name__}: {e}")
        print("  Fix with:  pip install -r requirements.txt")
        print("  In Cloud Shell make sure the venv is active first: source setup.sh")
        return 1

    print("Initialising Earth Engine…")
    try:
        from app import init_earth_engine
        init_earth_engine()
    except Exception as e:
        print(f"✗ Earth Engine would not initialise: {e}")
        print("  Check GOOGLE_APPLICATION_CREDENTIALS_JSON and EE_PROJECT are set")
        print("  (that is what `source setup.sh` does).")
        return 1
    print("✓ Earth Engine ready\n")

    try:
        import ee_series
    except BaseException as e:
        print(f"✗ Could not load ee_series: {type(e).__name__}: {e}")
        return 1

    print(f"Fetching {len(steps)} months of NDVI for a {AREA_HA:.0f} ha field…")
    print("(this is the slow part — that is the measurement, not a fault)\n")
    t0 = time.perf_counter()
    try:
        points = ee_series.ndvi_series(FIELD, steps, AREA_HA)
    except Exception as e:
        print(f"✗ The Earth Engine query failed: {e}")
        return 1
    elapsed = time.perf_counter() - t0

    print(f"{'month':<9} {'NDVI':>7}   {'valid':>6}")
    print("-" * 28)
    for p in points:
        if p["value"] is None:
            print(f"{p['t']:<9} {'no data':>7}   {p['valid_fraction'] * 100:>5.0f}%")
        else:
            print(f"{p['t']:<9} {p['value']:>7.3f}   {p['valid_fraction'] * 100:>5.0f}%")

    got = [p for p in points if p["value"] is not None]
    print(f"\n{len(got)} of {len(points)} months returned a value")
    print(f"took {elapsed:.1f}s — about {elapsed / max(1, len(steps)):.2f}s per month")

    if not got:
        print("\n✗ Every month came back empty. Usually one of:")
        print("  · the service account is not registered with Earth Engine")
        print("  · EE_PROJECT does not match the project the key belongs to")
        print("  · the area is outside Sentinel-2 coverage (it should not be, in England)")
        return 1

    values = [p["value"] for p in got]
    print(f"range {min(values):.3f} to {max(values):.3f}")
    if max(values) > 1.01 or min(values) < -1.01:
        print("⚠ NDVI outside -1..1 — the band maths is wrong somewhere")
        return 1

    print("\n✓ Real NDVI is working. Wire it up by starting the real backend:")
    print("    uvicorn app:app --reload --port 8000")
    print("  then draw a small shape in the app — the NDVI column gets a dot")
    print("  and every other factor still says demo data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
