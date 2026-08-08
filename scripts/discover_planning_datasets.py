#!/usr/bin/env python3
"""
Find out which planning.data.gov.uk datasets actually exist, instead of
guessing at them.

`open_data.py` already reads thirteen datasets from the Planning Data Platform,
and the platform publishes many more. Several map straight onto factors the
catalogue still generates — but which ones, and under what names, is a question
about a live service, and this repository has a standing rule against answering
those from memory:

    "Guessing at them would have produced five specs that fail on every run and
     five factors that promise data they cannot deliver."   — BLOCKERS.md §3

So nothing below is registered as real. This script is the step in between: it
takes a list of candidates, asks the platform which are genuine, runs a real
query for each survivor, and prints a block ready to paste into
`PLANNING_DATASETS`. Guessing becomes measuring, and it costs one command.

    python3 scripts/discover_planning_datasets.py
    python3 scripts/discover_planning_datasets.py --attributes flood-risk-zone
    python3 scripts/discover_planning_datasets.py --lat 51.24 --lon -0.57

It needs ordinary internet. The sandbox this was written in cannot reach the
platform (BLOCKERS.md §1), which is exactly why the candidates are candidates.

## Check the flood zones first

`flood_zone2_pct` and `flood_zone3_pct` shipped filtering on an attribute named
`flood-risk-type`, taken from the published schema and never seen in a live
response. If that name is wrong the factors raise and fall back to labelled
demo data — deliberately, rather than reporting 0% flood risk on a floodplain.

    python3 scripts/discover_planning_datasets.py --attributes flood-risk-zone

prints the attribute names the platform really returns. If `flood-risk-type` is
not among them, fix `PLANNING_DATASETS` in `open_data.py` and this becomes two
verified factors.
"""

import argparse
import json
import sys
from typing import Any, Dict, List, NamedTuple, Optional

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

import catalog  # noqa: E402
import open_data  # noqa: E402

BASE = "https://www.planning.data.gov.uk"
TIMEOUT = 30

# A default test area with a good chance of intersecting several designations:
# the Surrey Hills, which carry an AONB, green belt and a conservation area.
DEFAULT_LAT, DEFAULT_LON = 51.235, -0.57


class Candidate(NamedTuple):
    """A catalogue factor and the dataset that might supply it.

    `confidence` is honest about where the name came from:

      `documented` — seen in the platform's own dataset list or documentation.
      `likely`     — a standard national dataset that the platform is the
                     obvious home for, named by the usual convention.
      `guess`      — plausible and unconfirmed. Most of these will be wrong,
                     and that is the point of running this.
    """
    factor: str
    dataset: str
    mode: str
    confidence: str
    note: str = ""
    field: Optional[str] = None
    values: tuple = ()


CANDIDATES: List[Candidate] = [
    # --- already shipped, listed so the run re-confirms them ---------------
    Candidate("flood_zone3_pct", "flood-risk-zone", "pct", "likely",
              "SHIPPED — confirm the attribute name",
              field="flood-risk-type", values=("zone 3",)),

    # --- designations the catalogue still generates -------------------------
    Candidate("sac_spa_pct", "special-area-of-conservation", "pct", "likely",
              "one half of the factor; SPA is a second dataset, and the "
              "factor wants both — needs multi-dataset support before it can "
              "be registered"),
    Candidate("sac_spa_pct", "special-protection-area", "pct", "likely",
              "the other half"),
    Candidate("priority_habitat_pct", "priority-habitat", "pct", "guess",
              "Natural England publishes the Priority Habitat Inventory; "
              "whether the platform carries it is unknown"),
    Candidate("greenspace_access", "open-space", "pct", "guess",
              "the factor wants greenspace within 300 m, which is a distance "
              "query rather than a coverage one — a match here still needs "
              "different arithmetic"),

    # --- listed buildings by grade, using the filter flood risk added -------
    Candidate("listed_grade1_count", "listed-building", "density", "likely",
              "grade is an attribute; the factor wants Grade I and II* only",
              field="listed-building-grade", values=("i", "ii*")),

    # --- ground risk --------------------------------------------------------
    Candidate("historic_landfill_pct", "historic-landfill", "pct", "guess",
              "Environment Agency publishes this; platform coverage unknown"),
    Candidate("contamination_flag", "contaminated-land", "pct", "guess",
              "statutory registers are held by district councils and are "
              "rarely national — expect this to fail"),

    # --- planning policy ----------------------------------------------------
    Candidate("local_plan_allocation", "development-plan-document", "density",
              "guess",
              "the factor wants an allocation class, not a count — a match "
              "changes what the factor can honestly report"),
]


