"""
Check Contour's answers against a second source. Run where the publishers
are reachable (CI, Cloud Shell):

    python scripts/crosscheck.py out/      # folder of sheet records (*.json)

1. Green Belt at single points. planning.data's green-belt dataset is a
   national compilation from councils' yearly returns, not each council's
   own plan, so it may lag a plan that removed land from the Green Belt.
   Points in the middle of Guildford's 2019 allocations should NOT be Green
   Belt if the data is current. Two controls: Newlands Corner (should be)
   and Guildford High Street (should not).

2. Every "none found" designation on the sheets, asked again of the
   original publishers' own services (Natural England, Historic England),
   which are what MAGIC displays. A hit there means Contour said "clear"
   wrongly.
"""

import glob
import json
import sys

import requests
from shapely.geometry import shape

sys.path.insert(0, ".")
from sheet.geometry import search_area, to_bng, to_wgs  # noqa: E402
from sheet.layers import LAYER_BY_ID, PLANNING_ENTITIES  # noqa: E402

S = requests.Session()
S.headers["User-Agent"] = "Contour desk-study sheet (cross-check)"
T = 60

GB_POINTS = [
    ("Wisley airfield, west runway", 51.3060, -0.4600),
    ("Wisley airfield, mid runway", 51.3068, -0.4500),
    ("Wisley airfield, east runway", 51.3075, -0.4400),
    ("Gosden Hill Farm, centre", 51.2625, -0.5300),
    ("Gosden Hill Farm, south", 51.2600, -0.5330),
    ("Blackwell Farm, centre", 51.2330, -0.6200),
    ("Garlick's Arch, centre", 51.2955, -0.5010),
    ("CONTROL Newlands Corner (should be Green Belt)", 51.2330, -0.5060),
    ("CONTROL Guildford High Street (should not be)", 51.2365, -0.5720),
]

# Second sources: the publishers' own ArcGIS services, found by title.
SECOND = {
    "sssi": ("Sites of Special Scientific Interest (England)", "JJzESW51TqeY9uat"),
    "sac": ("Special Areas of Conservation (England)", "JJzESW51TqeY9uat"),
    "spa": ("Special Protection Areas (England)", "JJzESW51TqeY9uat"),
    "ramsar": ("Ramsar (England)", "JJzESW51TqeY9uat"),
    "nnr": ("National Nature Reserves (England)", "JJzESW51TqeY9uat"),
    "lnr": ("Local Nature Reserves (England)", "JJzESW51TqeY9uat"),
    "ancient_woodland": ("Ancient Woodland (England)", "JJzESW51TqeY9uat"),
    # Historic England's own services only. A loose match once picked Historic
    # Environment Scotland and a Suffolk council, which can only ever say 0.
    "listed_building": ("Listed Building", "historicengland"),
    "scheduled_monument": ("Scheduled Monument", "historicengland"),
    "park_garden": ("Park and Garden", "historicengland"),
}


def green_belt():
    out = ["## 1. Green Belt at single points (planning.data green-belt)", "",
           "| Point | Green Belt? | Record (organisation, reference, entry date, start date) |", "|---|---|---|"]
    for name, lat, lon in GB_POINTS:
        try:
            r = S.get(PLANNING_ENTITIES, timeout=T, params={
                "dataset": "green-belt", "geometry": f"POINT({lon} {lat})", "geometry_relation": "intersects",
                "exclude_field": "geometry,point", "limit": 5}).json()
            ents = r.get("entities", [])
            recs = "; ".join(f"org {e.get('organisation-entity')}, ref {e.get('reference')}, "
                             f"entered {e.get('entry-date')}, start {e.get('start-date') or '–'}, "
                             f"name {e.get('name') or '–'}" for e in ents)
            out.append(f"| {name} | {'YES' if ents else 'no'} | {recs or '–'} |")
        except Exception as e:
            out.append(f"| {name} | FAILED | {type(e).__name__}: {e} |")
    return out


def find_service(title, prefer):
    r = S.get("https://www.arcgis.com/sharing/rest/search", timeout=T, params={
        "q": f'title:"{title}" AND type:"Feature Service"', "num": 30, "f": "json"}).json()
    hits = [i for i in r.get("results", []) if i.get("url")]
    for i in hits:
        where = (i["url"] + " " + i.get("owner", "")).lower().replace("_", "").replace(" ", "")
        if prefer.lower() in where and "scotland" not in where and "wales" not in where:
            return i["url"].rstrip("/") + "/0", i.get("owner")
    # No exact publisher: say so, and show what was offered, rather than
    # comparing against someone else's data.
    offered = ", ".join(f"{i.get('title')} ({i.get('owner')})" for i in hits[:5])
    return None, f"none from the publisher; offered: {offered or 'nothing'}"


def count_in(url, area_bng):
    g = to_wgs(area_bng.simplify(10))
    polys = [g] if g.geom_type == "Polygon" else list(g.geoms)
    rings = [list(map(list, p.exterior.coords)) for p in polys]
    r = S.post(f"{url}/query", timeout=T, data={
        "where": "1=1", "geometry": json.dumps({"rings": rings, "spatialReference": {"wkid": 4326}}),
        "geometryType": "esriGeometryPolygon", "inSR": 4326, "spatialRel": "esriSpatialRelIntersects",
        "returnCountOnly": "true", "f": "json"}).json()
    if "error" in r:
        raise RuntimeError(r["error"].get("message"))
    return int(r.get("count", 0))


def none_found(folder):
    out = ["", "## 2. Every \"none found\" asked again of the original publisher", "",
           "| Site | Layer | Searched | Second source says | Verdict |", "|---|---|---|---|---|"]
    services = {}
    for lid, (title, prefer) in SECOND.items():
        try:
            services[lid] = find_service(title, prefer)
        except Exception as e:
            services[lid] = (None, f"search failed: {e}")
    out_src = ["", "Second sources used:", ""] + [
        f"- {lid}: {u or 'NOT FOUND'} (owner {o})" for lid, (u, o) in services.items()]
    wrong = checked = 0
    for p in sorted(glob.glob(f"{folder}/*/*.json")):
        rec = json.load(open(p))
        site = to_bng(shape(rec["red_line_wgs84"]))
        for f in rec["findings"]:
            if f["status"] != "none_found" or f["layer"] not in SECOND:
                continue
            url = services[f["layer"]][0]
            if not url:
                out.append(f"| {rec['title']} | {f['name']} | {f['search_m']} m | no second source | – |")
                continue
            try:
                n = count_in(url, search_area(site, LAYER_BY_ID[f["layer"]].search_m))
                checked += 1
                verdict = "agrees" if n == 0 else f"**WRONG: {n} found**"
                wrong += n > 0
                out.append(f"| {rec['title']} | {f['name']} | {f['search_m']} m | {n} | {verdict} |")
            except Exception as e:
                out.append(f"| {rec['title']} | {f['name']} | {f['search_m']} m | FAILED {e} | – |")
    out.insert(3, f"Checked {checked} \"none found\" answers; {wrong} disagree with the second source.\n")
    return out + out_src


if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else "out"
    lines = ["# Cross-check", ""] + green_belt() + none_found(folder)
    text = "\n".join(lines) + "\n"
    print(text)
    open(f"{folder}/CROSSCHECK.md", "w").write(text)
