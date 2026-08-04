#!/usr/bin/env python3
"""
Build the bundled basemap for the map canvas.

Why bundle one at all: the app's only cartography was an OpenStreetMap raster
underlay, which meant that with no tiles — a blocked host, an offline Cloud
Shell, OSM's usage policy applied to production traffic — the map was an empty
rectangle with a drawn shape floating in it. You could not tell Devon from
Durham. A site-analysis tool whose map cannot answer "where am I" is not
finished.

So the coastline, the towns and cities, the motorways, the railways and the
rivers travel with the application as one small file. Natural Earth is public
domain (CC0), it is generalised to roughly 1:10 million, and it is exactly
right for the zoom levels at which someone is *finding* a site. Street-level
detail is still the raster's job once they are down at a field.

Run:
    python3 scripts/build_basemap.py            # fetches, clips, writes
    python3 scripts/build_basemap.py --src DIR  # reuse already-downloaded files

Output: web/public/basemap/england.json — one JSON, several FeatureCollections.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import sys
import urllib.request

NE_BASE = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
           "master/geojson")

LAYERS = [
    "ne_10m_admin_0_countries_lakes",
    "ne_10m_populated_places_simple",
    "ne_10m_roads",
    "ne_10m_railroads",
    "ne_10m_urban_areas",
    "ne_10m_rivers_lake_centerlines",
    "ne_10m_lakes",
]

# Wider than England on purpose. A map that stops at the border reads as a
# rendering failure; Wales, Scotland, Ireland and the near-continent coast are
# what tell a user at a glance which way up the country is.
BBOX = (-11.0, 48.6, 4.2, 59.6)     # west, south, east, north

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "public" / "basemap" / "england.json"


# ---------------------------------------------------------------------------
# Geometry helpers. Deliberately dependency-free: this runs in CI and in a
# Cloud Shell that has fastapi and not much else.
# ---------------------------------------------------------------------------
def bbox_of(geom) -> tuple:
    xs, ys = [], []

    def walk(c):
        if isinstance(c[0], (int, float)):
            xs.append(c[0])
            ys.append(c[1])
        else:
            for k in c:
                walk(k)

    walk(geom["coordinates"])
    return min(xs), min(ys), max(xs), max(ys)


def intersects(b: tuple) -> bool:
    w, s, e, n = b
    return not (e < BBOX[0] or w > BBOX[2] or n < BBOX[1] or s > BBOX[3])


def simplify(points, tol):
    """Douglas-Peucker. Tolerance is in degrees, which is fine at this scale
    and one less thing to get wrong than reprojecting first."""
    if len(points) < 3:
        return points

    def dist(p, a, b):
        (px, py), (ax, ay), (bx, by) = p, a, b
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return math.hypot(px - ax, py - ay)
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        i, j = stack.pop()
        worst, idx = 0.0, -1
        for k in range(i + 1, j):
            d = dist(points[k], points[i], points[j])
            if d > worst:
                worst, idx = d, k
        if idx >= 0 and worst > tol:
            keep[idx] = True
            stack.append((i, idx))
            stack.append((idx, j))
    return [p for p, k in zip(points, keep) if k]


def clip_ring(ring, box):
    """Sutherland-Hodgman against our bounding box.

    Without this, one feature for France carries the whole of France — its
    bounding box touches ours, so it survives the filter and then contributes
    a megabyte of Mediterranean coastline nobody will ever see. Clipping is
    the difference between a 1.7 MB basemap and a 600 KB one.
    """
    w, s_, e, n = box
    edges = (("x>=", w), ("x<=", e), ("y>=", s_), ("y<=", n))

    def inside(pt, op, v):
        return pt[0] >= v if op == "x>=" else \
               pt[0] <= v if op == "x<=" else \
               pt[1] >= v if op == "y>=" else pt[1] <= v

    def cut(a, b, op, v):
        if op in ("x>=", "x<="):
            t = (v - a[0]) / (b[0] - a[0]) if b[0] != a[0] else 0.0
            return [v, a[1] + t * (b[1] - a[1])]
        t = (v - a[1]) / (b[1] - a[1]) if b[1] != a[1] else 0.0
        return [a[0] + t * (b[0] - a[0]), v]

    out = ring
    for op, v in edges:
        if not out:
            return []
        buf, prev = [], out[-1]
        for cur in out:
            ci, pi = inside(cur, op, v), inside(prev, op, v)
            if ci:
                if not pi:
                    buf.append(cut(prev, cur, op, v))
                buf.append(cur)
            elif pi:
                buf.append(cut(prev, cur, op, v))
            prev = cur
        out = buf
    return out


def clip_line(line, box):
    """Split a line at the box edge, keeping the pieces inside it."""
    w, s_, e, n = box
    inside = lambda p: w <= p[0] <= e and s_ <= p[1] <= n   # noqa: E731
    parts, cur = [], []
    for pt in line:
        if inside(pt):
            cur.append(pt)
        elif cur:
            parts.append(cur)
            cur = []
    if cur:
        parts.append(cur)
    return [p for p in parts if len(p) > 1]


def clip_geometry(geom, box):
    t = geom["type"]
    if t == "Polygon":
        rings = [clip_ring(r, box) for r in geom["coordinates"]]
        rings = [r for r in rings if len(r) > 3]
        return {"type": t, "coordinates": rings} if rings else None
    if t == "MultiPolygon":
        polys = []
        for poly in geom["coordinates"]:
            rings = [clip_ring(r, box) for r in poly]
            rings = [r for r in rings if len(r) > 3]
            if rings:
                polys.append(rings)
        return {"type": t, "coordinates": polys} if polys else None
    if t == "LineString":
        parts = clip_line(geom["coordinates"], box)
        if not parts:
            return None
        return ({"type": "LineString", "coordinates": parts[0]} if len(parts) == 1
                else {"type": "MultiLineString", "coordinates": parts})
    if t == "MultiLineString":
        parts = []
        for line in geom["coordinates"]:
            parts.extend(clip_line(line, box))
        return {"type": "MultiLineString", "coordinates": parts} if parts else None
    return geom


def thin(geom, tol):
    """Simplify every ring or line in a geometry, dropping anything that
    collapses to nothing."""
    t = geom["type"]
    if t == "LineString":
        return {"type": t, "coordinates": simplify(geom["coordinates"], tol)}
    if t == "MultiLineString":
        parts = [simplify(l, tol) for l in geom["coordinates"]]
        parts = [p for p in parts if len(p) > 1]
        return {"type": t, "coordinates": parts} if parts else None
    if t == "Polygon":
        rings = [simplify(r, tol) for r in geom["coordinates"]]
        rings = [r for r in rings if len(r) > 3]
        return {"type": t, "coordinates": rings} if rings else None
    if t == "MultiPolygon":
        polys = []
        for poly in geom["coordinates"]:
            rings = [simplify(r, tol) for r in poly]
            rings = [r for r in rings if len(r) > 3]
            if rings:
                polys.append(rings)
        return {"type": t, "coordinates": polys} if polys else None
    return geom


def round_coords(geom, places=4):
    """Five decimals is a metre; four is ten metres, which is finer than this
    data is accurate and halves the file."""
    def walk(c):
        if isinstance(c[0], (int, float)):
            return [round(c[0], places), round(c[1], places)]
        return [walk(k) for k in c]

    geom["coordinates"] = walk(geom["coordinates"])
    return geom


def load(src: pathlib.Path, name: str):
    path = src / f"{name}.geojson"
    if not path.exists():
        url = f"{NE_BASE}/{name}.geojson"
        print(f"  fetching {name} …", file=sys.stderr)
        src.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, path)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def clipped(fc, tol, keep=None, props=(), min_points=0):
    """Features whose bounding box touches ours, simplified, with only the
    properties we actually draw with."""
    out = []
    for f in fc["features"]:
        g = f.get("geometry")
        if not g or not g.get("coordinates"):
            continue
        try:
            if not intersects(bbox_of(g)):
                continue
        except (IndexError, ValueError):
            continue
        if keep and not keep(f["properties"]):
            continue
        if g["type"] != "Point":
            g = clip_geometry(g, BBOX)
            if g is None:
                continue
        g = thin(g, tol) if tol else g
        if g is None:
            continue
        p = {k: f["properties"].get(k) for k in props}
        out.append({"type": "Feature", "properties": p,
                    "geometry": round_coords(g)})
    return {"type": "FeatureCollection", "features": out}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.environ.get("NE_SRC", "/tmp/naturalearth"))
    args = ap.parse_args()
    src = pathlib.Path(args.src)

    print("Building the bundled basemap …", file=sys.stderr)
    data = {}

    countries = load(src, "ne_10m_admin_0_countries_lakes")
    data["land"] = clipped(countries, 0.004, props=("NAME", "ADM0_A3"))

    urban = load(src, "ne_10m_urban_areas")
    data["urban"] = clipped(urban, 0.004, props=())

    lakes = load(src, "ne_10m_lakes")
    data["lakes"] = clipped(lakes, 0.003, props=("name",))

    rivers = load(src, "ne_10m_rivers_lake_centerlines")
    data["rivers"] = clipped(
        rivers, 0.003,
        keep=lambda p: (p.get("scalerank") or 12) <= 9,
        props=("name",))

    roads = load(src, "ne_10m_roads")
    data["roads"] = clipped(
        roads, 0.002,
        keep=lambda p: p.get("type") in ("Major Highway", "Secondary Highway",
                                         "Road", "Beltway"),
        props=("type", "label", "name"))

    rail = load(src, "ne_10m_railroads")
    data["rail"] = clipped(rail, 0.003, props=())

    places = load(src, "ne_10m_populated_places_simple")
    data["places"] = clipped(
        places, 0,
        keep=lambda p: p.get("adm0name") in (
            "United Kingdom", "Ireland", "Isle of Man"),
        props=("name", "adm0name", "adm1name", "pop_max", "scalerank",
               "featurecla"))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"attribution": "Made with Natural Earth (public domain)",
                   "bbox": list(BBOX), **data}, fh, separators=(",", ":"))

    size = OUT.stat().st_size
    for k, v in data.items():
        print(f"  {k:8} {len(v['features']):5} features", file=sys.stderr)
    print(f"  wrote {OUT.relative_to(ROOT)} ({size/1024:.0f} KB)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