def _get(path: str, params: Optional[dict] = None) -> Any:
    r = requests.get(f"{BASE}{path}", params=params, timeout=TIMEOUT,
                     headers={"User-Agent": "SiteScanner/1.0 (discovery)"})
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def dataset_index() -> Optional[List[str]]:
    """Every dataset the platform publishes, if it will tell us in one call."""
    for path in ("/dataset.json", "/api/dataset.json"):
        try:
            data = _get(path)
        except requests.RequestException:
            continue
        if isinstance(data, dict) and "datasets" in data:
            return sorted(d.get("dataset") or d.get("name") for d in data["datasets"])
        if isinstance(data, list):
            return sorted(d.get("dataset") or d.get("name") for d in data)
    return None


def probe(dataset: str, lat: float, lon: float) -> Dict[str, Any]:
    """Does this dataset exist, and does it answer a real spatial query?

    Two questions, because they fail differently: a dataset that does not exist
    is a wrong name to delete, and a dataset that exists but returns nothing
    here may be perfectly correct — there is no coal mining in Surrey.
    """
    out: Dict[str, Any] = {"dataset": dataset}
    try:
        meta = _get(f"/dataset/{dataset}.json")
        out["exists"] = meta is not None
    except requests.RequestException as e:
        out["exists"] = None
        out["error"] = e.__class__.__name__
        return out

    if not out["exists"]:
        return out

    d = 0.005
    ring = [(lon - d, lat - d), (lon + d, lat - d), (lon + d, lat + d),
            (lon - d, lat + d), (lon - d, lat - d)]
    wkt = "POLYGON((" + ", ".join(f"{x:.6f} {y:.6f}" for x, y in ring) + "))"
    try:
        data = _get("/entity.geojson",
                    {"dataset": dataset, "geometry": wkt,
                     "geometry_relation": "intersects", "limit": 10})
    except requests.RequestException as e:
        out["error"] = e.__class__.__name__
        return out

    features = (data or {}).get("features", [])
    out["features_here"] = len(features)
    if features:
        out["attributes"] = sorted(attribute_names(features[0]))
    return out


def attribute_names(feature: dict) -> List[str]:
    """Every attribute key on a feature, at both levels the platform uses."""
    names = []
    for d in open_data._feature_fields(feature):
        names.extend(k for k in d if k != "json")
    return names


