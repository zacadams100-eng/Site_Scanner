"""
Measured rainfall, from Environment Agency gauges.

Everything in the "Water" group is currently generated. This makes four of it
real, from the Environment Agency's Hydrology API — an open, keyless service
carrying the daily rainfall record from the EA's own gauge network.

    https://environment.data.gov.uk/hydrology/doc/reference

## Why these are new factors and not the existing precipitation ones

`precip_total` and its siblings hang off the `haduk_precip` base — Met Office
HadUK-Grid, a 1 km *gridded areal* product. A rain gauge is a point. Over a
20-hectare site those two answer different questions, and the gridded one is
usually the better answer for an area: it has already reconciled the gauge
network onto a grid, and it does not care whether a gauge happens to sit
inside your boundary.

So serving gauge readings into a factor whose provenance says "HadUK-Grid"
would be a mislabel of exactly the kind `scripts/audit_catalogue.py` exists to
catch. These are separate factors, under their own base, named as gauge
measurements, and the catalogue says which gauge answered.

The honest trade is stated in each factor's note: this is a real measurement
at a real place, which may be several kilometres from the site.

## What is deliberately not implemented

**SPI-3.** The catalogue's drought index wants a standardised precipitation
index, which requires fitting a gamma distribution to the historical record
per calendar month and transforming to a normal deviate. A z-score of
three-month totals is *not* SPI — rainfall is strongly right-skewed, so the
two disagree most in exactly the dry tail the index exists to measure.
Shipping a z-score under the name SPI would be the "approximation is worse
than absence" failure `HANDOFF.md` records for the tasselled-cap indices.

**Flood zones, abstraction and water stress.** Those need the EA's spatial
services (WFS/OGC), whose layer names could not be confirmed from the
environment this was written in. See `BLOCKERS.md §7`: registering a factor
against an endpoint that cannot answer it makes the UI claim real data and
then fail on every request, which is worse than the honest label it has now.

## Verification status

**Written, not verified.** Every request here is shaped from the API's
published reference; none has been run against the live service, because this
environment's proxy denies `environment.data.gov.uk`. Run
`scripts/check_environment_agency.py` on any machine with ordinary internet:
it either promotes these to `verified` or names exactly what is wrong.
"""

from __future__ import annotations

import datetime as _dt
import math
import threading
from typing import Any, Dict, List, Optional, Tuple

import cache as cache_mod
from open_data import OpenDataError, _SESSION, TIMEOUT, _gap, _point, _ring

BASE_URL = "https://environment.data.gov.uk/hydrology"

# How far from the site to look for a gauge before giving up.
#
# Rainfall decorrelates with distance, and a gauge 40 km away over a hill is
# not measuring this site's weather. 25 km is generous for lowland England,
# where the EA network is dense, and the answer carries the actual distance so
# the user can judge it rather than trusting the threshold.
SEARCH_RADIUS_KM = 25.0

# A day at or above this counts as a wet day. The Met Office and WMO
# convention, so the number is comparable with published statistics rather
# than being this application's private definition.
WET_DAY_MM = 1.0

_LOOKUP = cache_mod.TTLCache(ttl=3600, max_entries=256)
_LOCK = threading.Lock()


