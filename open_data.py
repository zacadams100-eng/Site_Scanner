"""
Real numbers from public UK open data — no key, no quota, no satellite.

Everything in `ee_series.py` needs an Earth Engine service account. This module
needs nothing at all: five government sources publish under the Open Government
Licence over plain HTTPS, and between them they cover the half of the catalogue
Earth Engine cannot see — what the land is designated as, what happens on it,
what it sells for.

    Source                     What it gives us               Key needed
    ─────────────────────────  ─────────────────────────────  ──────────
    planning.data.gov.uk       designations and constraints   no
    landregistry.data.gov.uk   residential transactions       no
    data.police.uk             street-level crime, monthly    no
    api.postcodes.io           centroid → postcode → LA code  no
    epc.opendatacommunities    building energy performance    YES (free)
    ONS                        rents, earnings, affordability  no*

  * ONS publishes most of these as spreadsheets rather than through an API;
    see `ons_series` for what that means and what it does instead.

## The contract

Each function here returns exactly the point list `series.generate_series`
produces, so a factor becomes real without the frontend knowing:

    [{"t": "2024-07", "value": 12.4, "valid_fraction": 1.0,
      "interpolated": False}, ...]

A source that fails raises. `routes_catalog._series_for` catches that, falls
back to the generator, and records the failure in the response — so an outage
degrades to labelled demo data rather than to an empty report.

## Honesty about verification

**These integrations are written against each API's documented shape and are
covered by tests using recorded fixtures. They have not yet been run against
the live endpoints**, because the environment they were written in blocks
outbound HTTPS to everything except a short allowlist. `scripts/check_open_data.py`
runs them against the real services; until that has been run somewhere with
open egress, treat every factor here as implemented-but-unverified. The
catalogue reports that state rather than claiming more (see `SOURCE_STATUS`).

## Cost

These are per-request lookups, not a raster we hold. A 15-year monthly crime
series is 180 HTTP calls to data.police.uk; the price-paid series is one SPARQL
query. Everything is cached per AOI for the process lifetime, on top of the
per-factor cache in `routes_catalog`, and the slow ones say so in their
docstrings. This is exactly the pattern TECHNICAL_PLAN.md §3.4 argues should
eventually be pre-aggregated.
"""

from __future__ import annotations

import datetime as _dt
import os
import threading
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple

import requests

import cache as cache_mod

# One session, so connections are reused across the 180 calls a crime series
# makes. Requests' default is a new connection per call, which triples the time.
_SESSION = requests.Session()
_SESSION.headers["User-Agent"] = (
    "SiteScanner/1.0 (+https://github.com/zacadams100-eng/Site_Scanner)")

TIMEOUT = 20
_LOOKUP_CACHE = cache_mod.TTLCache(ttl=3600, max_entries=512)
_LOCK = threading.Lock()

# What each source is worth waiting for. A source slower than this is one that
# belongs in the pre-aggregated tier rather than on the interactive path.
SLOW_SOURCES = {"police"}


class OpenDataError(RuntimeError):
    """A source could not answer. Never swallowed here — the caller decides
    whether to fall back, and the response says that it did."""


def _get(url: str, params: Optional[dict] = None, auth=None) -> Any:
    key = cache_mod.cache_key("od", url, params or {})
    hit = _LOOKUP_CACHE.get(key)
    if hit is not None:
        return hit
    try:
        r = _SESSION.get(url, params=params, timeout=TIMEOUT, auth=auth)
    except requests.RequestException as e:
        raise OpenDataError(f"{url} unreachable: {e.__class__.__name__}") from e
    if r.status_code == 404:
        # A 404 from these APIs means "nothing here", which is a legitimate
        # answer (no crimes in the sea, no conservation area on a moor).
        _LOOKUP_CACHE.set(key, None)
        return None
    if not r.ok:
        raise OpenDataError(f"{url} returned {r.status_code}")
    try:
        data = r.json()
    except ValueError as e:
        raise OpenDataError(f"{url} did not return JSON") from e
    _LOOKUP_CACHE.set(key, data)
    return data


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def _ring(geometry: dict) -> List[List[float]]:
    if geometry["type"] == "Polygon":
        return geometry["coordinates"][0]
    return geometry["coordinates"][0][0]


def _wkt(geometry: dict) -> str:
    """WKT for the planning platform's geometry filter."""
    pts = ", ".join(f"{x:.6f} {y:.6f}" for x, y in _ring(geometry))
    return f"POLYGON(({pts}))"