def show_attributes(dataset: str, lat: float, lon: float) -> int:
    """Print the real attribute names, which is what a filter has to match.

    This is the mode that resolves the flood-zone question.
    """
    result = probe(dataset, lat, lon)
    if not result.get("exists"):
        print(f"  {dataset}: no such dataset on the platform")
        return 1
    if not result.get("features_here"):
        print(f"  {dataset}: exists, but nothing intersects the test area — "
              f"try --lat/--lon somewhere it applies")
        return 1
    print(f"  {dataset}: {result['features_here']} entities here")
    print("  attributes actually returned:")
    for name in result["attributes"]:
        print(f"    {name}")
    for factor, spec in open_data.PLANNING_DATASETS.items():
        if spec.dataset == dataset and spec.field:
            ok = spec.field in result["attributes"]
            mark = "OK  " if ok else "WRONG"
            print(f"\n  {mark} {factor} filters on {spec.field!r} — "
                  f"{'present' if ok else 'NOT PRESENT, fix open_data.py'}")
            if not ok:
                return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lat", type=float, default=DEFAULT_LAT)
    ap.add_argument("--lon", type=float, default=DEFAULT_LON)
    ap.add_argument("--attributes", metavar="DATASET",
                    help="print the attribute names one dataset really returns")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.attributes:
        return show_attributes(args.attributes, args.lat, args.lon)

    index = dataset_index()
    if index:
        print(f"The platform publishes {len(index)} datasets.")
        known = {s.dataset for s in open_data.PLANNING_DATASETS.values()}
        unused = [d for d in index if d and d not in known]
        print(f"{len(known)} are already read here; {len(unused)} are not.\n")
    else:
        print("No dataset index available; probing each candidate directly.\n")

    results = []
    print(f"Probing {len(CANDIDATES)} candidates against "
          f"{args.lat:.3f}, {args.lon:.3f}\n")
    for c in CANDIDATES:
        r = probe(c.dataset, args.lat, args.lon)
        r["factor"] = c.factor
        r["confidence"] = c.confidence
        r["note"] = c.note
        results.append(r)

        if r.get("exists") is None:
            state = f"unreachable ({r.get('error')})"
        elif not r["exists"]:
            state = "DOES NOT EXIST"
        elif r.get("error"):
            state = f"exists, query failed ({r['error']})"
        elif r.get("features_here"):
            state = f"exists, {r['features_here']} entities here"
        else:
            state = "exists, none in the test area"
        print(f"  [{c.confidence:>10}] {c.dataset:34} {state}")
        if c.field and r.get("attributes"):
            have = c.field in r["attributes"]
            print(f"               filter {c.field!r}: "
                  f"{'present' if have else 'NOT PRESENT — ' + ', '.join(r['attributes'][:6])}")
        if c.note:
            print(f"               {c.note}")

    real = [r for r in results if r.get("exists")]
    unreachable = [r for r in results if r.get("exists") is None]

    if len(unreachable) == len(results):
        # "0 of 9 exist" would be a finding. "we could not ask" is not the
        # same statement, and reporting the first when the second is true is
        # how a network failure turns into a decision to delete nine datasets.
        print(f"\nNothing was checked: all {len(results)} probes failed to "
              f"reach {BASE}.")
        print("This machine cannot see the platform — see BLOCKERS.md §1. "
              "Run it somewhere with ordinary internet.")
        return 2

    print(f"\n{len(real)} of {len(CANDIDATES) - len(unreachable)} reachable "
          f"candidates exist" +
          (f"; {len(unreachable)} could not be checked." if unreachable else "."))

    if args.json:
        print(json.dumps(results, indent=2))
        return 0

    usable = [r for r in real if r.get("features_here")]
    if usable:
        print("\nReady to add to PLANNING_DATASETS in open_data.py — but check "
              "each factor's units first: a dataset existing does not mean it "
              "answers the question the factor asks.\n")
        for r in usable:
            c = next(c for c in CANDIDATES
                     if c.dataset == r["dataset"] and c.factor == r["factor"])
            if c.note.startswith("SHIPPED"):
                continue
            filt = (f", {c.field!r}, {c.values!r}" if c.field else "")
            print(f'    "{c.factor}": PlanningSpec("{c.dataset}", '
                  f'"{c.mode}"{filt}),')

    missing = [r for r in results if r.get("exists") is False]
    if missing:
        print("\nDelete these candidates — the datasets do not exist:")
        for r in missing:
            print(f"    {r['factor']:28} {r['dataset']}")

    print("\nNothing here has been registered. Adding a factor to "
          "PLANNING_DATASETS is a deliberate act, and it still needs "
          "scripts/check_open_data.py to move it from written to verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
