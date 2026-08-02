"""
Site Scanner — monthly time-series generation
---------------------------------------------
Produces a 15-year monthly series for any factor over any drawn area.

In production this module's `generate_series` is replaced by the two query
paths described in TECHNICAL_PLAN.md §3.4 — an H3 aggregate lookup for the
instant answer and a windowed COG read for the exact one. The *shape* it
returns is the contract between those and the frontend, so it is worth getting
right now, while it costs nothing to change.

What is deliberately faithful, because the frontend has to handle all of it:

  * **Gaps are real.** Optical factors go blank in cloudy months — the value is
    `None`, not an interpolated guess. This is decision 10, implemented rather
    than described.
  * **Cadence varies per factor.** Static factors are flat, annual factors are
    stepped with `interpolated: true` on the months between observations, and
    monthly factors move every step. This is decision 9.
  * **`valid_fraction` travels with every point.** A number derived from three
    cloud-free pixels must be visibly weaker than one derived from thousands.
  * **Seasonality is genuine.** NDVI peaks in summer, precipitation in winter,
    frost days only in winter. A timeline demo where everything is noise
    teaches you nothing about whether the timeline works.
"""

import hashlib
import math
import random
from typing import Any, Dict, List, Optional, Tuple

from catalog import CLASS_VALUES, FACTOR_BY_ID, TIME_END, TIME_START

# Factors whose observation depends on a clear sky at the moment of capture.
# Sentinel-2 optical and MODIS thermal have cloud gaps; radar and modelled
# reanalysis do not.
#
# ESA WorldCover is deliberately *not* here. It is an annual composite built
# from a full year of imagery, so cloud is already resolved upstream — it does
# not blank out in December the way a monthly optical index does. Treating it
# as cloud-limited put spurious holes in a product that has none.
CLOUD_LIMITED_BASES = {"sentinel2_sr", "modis_lst"}

# Below this fraction of valid pixels we report no value at all rather than a
# number nobody should trust.
GAP_THRESHOLD = 0.15

# Northern-hemisphere seasonal phase, in months, per factor group. A value of 0
# peaks in January; 6 peaks in July.
SEASON_PEAK = {
    "Vegetation": 7.0,      # midsummer canopy
    "Temperature": 7.5,     # late July
    "Water": 0.5,           # wettest in January
    "Air quality": 1.0,     # winter inversions trap pollutants
    "Radar": 7.0,
    "Night lights": 0.0,    # brightest in the dark months
}

# How strongly each group swings through the year, as a fraction of its range.
SEASON_AMPLITUDE = {
    "Vegetation": 0.34,
    "Temperature": 0.40,
    "Water": 0.28,
    "Air quality": 0.22,
    "Radar": 0.12,
    "Night lights": 0.30,
    "People & economy": 0.03,
}


def month_steps(start: str = TIME_START, end: str = TIME_END) -> List[str]:
    """Every 'YYYY-MM' from start to end inclusive."""
    sy, sm = (int(x) for x in start.split("-"))
    ey, em = (int(x) for x in end.split("-"))
    out: List[str] = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def _rng(*parts: Any) -> random.Random:
    """Stable across processes — the same shape must always give the same
    numbers, or the charts flicker between reloads."""
    key = "|".join(str(p) for p in parts).encode("utf-8")
    return random.Random(int.from_bytes(hashlib.sha256(key).digest()[:8], "big"))


def _unit_noise(*parts: Any) -> float:
    """Deterministic value in [0, 1) without constructing a full Random."""
    key = "|".join(str(p) for p in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(key).digest()[:4], "big") / 2**32


def _site_character(lng: float, lat: float) -> Dict[str, float]:
    """A stable 'personality' for a location, so that two nearby shapes behave
    alike and a northern upland site reads differently from a southern city.

    Without this every drawn shape returns statistically identical data and the
    map stops meaning anything.
    """
    r = _rng("site", round(lng, 3), round(lat, 3))
    # Latitude drives temperature and growing season across England.
    northness = (lat - 49.9) / (55.8 - 49.9)          # 0 south, 1 north
    return {
        "urbanity": r.random(),          # 0 rural, 1 dense urban
        "wetness": 0.35 + 0.5 * r.random() + 0.15 * northness,
        "elevation": r.random() ** 1.6,  # most of England is low-lying
        "northness": northness,
        "affluence": r.random(),
    }


