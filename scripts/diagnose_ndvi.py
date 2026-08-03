"""
Work out why NDVI comes back flat.

check_real_ndvi.py proved Earth Engine is connected. It did not prove the
numbers are right, and they are not: a real English year swings from about
0.3 in winter to about 0.8 in summer, and the first run came back sitting
between 0.37 and 0.46 all year with June lower than October.

There are three candidate explanations and they need different fixes, so this
script separates them instead of guessing:

  A. Cloud masking is not working. Cloud has an NDVI near zero, so leaving it
     in drags every month toward the middle. Detected by computing each month
     twice, masked and unmasked, and comparing. If the two agree, the mask is
     doing nothing.

  B. The month filter is not working, so all twelve months reduce roughly the
     same imagery. Detected by printing how many images each month actually
     matched — a real English January and July differ a lot.

  C. Nothing is broken and the test field is simply mixed suburban land, whose
     NDVI genuinely is flat. Detected by running the identical code over
     intensive arable farmland, which has the strongest seasonal swing of any
     English land cover: bare soil in winter, closed canopy in summer. If that
     site is flat too, the code is wrong. If it swings, the code is fine and
     only the choice of test field was misleading.

    source ./setup.sh
    python3 scripts/diagnose_ndvi.py

Takes about a minute. It reads imagery only — it changes nothing.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# Same field check_real_ndvi.py uses, so the numbers are comparable.
GUILDFORD = {
    "type": "Polygon",
    "coordinates": [[
        [-0.580, 51.235], [-0.560, 51.235],
        [-0.560, 51.245], [-0.580, 51.245], [-0.580, 51.235],
    ]],
}

# Intensive arable in the Cambridgeshire fens. Chosen because it is the
# clearest seasonal signal available in England: near-bare soil in winter,
# full crop canopy by midsummer. If NDVI is flat here, the code is wrong.
FENS_ARABLE = {
    "type": "Polygon",
    "coordinates": [[
        [0.100, 52.550], [0.120, 52.550],
        [0.120, 52.570], [0.100, 52.570], [0.100, 52.550],
    ]],
}

MONTHS = ["2024-01", "2024-04", "2024-07", "2024-10"]


def probe(ee, geometry: dict, month: str) -> dict:
    """Everything we need to tell the three explanations apart, for one month."""
    import ee_series

    geom = ee.Geometry(geometry)
    start = ee.Date(month + "-01")
    end = start.advance(1, "month")

    raw = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
           .filterBounds(geom).filterDate(start, end))

    def ndvi_of(collection):
        return collection.map(
            lambda img: img.normalizedDifference(["B8", "B4"]).rename("NDVI"))

    # Exactly the masking the real code applies, so a difference here is a
    # difference in the real code.
    masked = ee_series._masked_ndvi_collection(geom, start, end)
    unmasked = ndvi_of(raw)

    reducer = (ee.Reducer.mean()
               .combine(ee.Reducer.count(), sharedInputs=True)
               .combine(ee.Reducer.percentile([10, 90]), sharedInputs=True))

    def stats(coll):
        blank = ee.Image.constant(0).rename("NDVI").updateMask(ee.Image.constant(0))
        img = ee.Image(ee.Algorithms.If(coll.size().gt(0), coll.median(), blank))
        return img.reduceRegion(reducer=reducer, geometry=geom,
                                scale=10, maxPixels=1e9, bestEffort=True)

    return ee.Dictionary({
        "images": raw.size(),
        "masked": stats(masked),
        "unmasked": stats(unmasked),
    }).getInfo()


def run_site(ee, name: str, geometry: dict) -> list:
    print(f"\n{name}")
    print(f"{'month':<9} {'imgs':>5} {'masked':>8} {'unmasked':>9} "
          f"{'p10':>7} {'p90':>7} {'pixels':>8}")
    print("-" * 60)

    rows = []
    for month in MONTHS:
        r = probe(ee, geometry, month)
        m, u = r["masked"], r["unmasked"]
        mean = m.get("NDVI_mean")
        rows.append({"month": month, "images": r["images"], "mean": mean,
                     "unmasked": u.get("NDVI_mean")})

        def fmt(v):
            return f"{v:.3f}" if isinstance(v, (int, float)) else "  —  "

        print(f"{month:<9} {r['images']:>5} {fmt(mean):>8} "
              f"{fmt(u.get('NDVI_mean')):>9} {fmt(m.get('NDVI_p10')):>7} "
              f"{fmt(m.get('NDVI_p90')):>7} {int(m.get('NDVI_count') or 0):>8}")
    return rows


def spread(rows) -> float:
    vals = [r["mean"] for r in rows if isinstance(r["mean"], (int, float))]
    return (max(vals) - min(vals)) if len(vals) > 1 else 0.0


def main() -> int:
    try:
        import ee
        from app import init_earth_engine
        init_earth_engine()
    except BaseException as e:
        print(f"✗ Earth Engine would not start: {type(e).__name__}: {e}")
        print("  Run `source ./setup.sh` first.")
        return 1
    print("✓ Earth Engine ready")

    guildford = run_site(ee, "Guildford test field (mixed suburban/farmland)", GUILDFORD)
    arable = run_site(ee, "Cambridgeshire fens (intensive arable)", FENS_ARABLE)

    print("\n" + "=" * 60)
    print("READING THE RESULT")
    print("=" * 60)

    g_spread, a_spread = spread(guildford), spread(arable)
    print(f"Guildford winter-to-summer spread: {g_spread:.3f}")
    print(f"Arable   winter-to-summer spread: {a_spread:.3f}")

    # Does masking change anything at all?
    diffs = [abs(r["mean"] - r["unmasked"])
             for r in guildford + arable
             if isinstance(r["mean"], (int, float))
             and isinstance(r["unmasked"], (int, float))]
    max_diff = max(diffs) if diffs else 0.0
    print(f"Largest masked vs unmasked difference: {max_diff:.3f}")

    print()
    if max_diff < 0.005:
        print("→ B/A: cloud masking is changing nothing. The masked and unmasked")
        print("  numbers agree, so updateMask is not taking effect and cloud is")
        print("  being averaged into every month. Fix the mask in ee_series.py.")
    elif a_spread < 0.15:
        print("→ A: even intensive arable is flat, which is not physically")
        print("  possible. The monthly composite is wrong — most likely the")
        print("  date filter, since flat means every month sees similar imagery.")
    elif g_spread < 0.15 <= a_spread:
        print("→ C: the code is correct. Arable swings as it should, so the")
        print("  pipeline works; the Guildford test field is simply mixed land")
        print("  whose NDVI really is flat. Change the test field, not the code.")
    else:
        print("→ Both sites swing. NDVI is behaving; re-read the first table.")

    print("\nAlso worth checking above: image counts should vary month to month.")
    print("If January and July matched the same number of images, the date")
    print("filter is the problem regardless of what the spreads say.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
