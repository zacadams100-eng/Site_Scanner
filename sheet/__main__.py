"""
Command line — the way to fulfil an order today.

    python -m sheet make red-line.geojson --title "Land at Home Farm, Dorking" --ref ORD-001
    python -m sheet make client.kml --title "..." --out jobs/ORD-002
    python -m sheet layers

The red line can be GeoJSON, KML, a GeoPackage or a zipped shapefile.
Set OS_API_KEY for an OS basemap (free OS Data Hub key; open zoom levels only).
"""

import argparse
import os
import sys
from pathlib import Path

from .fetch import NOT_ASSESSED, Fetcher, FixtureFetcher
from .geometry import site_from_file
from .layers import GROUPS, LAYERS
from .make import make_sheet


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m sheet")
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("make", help="make a desk-study sheet for a red line")
    m.add_argument("red_line", type=Path)
    m.add_argument("--title", required=True)
    m.add_argument("--ref", required=True, help="order reference, printed on every page")
    m.add_argument("--out", type=Path, default=Path("jobs"))
    m.add_argument("--context", type=float, default=500,
                   help="metres of context around the red line on the map (default 500: sites of 2–50 ha print at 1:10,000)")
    m.add_argument("--fixtures", type=Path, help="TEST ONLY: read layers from this folder")

    sub.add_parser("layers", help="list the 30 layers")

    a = p.parse_args(argv)
    if a.cmd == "layers":
        for g in GROUPS:
            print(f"\n{g}")
            for l in LAYERS:
                if l.group == g:
                    r = "red line" if l.search_m == 0 else f"{l.search_m:,} m"
                    print(f"  {l.id:<20} {l.name:<40} {r:>9}  {l.publisher}")
        return 0

    site = site_from_file(a.red_line)
    fetcher = FixtureFetcher(a.fixtures) if a.fixtures else Fetcher(contact=os.environ.get("CONTOUR_CONTACT", ""))
    def progress(r, secs):
        # One write per line: layers finish on several threads at once.
        sys.stdout.write(f"  {r.status:<13} {secs:5.1f}s  {r.layer.name}\n")
        sys.stdout.flush()

    rec = make_sheet(site, a.out, a.title, a.ref, fetcher, a.context, on_done=progress)
    c = rec["counts"]
    print(f"{rec['title']} · {rec['area_ha']} ha · 1:{rec['scale']:,}")
    print(f"present {c['present']} · none found {c['none_found']} · not assessed {c['not_assessed']}")
    for f in rec["findings"]:
        if f["status"] == NOT_ASSESSED:
            print(f"  NOT ASSESSED  {f['name']}: {f['error']}")
    for k, v in rec["files"].items():
        print(f"  {k:<5} {a.out / v}")
    if rec["test_data"]:
        print("  (test data — watermarked, not for clients)")
    # Exit 3 when anything was not assessed: check before sending to a client.
    return 3 if c["not_assessed"] else 0


if __name__ == "__main__":
    sys.exit(main())