def _baseline(factor: Dict[str, Any], site: Dict[str, float], area_ha: float) -> float:
    """Where in its plausible range this particular site sits, before any
    seasonal or year-on-year movement is applied."""
    lo, hi = factor["lo"], factor["hi"]
    span = hi - lo
    group = factor["group"]
    fid = factor["id"]
    u = site["urbanity"]

    # Position in range, 0..1. Nudged by the site's character so the numbers
    # hang together — a built-up site is warm, sealed, polluted and expensive.
    pos = _unit_noise("base", fid, round(site["urbanity"], 4), round(site["northness"], 4))
    pos = 0.35 * pos + 0.65 * _coherent_position(fid, group, site)

    if fid in ("lc_built_pct", "impervious_pct", "built_pct", "building_density",
               "road_density", "population_density", "no2", "nightlight_radiance"):
        pos = min(1.0, 0.15 + 0.85 * u)
    elif fid in ("lc_tree_pct", "lc_crop_pct", "lc_grass_pct", "ndvi", "evi"):
        pos = max(0.0, 0.85 - 0.6 * u) * (0.7 + 0.6 * pos)

    # Small AOIs are more extreme; large ones regress toward the middle because
    # they average over more varied ground. This is real, and it matters for
    # anyone comparing a field against a county.
    pull = min(1.0, area_ha / 20000.0)
    pos = pos * (1 - 0.45 * pull) + 0.5 * (0.45 * pull)

    return lo + span * max(0.0, min(1.0, pos))


def _coherent_position(fid: str, group: str, site: Dict[str, float]) -> float:
    """Ties related factors to the same underlying site character, so NDVI and
    tree cover agree, and heat and built-up agree."""
    if group in ("Temperature",):
        return 0.75 - 0.45 * site["northness"] + 0.2 * site["urbanity"]
    if group in ("Water", "Flood & water"):
        return 0.25 + 0.55 * site["wetness"] - 0.3 * site["elevation"]
    if group == "Terrain":
        return site["elevation"]
    if group in ("People & economy",):
        return 0.2 + 0.6 * site["affluence"]
    if group in ("Air quality", "Built environment", "Night lights"):
        return 0.1 + 0.8 * site["urbanity"]
    if group in ("Vegetation", "Land cover", "Designations"):
        return 0.8 - 0.55 * site["urbanity"]
    return 0.5


def _trend_per_year(factor: Dict[str, Any], site: Dict[str, float]) -> float:
    """Long-run drift as a fraction of range per year. Warming, urbanisation
    and house prices go up; frost days and rural land go down. A 15-year
    timeline is pointless if nothing trends."""
    fid, group = factor["id"], factor["group"]
    r = _rng("trend", fid, round(site["urbanity"], 3))
    jitter = (r.random() - 0.5) * 0.004

    if group == "Temperature":
        return 0.006 + jitter
    if fid == "frost_days":
        return -0.008 + jitter
    if fid in ("lc_built_pct", "built_pct", "impervious_pct", "building_density"):
        return 0.004 * (0.3 + site["urbanity"]) + jitter
    if fid in ("avg_sale_price", "price_per_m2"):
        return 0.021 + jitter
    if fid in ("no2", "pm25", "pm10", "so2"):
        return -0.010 + jitter          # air quality has genuinely improved
    if fid in ("lc_tree_pct", "ancient_woodland_pct"):
        return 0.001 + jitter
    if fid in ("lc_crop_pct", "lc_grass_pct"):
        return -0.002 + jitter
    return jitter


def _seasonal(factor: Dict[str, Any], month: int) -> float:
    """Fraction-of-range seasonal offset for a given month."""
    group = factor["group"]
    amp = SEASON_AMPLITUDE.get(group, 0.0)
    if amp == 0.0:
        return 0.0
    peak = SEASON_PEAK.get(group, 7.0)
    phase = (month - peak) / 12.0 * 2 * math.pi
    swing = math.cos(phase)

    # A few factors have their own shape rather than their group's.
    fid = factor["id"]
    if fid == "frost_days":
        return -amp * swing * 1.6
    if fid in ("dry_days", "sunshine_hours", "o3", "solar_ghi"):
        return -amp * swing            # inverse of the Water group's phase
    if fid == "growing_degree_days":
        return amp * max(0.0, swing) * 1.8
    return amp * swing


def _valid_fraction(factor: Dict[str, Any], year: int, month: int,
                    site: Dict[str, float]) -> float:
    """How much of the area produced a usable observation.

    English winters are genuinely cloudy — December optical coverage is often
    under 20%. The frontend must show that honestly rather than pretending a
    January NDVI is as solid as a July one.
    """
    if factor["base"] not in CLOUD_LIMITED_BASES:
        return 1.0
    # Summer clear, winter poor.
    seasonal_clear = 0.5 + 0.42 * math.cos((month - 7.0) / 12.0 * 2 * math.pi)
    noise = _unit_noise("cloud", factor["base"], year, month,
                        round(site["wetness"], 3))
    frac = seasonal_clear * (0.55 + 0.75 * noise)
    frac -= 0.12 * site["wetness"]
    return max(0.0, min(1.0, frac))