def _get(path: str, params: Optional[dict] = None) -> Any:
    """One GET against the Hydrology API, cached for the process lifetime."""
    url = f"{BASE_URL}{path}"
    key = cache_mod.cache_key("ea-hyd", url, params or {})
    hit = _LOOKUP.get(key)
    if hit is not None:
        return hit
    try:
        resp = _SESSION.get(url, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:                              # noqa: BLE001
        raise OpenDataError(f"Environment Agency hydrology: {exc}") from exc
    _LOOKUP.set(key, data)
    return data


def _centroid(geometry: dict) -> Tuple[float, float]:
    ring = _ring(geometry)
    lngs = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return sum(lngs) / len(lngs), sum(lats) / len(lats)


def _haversine_km(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_rainfall_station(geometry: dict) -> Dict[str, Any]:
    """The closest rainfall gauge to the site, with its distance.

    The API's own `lat`/`long`/`dist` search does the filtering server-side;
    the results are re-sorted here by true great-circle distance because
    "within `dist` km" is a filter, not an ordering, and the first row of an
    unordered result is not the nearest gauge.
    """
    lng, lat = _centroid(geometry)
    data = _get("/id/stations.json", {
        "observedProperty": "rainfall",
        "lat": round(lat, 5),
        "long": round(lng, 5),
        "dist": SEARCH_RADIUS_KM,
        "_limit": 100,
    })
    items = data.get("items") or []
    if not items:
        raise OpenDataError(
            f"no Environment Agency rainfall gauge within {SEARCH_RADIUS_KM:g} km "
            f"of {lat:.4f}, {lng:.4f}")

    scored: List[Tuple[float, Dict[str, Any]]] = []
    for it in items:
        slat, slng = it.get("lat"), it.get("long")
        if slat is None or slng is None:
            continue
        scored.append((_haversine_km(lng, lat, float(slng), float(slat)), it))
    if not scored:
        raise OpenDataError("Environment Agency returned gauges with no coordinates")

    scored.sort(key=lambda s: s[0])
    dist, station = scored[0]
    return {
        "id": station.get("notation") or station.get("stationReference") or "",
        "label": _label(station.get("label")),
        "lat": float(station["lat"]),
        "lng": float(station["long"]),
        "distance_km": round(dist, 2),
    }


def _label(value: Any) -> str:
    """The API returns `label` as either a string or a list of them."""
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value or "")


def _daily_readings(station_id: str, start: str, end: str) -> List[Tuple[str, float]]:
    """Daily rainfall totals for one gauge, as (YYYY-MM-DD, mm).

    `period=86400` asks for the daily-total measure rather than the 15-minute
    tipping-bucket series. Requesting the raw series and summing it here would
    be both far more data and less correct — the EA applies its own quality
    control when it publishes the daily figure.
    """
    data = _get("/data/readings.json", {
        "station": station_id,
        "observedProperty": "rainfall",
        "period": 86400,
        "mineq-date": start,
        "maxeq-date": end,
        "_limit": 20000,
    })
    out: List[Tuple[str, float]] = []
    for row in data.get("items") or []:
        day = str(row.get("date") or "")[:10]
        value = row.get("value")
        if not day or value is None:
            continue
        # A reading the EA flags as invalid or missing is a gap, not a zero.
        # On rainfall the difference is total: a broken gauge reads zero, and
        # zero is also the most common true value.
        if row.get("quality") in {"Missing", "Invalid"}:
            continue
        try:
            out.append((day, float(value)))
        except (TypeError, ValueError):
            continue
    return out


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (_dt.date(year, month + 1, 1) - _dt.date(year, month, 1)).days


def rainfall_group(geometry: dict, steps: List[str],
                   area_ha: float) -> Dict[str, List[Dict[str, Any]]]:
    """All four rainfall factors from one gauge and one readings query.

    Four factors, one round trip: the daily series answers every one of them,
    and fetching it four times would be four times the load on a free public
    service for identical bytes.
    """
    if not steps:
        return {}

    station = nearest_rainfall_station(geometry)
    start = f"{steps[0]}-01"
    last_y, last_m = int(steps[-1][:4]), int(steps[-1][5:7])
    end = f"{steps[-1]}-{_days_in_month(last_y, last_m):02d}"

    readings = _daily_readings(station["id"], start, end)
    by_month: Dict[str, List[float]] = {}
    for day, mm in readings:
        by_month.setdefault(day[:7], []).append(mm)

    total, heaviest, wet, dry = [], [], [], []
    for step in steps:
        values = by_month.get(step)
        expected = _days_in_month(int(step[:4]), int(step[5:7]))
        if not values:
            for series in (total, heaviest, wet, dry):
                series.append(_gap(step))
            continue

        # A month the gauge only half-covered is reported with the fraction it
        # managed, not silently scaled up. `valid_fraction` is what the map
        # hatches and the table greys out, so a part-month arrives labelled
        # rather than looking like a dry spell.
        valid = min(1.0, len(values) / expected)
        total.append(_point(step, round(sum(values), 1), valid))
        heaviest.append(_point(step, round(max(values), 1), valid))
        wet_count = sum(1 for v in values if v >= WET_DAY_MM)
        wet.append(_point(step, wet_count, valid))
        dry.append(_point(step, len(values) - wet_count, valid))

    return {
        "ea_rain_total": total,
        "ea_rain_max_daily": heaviest,
        "ea_rain_wet_days": wet,
        "ea_rain_dry_days": dry,
        # Not a factor — carried so `install` can name the gauge that answered.
        "_station": station,
    }


FACTOR_IDS = ("ea_rain_total", "ea_rain_max_daily",
              "ea_rain_wet_days", "ea_rain_dry_days")


def install(registry: Dict[str, Any],
            provenance: Optional[Dict[str, Any]] = None) -> None:
    """Register the rainfall factors. No credential, so both backends call it."""
    import catalog
    import open_data

    memo: Dict[tuple, Dict[str, Any]] = {}

    def fetch(factor_id: str):
        def call(geometry: dict, steps: List[str], area_ha: float):
            key = cache_mod.cache_key("ea-rain", geometry, steps)
            with _LOCK:
                hit = memo.get(key)
            if hit is None:
                hit = rainfall_group(geometry, steps, area_ha)
                with _LOCK:
                    memo.clear()          # one AOI at a time; not the cache
                    memo[key] = hit
            points = hit.get(factor_id)
            if points is None:
                raise OpenDataError(f"rainfall_group did not return {factor_id}")
            return points
        return call

    registered = [f for f in FACTOR_IDS if f in catalog.FACTOR_BY_ID]
    for factor_id in registered:
        registry[factor_id] = fetch(factor_id)

    if registered:
        open_data._mark(
            registered, "Environment Agency", "written",
            "measured at the nearest EA rain gauge, which may be several "
            "kilometres from the site — a point observation, not an areal "
            "average over the boundary",
            endpoint="environment.data.gov.uk/hydrology")

    if provenance is not None:
        for factor_id in registered:
            provenance[factor_id] = dict(open_data.SOURCE_STATUS[factor_id])
