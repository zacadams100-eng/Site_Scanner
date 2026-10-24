"""
Print what each publisher actually sends: field names, record counts, and
one example record. Run where the publishers are reachable (CI, Cloud Shell):

    python scripts/inspect_layers.py              # every layer
    python scripts/inspect_layers.py woodland     # just these ids

Field names in sheet/layers.py were first guessed and twice came out wrong.
This is how to get them right instead: read them off the live service.
It also searches ArcGIS Online for the Forestry Commission's current
National Forest Inventory service, which is published under a new name
each year.
"""

import sys

import requests

sys.path.insert(0, ".")
from sheet.layers import LAYERS, PLANNING_ENTITIES  # noqa: E402

S = requests.Session()
S.headers["User-Agent"] = "Contour desk-study sheet (layer inspection)"


def show(props: dict) -> str:
    return ", ".join(f"{k}={str(v)[:40]!r}" for k, v in props.items())


def arcgis(l):
    meta = S.get(l.url, params={"f": "json"}, timeout=60).json()
    if "error" in meta:
        print(f"  ERROR {meta['error']}")
        return
    count = S.get(f"{l.url}/query", params={"where": "1=1", "returnCountOnly": "true", "f": "json"},
                  timeout=60).json().get("count")
    print(f"  name={meta.get('name')!r} geometry={meta.get('geometryType')} records={count}")
    print(f"  fields: {[f['name'] for f in meta.get('fields', [])]}")
    ex = S.get(f"{l.url}/query", params={"where": "1=1", "outFields": "*", "returnGeometry": "false",
                                          "resultRecordCount": 1, "f": "json"}, timeout=60).json()
    for f in ex.get("features", [])[:1]:
        print(f"  example: {show(f.get('attributes', {}))}")
    print(f"  label_fields now: {l.label_fields}")


def planning(l):
    # Without geometry: a whole National Landscape outline timed out at 40 s.
    r = S.get(PLANNING_ENTITIES, params={"dataset": l.dataset, "limit": 1, "exclude_field": "geometry,point"},
              timeout=60).json()
    ents = r.get("entities", [])
    print(f"  records: {r.get('count', '?')}{'  — EMPTY DATASET' if not ents else ''}")
    for e in ents[:1]:
        print(f"  example: {show(e)}")
    print(f"  label_fields now: {l.label_fields}")


def find_nfi():
    print("\n== ArcGIS Online: National Forest Inventory services, newest first")
    r = S.get("https://www.arcgis.com/sharing/rest/search", timeout=60, params={
        "q": 'title:"National Forest Inventory" AND type:"Feature Service"',
        "sortField": "modified", "sortOrder": "desc", "num": 15, "f": "json"}).json()
    for it in r.get("results", []):
        print(f"  {it.get('title')!r} owner={it.get('owner')} url={it.get('url')}")


if __name__ == "__main__":
    want = set(sys.argv[1:])
    for l in LAYERS:
        if want and l.id not in want:
            continue
        print(f"\n== {l.id} ({l.source}) {l.url or l.dataset}")
        try:
            arcgis(l) if l.source == "arcgis" else planning(l)
        except Exception as e:
            print(f"  FAILED {type(e).__name__}: {e}")
    if not want or "woodland" in want:
        find_nfi()