def _categorical_value(factor: Dict[str, Any], year: int,
                       site: Dict[str, float]) -> str:
    classes = CLASS_VALUES.get(factor["id"], ["Unknown"])
    if factor["id"] == "lc_dominant":
        u = site["urbanity"]
        weights = [max(0.02, 0.9 - u), 0.12, max(0.05, 0.7 - 0.4 * u),
                   max(0.05, 0.8 - 0.6 * u), 0.1 + 1.4 * u, 0.05, 0.08, 0.05]
    else:
        weights = [1.0] * len(classes)
    r = _rng("cat", factor["id"], round(site["urbanity"], 3),
             round(site["northness"], 3), year // 5)
    return r.choices(classes, weights=weights, k=1)[0]


def generate_series(factor_id: str, geometry_centroid: Tuple[float, float],
                    area_ha: float, steps: List[str]) -> Dict[str, Any]:
    """A full monthly series for one factor over one area.

    Returns the shape the frontend consumes:
        {
          "factor_id": "ndvi",
          "kind": "continuous",
          "cadence": "monthly",
          "points": [
            {"t": "2011-01", "value": 0.41, "valid_fraction": 0.22,
             "interpolated": false},
            {"t": "2011-02", "value": null, "valid_fraction": 0.08, ...},
            ...
          ]
        }

    `value: null` means no usable observation. It is never filled in.
    """
    factor = FACTOR_BY_ID.get(factor_id)
    if factor is None:
        raise ValueError(f"Unknown factor {factor_id!r}")

    lng, lat = geometry_centroid
    site = _site_character(lng, lat)
    cadence = factor["cadence"]
    points: List[Dict[str, Any]] = []

    if factor["kind"] == "categorical":
        for step in steps:
            year, month = (int(x) for x in step.split("-"))
            points.append({
                "t": step,
                "value": _categorical_value(factor, year, site),
                "valid_fraction": _valid_fraction(factor, year, month, site),
                # A yearly product shown on a monthly axis is stepped, and the
                # months between observations are marked as such.
                "interpolated": cadence in ("annual", "5 years", "periodic") and month != 1,
            })
        return _wrap(factor, points)

    base = _baseline(factor, site, area_ha)
    lo, hi = factor["lo"], factor["hi"]
    span = hi - lo
    trend = _trend_per_year(factor, site)
    first_year = int(steps[0].split("-")[0])

    for step in steps:
        year, month = (int(x) for x in step.split("-"))

        if cadence == "static":
            value = base
            valid = 1.0
            interpolated = False
        else:
            # Static-in-year products hold their January value all year.
            sample_month = 1 if cadence in ("annual", "5 years", "periodic") else month
            sample_year = year - (year % 5) if cadence == "5 years" else year

            drift = trend * (sample_year - first_year) * span
            season = _seasonal(factor, sample_month) * span
            wobble = (_unit_noise("v", factor_id, sample_year, sample_month,
                                  round(lng, 3), round(lat, 3)) - 0.5) * 0.09 * span

            value = base + drift + season + wobble
            valid = _valid_fraction(factor, year, month, site)
            interpolated = cadence in ("annual", "5 years", "periodic") and month != 1

        value = max(lo, min(hi, value))

        # The honest gap. Cloud-limited factors simply have no answer some
        # months, and the chart must show a hole rather than a straight line.
        if valid < GAP_THRESHOLD:
            points.append({"t": step, "value": None, "valid_fraction": round(valid, 3),
                           "interpolated": False})
            continue

        points.append({
            "t": step,
            "value": round(value, 4),
            "valid_fraction": round(valid, 3),
            "interpolated": interpolated,
        })

    return _wrap(factor, points)


def _wrap(factor: Dict[str, Any], points: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "factor_id": factor["id"],
        "kind": factor["kind"],
        "cadence": factor["cadence"],
        "unit": factor["unit"],
        "points": points,
    }


def annual_rollup(series: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Collapse a monthly series into one row per year — the attribute table's
    default view (decision 5).

    Continuous factors report mean/min/max plus how many months contributed.
    Categorical factors report the modal class instead, because averaging a
    class code is meaningless (TECHNICAL_PLAN.md §8.5).

    `months_observed` is what stops a year built from two cloud-free Julys
    from looking as authoritative as one built from twelve months.
    """
    by_year: Dict[int, List[Dict[str, Any]]] = {}
    for p in series["points"]:
        by_year.setdefault(int(p["t"][:4]), []).append(p)

    rows: List[Dict[str, Any]] = []
    for year in sorted(by_year):
        pts = [p for p in by_year[year] if p["value"] is not None]
        observed = len(pts)
        total = len(by_year[year])

        if not pts:
            rows.append({"year": year, "value": None, "min": None, "max": None,
                         "months_observed": 0, "months_total": total,
                         "confidence": 0.0})
            continue

        if series["kind"] == "categorical":
            counts: Dict[str, int] = {}
            for p in pts:
                counts[p["value"]] = counts.get(p["value"], 0) + 1
            modal = max(counts, key=counts.get)
            rows.append({"year": year, "value": modal, "min": None, "max": None,
                         "months_observed": observed, "months_total": total,
                         "confidence": round(sum(p["valid_fraction"] for p in pts) / observed, 3)})
            continue

        # Weight by valid_fraction: a month where 90% of pixels were clear
        # should count for more than one where 20% were.
        weights = [max(0.01, p["valid_fraction"]) for p in pts]
        values = [p["value"] for p in pts]
        mean = sum(v * w for v, w in zip(values, weights)) / sum(weights)

        rows.append({
            "year": year,
            "value": round(mean, 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "months_observed": observed,
            "months_total": total,
            "confidence": round(sum(weights) / len(weights), 3),
        })
    return rows