def _police_poly(geometry: dict, max_points: int = 60) -> str:
    """data.police.uk takes `lat,lng:lat,lng:…` and rejects very long strings,
    so a traced field boundary has to be thinned before it is sent.

    **The thinned ring is re-closed explicitly.** `ring[::step]` only lands on
    the final vertex when the length divides evenly, so a 200-point freehand
    outline was sent as 67 points that did not return to the start — an open
    polyline where a polygon was meant. Whether the far end closes it for us is
    undocumented, and a boundary that depends on undocumented behaviour is a
    boundary that will move without warning.

    Rectangles and circles never hit this: they are under the threshold and no
    thinning happens. Only a hand-traced outline is long enough, which is why
    it survived every test and every run over the default test square.
    """
    ring = _ring(geometry)
    step = max(1, len(ring) // max_points)
    thinned = ring[::step]
    if thinned[0] != thinned[-1]:
        thinned = [*thinned, thinned[0]]
    return ":".join(f"{y:.5f},{x:.5f}" for x, y in thinned)


def _months(steps: List[str]) -> List[Tuple[int, int]]:
    return [(int(s[:4]), int(s[5:])) for s in steps]


def _point(t: str, value, valid: float = 1.0) -> Dict[str, Any]:
    return {"t": t, "value": value, "valid_fraction": valid, "interpolated": False}


def _gap(t: str) -> Dict[str, Any]:
    """No usable observation. Never a zero: "no data published for this month"
    and "no crimes happened" are different facts, and a chart that conflates
    them is worse than one with a hole in it."""
    return {"t": t, "value": None, "valid_fraction": 0.0, "interpolated": False}


def _static(steps: List[str], value) -> List[Dict[str, Any]]:
    """A static measurement held across the timeline, flagged as carried
    forward for every month after the first."""
    out = [_point(steps[0], value)] if steps else []
    for s in steps[1:]:
        p = _point(s, value)
        p["interpolated"] = True
        out.append(p)
    return out


# ---------------------------------------------------------------------------
# postcodes.io — the join between a drawn shape and every statistical geography
# ---------------------------------------------------------------------------
"""Search radii for the postcode lookup, in metres.

postcodes.io defaults to **100 m** and this function used to send no radius at
all, so any AOI whose centroid sat more than 100 m from a postcode raised "no
postcode near this area" — and since almost every non-spatial source is keyed
off this lookup, that failed roughly twenty factors at once.

The AOIs that fail are farms, development plots, solar sites and woodland:
open countryside, which is most of what this product is for. It was found on
the first run over the South Downs and could not have been found any other
way, because the sandbox these integrations were written in cannot reach
postcodes.io and the default test AOI is inside Guildford.

2,000 m is the API's maximum for a postcode search; beyond that the outcode
endpoint takes over.
"""
POSTCODE_RADII_M = (100, 500, 2000)


def locate(geometry: dict) -> Dict[str, Any]:
    """Nearest postcode to the AOI centroid, with its administrative codes.

    Almost every non-spatial source here is published by postcode district or
    by local authority, so this is the hinge: without it a polygon cannot be
    joined to a price index or an earnings figure.

    Widens its search rather than giving up, and reports how far it had to go.
    That distance is not bookkeeping — a site joined to a price index from a
    postcode 40 m away and one joined from 4 km away are different claims, and
    the second should be visible to whoever reads the number.
    """
    ring = _ring(geometry)
    lng = sum(p[0] for p in ring) / len(ring)
    lat = sum(p[1] for p in ring) / len(ring)
    params = {"lon": round(lng, 5), "lat": round(lat, 5), "limit": 1}

    for radius in POSTCODE_RADII_M:
        data = _get("https://api.postcodes.io/postcodes",
                    {**params, "radius": radius})
        result = (data or {}).get("result")
        if result:
            r = result[0]
            return {
                "postcode": r["postcode"],
                "district": r["postcode"].split()[0],
                "admin_district": r.get("admin_district"),
                "admin_district_code": (r.get("codes") or {}).get("admin_district"),
                "within_m": radius,
                "precision": "postcode",
                "lng": lng, "lat": lat,
            }

    # Nothing within 2 km. Fall back to the outward code, which is coarser but
    # is exactly what the Land Registry district query already uses — so the
    # price factors keep working on a moor where the postcode search does not.
    data = _get("https://api.postcodes.io/outcodes",
                {**params, "radius": 25000})
    result = (data or {}).get("result")
    if not result:
        raise OpenDataError(
            f"no postcode within {POSTCODE_RADII_M[-1]} m and no outcode "
            f"within 25 km of {lat:.4f}, {lng:.4f} — is this area offshore?")

    r = result[0]
    districts = r.get("admin_district") or []
    return {
        # There is no full postcode here, and inventing one would be worse
        # than saying so: the outward code is what we actually know.
        "postcode": r["outcode"],
        "district": r["outcode"],
        "admin_district": districts[0] if districts else None,
        "admin_district_code": (r.get("codes") or {}).get("admin_district"),
        "within_m": 25000,
        # Carried through so a caller can say the join is approximate. Nothing
        # in this file quietly upgrades a coarse answer to a precise one.
        "precision": "outcode",
        "lng": lng, "lat": lat,
    }


# ---------------------------------------------------------------------------
# planning.data.gov.uk — designations and constraints
# ---------------------------------------------------------------------------
# Each entry is a national dataset published by MHCLG on the planning data
# platform. `pct` factors report the share of the AOI covered; `density`
# factors report features per square kilometre.
class PlanningSpec(NamedTuple):
    """One catalogue factor, and how to get it from the Planning Data Platform.

    `field`/`values` are for the datasets that carry more than one thing. Flood
    risk is the only one so far: Zone 2 and Zone 3 share the `flood-risk-zone`
    dataset and are told apart by an attribute.
    """
    dataset: str
    mode: str
    field: Optional[str] = None
    values: Tuple[str, ...] = ()


PLANNING_DATASETS: Dict[str, PlanningSpec] = {
    "conservation_area_pct": PlanningSpec("conservation-area", "pct"),
    "article4_pct": PlanningSpec("article-4-direction-area", "pct"),
    "green_belt_pct": PlanningSpec("green-belt", "pct"),
    "national_park_pct": PlanningSpec("national-park", "pct"),
    "aonb_pct": PlanningSpec("area-of-outstanding-natural-beauty", "pct"),
    "sssi_pct": PlanningSpec("site-of-special-scientific-interest", "pct"),
    "ancient_woodland_pct": PlanningSpec("ancient-woodland", "pct"),
    "brownfield_register_pct": PlanningSpec("brownfield-land", "pct"),
    "scheduled_monument_pct": PlanningSpec("scheduled-monument", "pct"),
    "listed_building_density": PlanningSpec("listed-building-outline", "density"),
    "tpo_density": PlanningSpec("tree-preservation-zone", "density"),

    # Flood risk. The two zones are one dataset on the platform and two
    # factors in the catalogue, because they mean different things to a
    # developer: Zone 3 is a sequential-test refusal risk, Zone 2 is a
    # flood-risk-assessment requirement. Reporting one number for both would
    # be wrong in the direction that looks plausible.
    #
    # Zone 3 is a subset of Zone 2 on the published maps, so the two factors
    # are not disjoint and should not be summed. `zone 3` matches both
    # `Flood Zone 3` and the `3a`/`3b` subdivisions some authorities publish.
    "flood_zone2_pct": PlanningSpec(
        "flood-risk-zone", "pct", "flood-risk-type", ("zone 2",)),
    "flood_zone3_pct": PlanningSpec(
        "flood-risk-zone", "pct", "flood-risk-type", ("zone 3",)),
}


def _in_polygon(x: float, y: float, coords, kind: str) -> bool:
    """Point in polygon or multipolygon, holes included. Ray casting."""
    def in_ring(ring) -> bool:
        inside = False
        n = len(ring)
        for i in range(n - 1):
            x1, y1 = float(ring[i][0]), float(ring[i][1])
            x2, y2 = float(ring[i + 1][0]), float(ring[i + 1][1])
            if (y1 > y) != (y2 > y):
                xint = (x2 - x1) * (y - y1) / (y2 - y1) + x1
                if x < xint:
                    inside = not inside
        return inside

    polys = coords if kind == "MultiPolygon" else [coords]
    for poly in polys:
        if not poly:
            continue
        if in_ring(poly[0]) and not any(in_ring(h) for h in poly[1:]):
            return True
    return False


SAMPLE_GRID = 32          # 1,024 points over the AOI's bounding box


def _coverage(geometry: dict, features: List[dict]) -> float:
    """Share of the AOI covered by any of `features`, by sampling.

    The platform answers "which entities intersect this polygon" and does not
    compute intersection area, so the choice is between a real number and a
    quick one. Sampling a 32x32 grid inside the drawn shape and counting how
    many points fall inside a designation gives a percentage accurate to a
    couple of points — good enough to say "about a third of this site is in a
    conservation area", which is the actual question, and honest about being an
    estimate. Exact clipped areas need the geometries in a spatial index, which
    is the ingest tier's job.
    """
    ring = _ring(geometry)
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    west, east, south, north = min(xs), max(xs), min(ys), max(ys)

    # Only areal features can cover anything. The brownfield land register
    # publishes **points**, not polygons, and feeding one to `_in_polygon`
    # reached `len()` on a float and took the whole factor down with a
    # TypeError — found by the first live run, not by any fixture, because
    # every fixture in the test suite was written as a polygon.
    areal = [f for f in features
             if (f.get("geometry") or {}).get("type") in ("Polygon", "MultiPolygon")
             and (f.get("geometry") or {}).get("coordinates")]

    if features and not areal:
        # The dataset answered, and nothing it returned can be measured as
        # coverage. Reporting 0.0 here would say "no brownfield land on this
        # site" on the strength of not knowing how to read the answer — the
        # same false-zero this file already refuses for flood risk. Raising
        # falls back to the generator, which labels itself demo data.
        kinds = sorted({(f.get("geometry") or {}).get("type") for f in features})
        raise OpenDataError(
            f"{len(features)} entities returned, all {'/'.join(str(k) for k in kinds)} "
            f"— coverage needs polygons. This dataset probably wants a density "
            f"or an area attribute rather than a coverage estimate.")

    inside_aoi = 0
    covered = 0
    for i in range(SAMPLE_GRID):
        x = west + (east - west) * (i + 0.5) / SAMPLE_GRID
        for j in range(SAMPLE_GRID):
            y = south + (north - south) * (j + 0.5) / SAMPLE_GRID
            if not _in_polygon(x, y, [ring], "Polygon"):
                continue
            inside_aoi += 1
            for f in areal:
                if _in_polygon(x, y, f["geometry"]["coordinates"],
                               f["geometry"]["type"]):
                    covered += 1
                    break

    if not inside_aoi:
        return 0.0
    return round(100.0 * covered / inside_aoi, 1)


# Entities requested per planning query.
#
# The number matters less than what happens when it is reached. A large AOI
# over a city intersects far more than a hundred listed-building outlines, and
# the old code took whatever came back and computed a coverage or a density
# from it — so a truncated answer produced a confidently wrong number with no
# indication that anything had been left out. Densities came out capped;
# coverage came out low.
#
# Invisible in the 1.2 km test square around Guildford, wrong on the 250,000 ha
# AOI the app actually permits. Same shape as the `locate` bug: correct in the
# one place it was ever exercised.
PLANNING_LIMIT = 100


def _refuse_if_truncated(dataset: str, returned: int) -> None:
    """A full page back means there were probably more, and we cannot tell how
    many. Refuse rather than report a number derived from an unknown fraction
    of the answer — `_series_for` falls back to the generator, which labels
    itself demo data, and a labelled estimate beats an unlabelled wrong one."""
    if returned >= PLANNING_LIMIT:
        raise OpenDataError(
            f"{dataset}: {returned} entities returned, which is the page "
            f"limit — the real count is unknown and any coverage or density "
            f"computed from it would be too low. Draw a smaller area.")


def _feature_fields(feature: dict) -> List[Any]:
    """Every place the platform might have put a dataset-specific attribute.

    Some datasets surface these at the top level of a feature's properties,
    others under a `json` sub-object, and which one is not documented per
    dataset — so both are read rather than guessed between.
    """
    props = feature.get("properties") or {}
    out = [props]
    nested = props.get("json")
    if isinstance(nested, dict):
        out.append(nested)
    return out


def _feature_has(feature: dict, field: str) -> bool:
    """Is this attribute present at all, whatever its value?"""
    return any(field in d for d in _feature_fields(feature))


def _feature_matches(feature: dict, field: str, wanted: Tuple[str, ...]) -> bool:
    """Does this entity carry one of the wanted values in `field`?

    The platform puts dataset-specific attributes in a nested `properties`
    dict, but not consistently — some datasets surface them at the top level of
    the feature's properties, others under a `json` sub-object. Both are
    checked, and the comparison is case- and separator-insensitive, because the
    same zone appears as `Flood Zone 3`, `flood-zone-3` and `zone 3` across the
    register.
    """
    for value in [d.get(field) for d in _feature_fields(feature)]:
        if value is None:
            continue
        flat = str(value).lower().replace("-", " ").replace("_", " ").strip()
        if any(w in flat for w in wanted):
            return True
    return False


def planning_series(dataset: str, mode: str, geometry: dict, steps: List[str],
                    area_ha: float, field: Optional[str] = None,
                    values: Tuple[str, ...] = ()) -> List[Dict[str, Any]]:
    """One national designation dataset, measured inside the drawn shape.

    `pct` factors report the share of the AOI covered, estimated by sampling
    (see `_coverage`). `density` factors report intersecting features per
    square kilometre, which needs no geometry at all.

    `field`/`values` narrow one dataset to a subset of its entities. Flood risk
    is the case that needs it: the platform publishes Zone 2 and Zone 3 as one
    `flood-risk-zone` dataset distinguished by an attribute, and the catalogue
    asks for them separately — as it must, because they carry entirely
    different planning consequences. Without the filter both factors would
    return the same number, which is the kind of wrong that looks right.

    These are static in time. The platform records when an entity entered and
    left the register, but a conservation area designated in 1974 has no
    meaningful monthly series, so the value is held across the timeline and
    every month after the first is flagged as carried forward.
    """
    fmt = "geojson" if mode == "pct" else "json"
    data = _get(f"https://www.planning.data.gov.uk/entity.{fmt}",
                {"dataset": dataset, "geometry": _wkt(geometry),
                 "geometry_relation": "intersects", "limit": PLANNING_LIMIT})

    if mode == "density":
        entities = (data or {}).get("entities", [])
        _refuse_if_truncated(dataset, len(entities))
        km2 = max(0.01, area_ha / 100.0)
        return _static(steps, round(len(entities) / km2, 2))

    features = (data or {}).get("features", [])
    _refuse_if_truncated(dataset, len(features))
    if field and features:
        # Before trusting the filter, check the attribute exists at all.
        #
        # This matters more than it looks. `flood-risk-type` is taken from the
        # platform's published schema and has never been seen in a live
        # response. If the real key is something else, every feature fails the
        # filter, and "no feature matched" is indistinguishable from "no Zone 3
        # here" — so the app would report 0% flood risk, confidently, on a
        # floodplain. A silent false zero on the one factor a developer checks
        # before buying land is the worst failure available in this file.
        #
        # So an absent attribute raises instead, and `_series_for` falls back
        # to the generator and labels the result demo data. Wrong and labelled
        # beats wrong and authoritative.
        if not any(_feature_has(f, field) for f in features):
            raise OpenDataError(
                f"{dataset}: none of the {len(features)} entities carry "
                f"'{field}' — the attribute name is wrong, so the filter "
                f"cannot be trusted. Run scripts/discover_planning_datasets.py "
                f"to see the real attribute names.")
        # An entity carrying the attribute but not the wanted value is a real
        # answer — no Zone 3 here — and correctly reads as 0%.
        features = [f for f in features if _feature_matches(f, field, values)]

    if not features:
        return _static(steps, 0.0)
    return _static(steps, _coverage(geometry, features))


# ---------------------------------------------------------------------------
# HM Land Registry Price Paid — residential transactions
# ---------------------------------------------------------------------------
_PPD_QUERY = """
PREFIX ppi: <http://landregistry.data.gov.uk/def/ppi/>
PREFIX lrcommon: <http://landregistry.data.gov.uk/def/common/>
SELECT ?date ?amount ?newBuild ?type
WHERE {
  ?tx ppi:pricePaid ?amount ;
      ppi:transactionDate ?date ;
      ppi:propertyAddress ?addr .
  ?addr lrcommon:postcode ?postcode .
  FILTER(STRSTARTS(STR(?postcode), "%(district)s "))
  OPTIONAL { ?tx ppi:newBuild ?newBuild }
  OPTIONAL { ?tx ppi:propertyType ?type }
  FILTER(?date >= "%(start)s"^^<http://www.w3.org/2001/XMLSchema#date>)
}
LIMIT %(limit)d
"""

# Transactions requested per district.
#
# Fifteen years of a busy district can exceed this, and a truncated set makes
# every figure built on it wrong in a way nobody can see: the median moves, the
# count is capped, and the new-build share reflects whichever slice the store
# happened to return first. The Guildford test window is six months, which
# never comes close.
PPD_LIMIT = 20000


def ppd_group(geometry: dict, steps: List[str],
              area_ha: float) -> Dict[str, List[Dict[str, Any]]]:
    """Every price-paid factor from one SPARQL query.

    Land Registry publishes each residential sale in England and Wales with a
    date, a price, a postcode and a property type, under the OGL. One query per
    AOI returns the lot; the monthly aggregates are computed here rather than
    in fifteen more queries.

    Reported by **postcode district** (GU2), not by the drawn polygon — the
    dataset's finest public geography that reliably has enough transactions to
    average. A field has no sale price of its own; the district around it does.
    """
    loc = locate(geometry)
    query = _PPD_QUERY % {"district": loc["district"],
                          "start": steps[0] + "-01",
                          "limit": PPD_LIMIT}
    data = _get("https://landregistry.data.gov.uk/landregistry/query",
                {"query": query, "output": "json"})
    rows = ((data or {}).get("results") or {}).get("bindings", [])
    if len(rows) >= PPD_LIMIT:
        # A full page back means there were probably more, and which ones were
        # dropped is not knowable from here. A median computed from an unknown
        # slice is the kind of number that quietly acquires authority it has
        # not earned, so this refuses and falls back to labelled demo data.
        raise OpenDataError(
            f"{loc['district']}: {len(rows)} transactions returned, which is "
            f"the query limit — the median and count would be computed from "
            f"an unknown fraction of the sales. Ask for a shorter window.")

    by_month: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        date = row.get("date", {}).get("value", "")[:7]
        if not date:
            continue
        try:
            amount = float(row["amount"]["value"])
        except (KeyError, ValueError):
            continue
        by_month.setdefault(date, []).append({
            "amount": amount,
            "new": str(row.get("newBuild", {}).get("value", "")).lower() in ("true", "1"),
            "type": row.get("type", {}).get("value", "").rsplit("/", 1)[-1],
        })

    def median(xs: List[float]) -> float:
        xs = sorted(xs)
        n = len(xs)
        return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2

    avg, med, count, newb, flat = [], [], [], [], []
    for s in steps:
        sales = by_month.get(s, [])
        if not sales:
            # A month with no recorded sale is a real gap in a small district,
            # not a price of zero.
            avg.append(_gap(s)); med.append(_gap(s)); newb.append(_gap(s))
            flat.append(_gap(s))
            count.append(_point(s, 0))
            continue
        amounts = [x["amount"] for x in sales]
        avg.append(_point(s, round(sum(amounts) / len(amounts))))
        med.append(_point(s, round(median(amounts))))
        count.append(_point(s, len(sales)))
        newb.append(_point(s, round(100.0 * sum(1 for x in sales if x["new"]) / len(sales), 1)))
        flat.append(_point(s, round(100.0 * sum(1 for x in sales if x["type"] == "flat-maisonette")
                                    / len(sales), 1)))

    def yoy(points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = []
        for i, p in enumerate(points):
            prev = points[i - 12] if i >= 12 else None
            if p["value"] is None or prev is None or not prev["value"]:
                out.append(_gap(p["t"]))
            else:
                out.append(_point(p["t"], round(100.0 * (p["value"] - prev["value"]) / prev["value"], 1)))
        return out

    def growth5(points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = []
        for i, p in enumerate(points):
            prev = points[i - 60] if i >= 60 else None
            if p["value"] is None or prev is None or not prev["value"]:
                out.append(_gap(p["t"]))
            else:
                out.append(_point(p["t"], round(100.0 * (p["value"] - prev["value"]) / prev["value"], 1)))
        return out

    return {
        "avg_sale_price": avg,
        "median_sale_price": med,
        "transaction_count": count,
        "new_build_share": newb,
        "flat_share": flat,
        "price_change_yoy": yoy(med),
        "price_growth_5yr": growth5(med),
    }


# ---------------------------------------------------------------------------
# data.police.uk — street-level crime
# ---------------------------------------------------------------------------
def police_group(geometry: dict, steps: List[str],
                 area_ha: float) -> Dict[str, List[Dict[str, Any]]]:
    """Street-level crime inside the drawn shape, month by month.

    The API takes a polygon, so unlike the price data this really is *this
    area* rather than the district around it.

    **Slow on purpose to be honest**: one HTTP call per month, so a 15-year
    series is 180 calls and takes minutes on a first run. It is cached per AOI
    afterwards. This is the clearest example in the codebase of a source that
    belongs in the pre-aggregated tier rather than on the interactive path, and
    it is left on the interactive path deliberately so the cost is visible.

    Two honest limits: police.uk locates crimes at an anonymised "snap point"
    up to a few hundred metres from where they happened, so a small polygon
    measures its neighbourhood rather than itself; and coverage begins when
    each force started publishing, which is not the same month everywhere.
    """
    poly = _police_poly(geometry)
    km2 = max(0.01, area_ha / 100.0)

    total, burglary, violent, anti = [], [], [], []
    today = _dt.date.today()
    for s in steps:
        year, month = int(s[:4]), int(s[5:])
        # The archive does not cover the current month, and asking for the
        # future returns an empty list that would read as "no crime".
        if (year, month) >= (today.year, today.month):
            for lst in (total, burglary, violent, anti):
                lst.append(_gap(s))
            continue

        data = _get("https://data.police.uk/api/crimes-street/all-crime",
                    {"poly": poly, "date": s})
        if data is None:
            for lst in (total, burglary, violent, anti):
                lst.append(_gap(s))
            continue

        crimes = data if isinstance(data, list) else []
        n = len(crimes)
        cats = [c.get("category", "") for c in crimes]
        total.append(_point(s, round(n / km2, 2)))
        burglary.append(_point(s, round(sum(1 for c in cats if c == "burglary") / km2, 2)))
        if n:
            violent.append(_point(s, round(100.0 * sum(1 for c in cats if c == "violent-crime") / n, 1)))
            anti.append(_point(s, round(100.0 * sum(1 for c in cats if c == "anti-social-behaviour") / n, 1)))
        else:
            # No crimes recorded is a real zero for a count, but a share of
            # nothing is undefined.
            violent.append(_gap(s))
            anti.append(_gap(s))

    return {
        "crime_density": total,
        "burglary_density": burglary,
        "violent_crime_share": violent,
        "antisocial_share": anti,
    }


# ---------------------------------------------------------------------------
# EPC register — building energy performance
# ---------------------------------------------------------------------------
def epc_group(geometry: dict, steps: List[str],
              area_ha: float) -> Dict[str, List[Dict[str, Any]]]:
    """Domestic EPC certificates for the postcode, aggregated by lodgement month.

    The one source here that needs a credential: the register is free and open
    but requires a registered email and key sent as HTTP Basic auth. Without
    `EPC_API_KEY` (and `EPC_API_EMAIL`) this raises, the factor falls back to
    generated data, and the response says so — which is the correct behaviour
    for "open data behind a free signup".
    """
    email = os.environ.get("EPC_API_EMAIL")
    key = os.environ.get("EPC_API_KEY")
    if not (email and key):
        raise OpenDataError("EPC_API_EMAIL / EPC_API_KEY are not set — "
                            "register free at epc.opendatacommunities.org")

    loc = locate(geometry)
    data = _get("https://epc.opendatacommunities.org/api/v1/domestic/search",
                {"postcode": loc["postcode"], "size": 5000},
                auth=(email, key))
    rows = (data or {}).get("rows", [])

    by_month: Dict[str, List[dict]] = {}
    for row in rows:
        lodged = (row.get("lodgement-date") or "")[:7]
        if lodged:
            by_month.setdefault(lodged, []).append(row)

    bands = ["A", "B", "C", "D", "E", "F", "G"]

    def num(row, field) -> Optional[float]:
        try:
            return float(row.get(field))
        except (TypeError, ValueError):
            return None

    sap, band, below_c, uplift, floor, heatpump = [], [], [], [], [], []
    seen: List[dict] = []
    for s in steps:
        # Certificates accumulate: the stock's rating at a month is everything
        # lodged up to it, not just that month's handful.
        seen.extend(by_month.get(s, []))
        if not seen:
            for lst in (sap, band, below_c, uplift, floor, heatpump):
                lst.append(_gap(s))
            continue

        scores = [v for v in (num(r, "current-energy-efficiency") for r in seen) if v is not None]
        pots = [v for v in (num(r, "potential-energy-efficiency") for r in seen) if v is not None]
        areas = [v for v in (num(r, "total-floor-area") for r in seen) if v is not None]
        letters = [str(r.get("current-energy-rating", "")).upper() for r in seen]
        letters = [x for x in letters if x in bands]

        sap.append(_point(s, round(sum(scores) / len(scores), 1)) if scores else _gap(s))
        band.append(_point(s, max(set(letters), key=letters.count)) if letters else _gap(s))
        below_c.append(_point(s, round(100.0 * sum(1 for x in letters if x > "C") / len(letters), 1))
                       if letters else _gap(s))
        uplift.append(_point(s, round((sum(pots) / len(pots)) - (sum(scores) / len(scores)), 1))
                      if scores and pots else _gap(s))
        floor.append(_point(s, round(sum(areas) / len(areas), 1)) if areas else _gap(s))
        heat = [str(r.get("mainheat-description", "")).lower() for r in seen]
        heatpump.append(_point(s, round(100.0 * sum(1 for h in heat if "heat pump" in h) / len(heat), 1))
                        if heat else _gap(s))

    return {
        "epc_mean_sap": sap,
        "epc_band_mode": band,
        "epc_below_c_share": below_c,
        "epc_potential_uplift": uplift,
        "mean_floor_area": floor,
        "heat_pump_share": heatpump,
    }


# ---------------------------------------------------------------------------
# ONS — earnings, rents, affordability
# ---------------------------------------------------------------------------
def ons_stored_series(factor_id: str, geometry: dict, steps: List[str],
                      area_ha: float) -> List[Dict[str, Any]]:
    """One ONS indicator for the local authority containing the AOI.

    Read from what `ons/job.py` downloaded and parsed, not from an API. ONS
    publishes rents, earnings, affordability and the census as **spreadsheets
    on a release page**, so there is no per-area endpoint to call — which is
    why these factors stayed generated while the rest of this module went
    real, and why the fix had to be a scheduled job.

    Two consequences travel with every number and are recorded in the factor's
    provenance rather than smoothed over:

    * It is a **local authority** figure. A 5-hectare AOI reports its
      district's rent, not its own. Real data; not a measurement of the site.
    * It may be **years old**. The census is 2021 and deprivation is 2019.
      Values carried across months are flagged `interpolated`, so a chart
      cannot imply they were measured monthly.
    """
    import ons_store

    loc = locate(geometry)
    code = loc.get("admin_district_code")
    if not code:
        raise OpenDataError("no local authority code for this area")
    try:
        return ons_store.series(factor_id, code, steps)
    except ons_store.OnsStoreError as exc:
        raise OpenDataError(str(exc)) from exc


def rental_growth_series(geometry: dict, steps: List[str],
                         area_ha: float) -> List[Dict[str, Any]]:
    """Year-on-year change in the local authority's median rent.

    Derived from the stored monthly series rather than published, so it needs
    thirteen months of data to produce its first point. Months without a
    comparison twelve months back are gaps — an unanchored percentage is worse
    than no percentage.
    """
    import ons_store

    loc = locate(geometry)
    code = loc.get("admin_district_code")
    if not code:
        raise OpenDataError("no local authority code for this area")

    # Ask for each step and its anniversary in one pass.
    wanted = sorted({s for s in steps} | {_year_before(s) for s in steps})
    try:
        points = ons_store.series("rental_median", code, wanted)
    except ons_store.OnsStoreError as exc:
        raise OpenDataError(str(exc)) from exc

    by_month = {p["t"]: p["value"] for p in points}
    out = []
    for step in steps:
        now, then = by_month.get(step), by_month.get(_year_before(step))
        if now is None or not then:
            out.append(_gap(step))
        else:
            out.append(_point(step, round((now - then) / then * 100.0, 2)))
    return out


def gross_yield_series(geometry: dict, steps: List[str],
                       area_ha: float) -> List[Dict[str, Any]]:
    """Annual rent as a percentage of purchase price.

    The one number a residential investor actually asks for, and it exists
    here only because two separate sources are already in the process: ONS
    rents from the stored release, Land Registry sale prices from the live
    SPARQL query. Neither publishes it.

    Both sides are district-level, so this is the yield of the area rather
    than of the site — stated in the factor's provenance, because a yield
    quoted to four significant figures invites more precision than it has.
    """
    rents = ons_stored_series("rental_median", geometry, steps, area_ha)
    prices = ppd_group(geometry, steps, area_ha)["median_sale_price"]

    by_month = {p["t"]: p["value"] for p in prices}
    out = []
    for rent in rents:
        price = by_month.get(rent["t"])
        if rent["value"] is None or not price:
            out.append(_gap(rent["t"]))
            continue
        point = _point(rent["t"], round(rent["value"] * 12 / price * 100.0, 2))
        # Inherits the rent's carried-forward flag: a yield computed from a
        # held annual figure is itself held.
        point["interpolated"] = rent.get("interpolated", False)
        out.append(point)
    return out


def _year_before(step: str) -> str:
    return f"{int(step[:4]) - 1:04d}-{step[5:]}"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
# Which source each factor comes from, and how far it has been proven. The
# catalogue and the UI read this, so "we wrote it" is never displayed as "we
# ran it".
#
#   verified  — run against the live endpoint and checked by a human
#   written   — implemented against the documented API, covered by fixture
#               tests, not yet run against the live service
SOURCE_STATUS: Dict[str, Dict[str, str]] = {}


# ---------------------------------------------------------------------------
# What has actually been run against a live service
# ---------------------------------------------------------------------------
#
# For most of this project's life this was empty and the honest count of
# verified factors was 1 — NDVI, checked by hand. Everything else was written
# against documented API shapes and covered by fixture tests, which proves the
# parsing and proves nothing about whether the endpoint still answers.
#
# On 2026-08-09 `scripts/verify.py` was run from Google Cloud Shell, which has
# ordinary outbound internet, and 21 of 24 open-data checks returned plausible
# live values — right number of points, inside the catalogue's declared range,
# not all gaps. The observed figures are recorded beside each group so a future
# reader can tell a real verification from a tick.
#
# **Only add to this from an actual run.** A factor listed here claims, in the
# UI and in every export, that a human has seen it work against the real
# service. That claim is the one thing in this repository that cannot be
# rebuilt from the code, so it must never be written from optimism.
VERIFIED_ON = "2026-08-09"

VERIFIED: Dict[str, str] = {
    # HM Land Registry Price Paid, via one SPARQL query.
    # `avg_sale_price` is deliberately absent: it is in the same group and
    # almost certainly worked, but its line was not in the captured output and
    # "almost certainly" is not the standard this list is held to.
    "median_sale_price": "£425,000 for 2026-05",
    "transaction_count": "32 transactions for 2026-05",
    "new_build_share": "0.0% for 2026-05",
    "flat_share": "50.0% for 2026-05",

    # data.police.uk street-level crime, one call per month.
    "crime_density": "230.0 per km² for 2026-05",
    "burglary_density": "5.0 per km² for 2026-05",
    "violent_crime_share": "24.6% for 2026-05",
    "antisocial_share": "16.7% for 2026-05",

    # planning.data.gov.uk designations. Only the three that came back with a
    # real measurement are here.
    #
    # Twelve of the thirteen planning checks "passed", and ten of those
    # returned 0.0 — which is the correct answer for a Guildford site with no
    # SSSI on it, and *also* precisely what a misspelled dataset name returns,
    # because `planning_series` reports no-entities as zero coverage. A zero
    # confirms the code path and says nothing about whether we asked for the
    # right dataset, so promoting all twelve would have claimed ten things
    # nobody has established.
    "conservation_area_pct": "53.3% of the AOI — the measurement that proves "
                             "the query finds and clips real entities",
    "green_belt_pct": "0.8% of the AOI",
    "scheduled_monument_pct": "0.9% of the AOI",
}

# Ran clean, returned only zeros, still `written`. To settle these, run
# `scripts/check_open_data.py --source planning --lat 50.90 --lon -0.60` over
# the South Downs, where national park and AONB must be non-zero:
#   article4_pct, national_park_pct, aonb_pct, sssi_pct, ancient_woodland_pct,
#   listed_building_density, tpo_density, flood_zone2_pct, flood_zone3_pct
#
# The flood pair is the frustrating one — the *attribute name* is confirmed by
# the discovery script, but no run has yet found a site with flood zone on it.

# `price_change_yoy` and `price_growth_5yr` are deliberately absent. They are
# derived from twelve and sixty months of history respectively, and the check
# asks for six — so every point was correctly a gap and nothing was verified.
# That is the check's window being too short, not the integration failing, and
# recording them as verified on the strength of a run that never exercised
# them would be exactly the overclaim this file exists to prevent. Re-run with
# `--months 72` to test them for real.


def _mark(factors, source: str, status: str = "written", note: str = "",
          endpoint: str = "") -> None:
    """`endpoint` is the host actually queried, which is not always the
    publisher. SSSI boundaries are Natural England's data, but we get them
    from planning.data.gov.uk, and a user told only "Natural England" cannot
    reproduce the number they are looking at. Both belong in the answer."""
    for f in factors:
        status_now = "verified" if f in VERIFIED else status
        note_now = note
        if f in VERIFIED:
            seen = VERIFIED[f]
            note_now = (f"run against the live service on {VERIFIED_ON} — "
                        f"{seen}" + (f"; {note}" if note else ""))
        SOURCE_STATUS[f] = {"source": source, "status": status_now,
                            "note": note_now,
                            "endpoint": endpoint or source}


def _group_installer(fn: Callable, factor_id: str) -> Callable:
    """Adapt a group fetcher to the one-factor-at-a-time registry, with a
    per-request memo so six factors from one query cost one query."""
    memo: Dict[tuple, Dict[str, List[Dict[str, Any]]]] = {}

    def call(geometry: dict, steps: List[str], area_ha: float):
        key = cache_mod.cache_key(fn.__name__, geometry, steps)
        with _LOCK:
            hit = memo.get(key)
        if hit is None:
            hit = fn(geometry, steps, area_ha)
            with _LOCK:
                memo.clear()          # one AOI at a time; this is not the cache
                memo[key] = hit
        points = hit.get(factor_id)
        if points is None:
            raise OpenDataError(f"{fn.__name__} did not return {factor_id}")
        return points

    return call


def install(registry: Dict[str, Any],
            provenance: Optional[Dict[str, Any]] = None) -> None:
    """Register every open-data factor into routes_catalog's hook.

    Called by both backends — the Vercel function and `app.py` — because none
    of this needs Earth Engine. Anything not registered keeps returning
    generated data and keeps saying so.
    """
    import catalog

    for factor_id, spec in PLANNING_DATASETS.items():
        if factor_id not in catalog.FACTOR_BY_ID:
            continue
        registry[factor_id] = (
            lambda g, s, a, _sp=spec: planning_series(
                _sp.dataset, _sp.mode, g, s, a, _sp.field, _sp.values))
    # These eleven come from one host but five publishers — SSSI and AONB
    # boundaries are Natural England's, listed buildings are Historic
    # England's, and MHCLG aggregates them. The catalogue already knows who
    # publishes each, so name the publisher and record the host we actually
    # queried separately, rather than flattening both into one wrong answer.
    for factor_id in PLANNING_DATASETS:
        if factor_id not in catalog.FACTOR_BY_ID:
            continue
        base = catalog.BASE_BY_ID[catalog.FACTOR_BY_ID[factor_id]["base"]]
        _mark([factor_id], base["source"], "written",
              "served through the Planning Data Platform, not the publisher's "
              "own API; coverage is approximated from intersecting entities, "
              "not clipped area",
              endpoint="planning.data.gov.uk")

    for factor_id in ("avg_sale_price", "median_sale_price", "transaction_count",
                      "new_build_share", "flat_share", "price_change_yoy",
                      "price_growth_5yr"):
        if factor_id in catalog.FACTOR_BY_ID:
            registry[factor_id] = _group_installer(ppd_group, factor_id)
    _mark(["avg_sale_price", "median_sale_price", "transaction_count",
           "new_build_share", "flat_share", "price_change_yoy", "price_growth_5yr"],
          "HM Land Registry", "written",
          "reported for the postcode district containing the AOI, not the AOI itself",
          endpoint="landregistry.data.gov.uk")

    for factor_id in ("crime_density", "burglary_density", "violent_crime_share",
                      "antisocial_share"):
        if factor_id in catalog.FACTOR_BY_ID:
            registry[factor_id] = _group_installer(police_group, factor_id)
    _mark(["crime_density", "burglary_density", "violent_crime_share", "antisocial_share"],
          "Home Office / police forces", "written",
          "one HTTP call per month; anonymised to snap points, so a small "
          "polygon measures its neighbourhood",
          endpoint="data.police.uk")

    if os.environ.get("EPC_API_KEY"):
        for factor_id in ("epc_mean_sap", "epc_band_mode", "epc_below_c_share",
                          "epc_potential_uplift", "mean_floor_area", "heat_pump_share"):
            if factor_id in catalog.FACTOR_BY_ID:
                registry[factor_id] = _group_installer(epc_group, factor_id)
        _mark(["epc_mean_sap", "epc_band_mode", "epc_below_c_share",
               "epc_potential_uplift", "mean_floor_area", "heat_pump_share"],
              "Department for Levelling Up / EPC register", "written",
              "needs EPC_API_EMAIL and EPC_API_KEY",
              endpoint="epc.opendatacommunities.org")

    # ONS and MHCLG spreadsheets, via the scheduled job. Registered only for
    # factors the store can actually answer: until `python3 -m ons.job` has run
    # once there is no data, and a factor with nothing behind it must keep
    # saying "generated" rather than promising a number it cannot produce.
    try:
        import ons_store

        for factor_id in ons_store.available_factors():
            if factor_id not in catalog.FACTOR_BY_ID:
                continue
            registry[factor_id] = (
                lambda g, s, a, _f=factor_id: ons_stored_series(_f, g, s, a))
            meta = ons_store.factor_meta(factor_id)
            retrieved = (meta.get("retrieved") or "")[:10]
            _mark([factor_id], meta.get("publisher") or "ONS", "written",
                  f"published for the local authority containing the AOI, not "
                  f"the AOI itself; {meta.get('title', 'release')} "
                  f"({meta.get('latest_period') or 'unknown period'}), "
                  f"downloaded {retrieved or 'unknown date'}",
                  endpoint=f"ons.gov.uk (stored release, {meta.get('dataset')})")
        # Two factors nobody publishes, derived from what is now in the
        # process. They register only when their inputs do.
        if "rental_median" in ons_store.available_factors():
            if "rental_growth_yoy" in catalog.FACTOR_BY_ID:
                registry["rental_growth_yoy"] = rental_growth_series
                _mark(["rental_growth_yoy"], "Office for National Statistics",
                      "written",
                      "derived from the stored rent series; needs thirteen "
                      "months of data before its first point",
                      endpoint="ons.gov.uk (stored release, private_rents)")
            if "gross_yield" in catalog.FACTOR_BY_ID:
                registry["gross_yield"] = gross_yield_series
                _mark(["gross_yield"], "ONS and HM Land Registry", "written",
                      "annual rent over sale price, both district-level — the "
                      "yield of the area, not of the site",
                      endpoint="ons.gov.uk + landregistry.data.gov.uk")
    except Exception:                                   # pragma: no cover
        # A missing store must not stop the backend booting; it is the normal
        # state before the job has ever run.
        pass

    if provenance is not None:
        for factor_id in registry:
            if factor_id in SOURCE_STATUS:
                provenance[factor_id] = dict(SOURCE_STATUS[factor_id])
