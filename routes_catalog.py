"""
Site Scanner — catalogue and time-series routes
-----------------------------------------------
Mounted by *both* `app.py` and `mock_ee_backend.py`, so the two backends stay
in parity by construction rather than by discipline. Nothing in here imports
Earth Engine.

When the real data layer lands, exactly one function changes:
`_series_for` stops calling `series.generate_series` and starts issuing the H3
aggregate query from TECHNICAL_PLAN.md §3.4. The routes, request bodies and
response shapes below are the contract the frontend is built against, and they
do not move.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import time

import redaction

import catalog
import series as series_mod

router = APIRouter()

# Drawing outside the covered area should fail with an explanation, not return
# plausible-looking nonsense for a field in France.
_BBOX = catalog.ENGLAND_BBOX

# An AOI larger than this is refused on the interactive path. See
# TECHNICAL_PLAN.md §8.8 — nothing otherwise stops a user rectangle-selecting
# the whole country and taking the service down with them.
MAX_AREA_HA = 250_000.0


class SeriesRequest(BaseModel):
    geometry: dict
    factor_ids: List[str] = Field(..., min_length=1, max_length=24)
    start: Optional[str] = None          # 'YYYY-MM'
    end: Optional[str] = None


@router.get("/api/catalog")
def get_catalog() -> Dict[str, Any]:
    """Everything the UI needs to render the factor browser, with provenance
    attached. The frontend never hard-codes a factor list."""
    return {
        "factors": catalog.FACTORS,
        "bases": catalog.BASES,
        "groups": catalog.GROUPS,
        "class_values": catalog.CLASS_VALUES,
        "summary": catalog.catalogue_summary(),
        "coverage": {"name": "England", "bbox": _BBOX},
        "time": {
            "start": catalog.TIME_START,
            "end": catalog.TIME_END,
            "steps": series_mod.month_steps(),
        },
    }


def _validate_geometry(geometry: dict) -> tuple:
    """Returns (centroid, area_ha). Raises ValueError with a message a
    non-technical user can act on."""
    from mock_ee_backend import geometry_area_m2, geometry_centroid

    area_ha = geometry_area_m2(geometry) / 10_000.0
    if area_ha <= 0:
        raise ValueError("That shape has no area — try drawing it again.")
    if area_ha > MAX_AREA_HA:
        raise ValueError(
            f"That area is {area_ha:,.0f} ha, which is larger than the "
            f"{MAX_AREA_HA:,.0f} ha interactive limit. Draw something smaller, "
            "or save it as a project to run in the background."
        )

    lng, lat = geometry_centroid(geometry)
    if not (_BBOX["west"] <= lng <= _BBOX["east"]
            and _BBOX["south"] <= lat <= _BBOX["north"]):
        raise ValueError(
            "That area is outside England. Site Scanner only covers England "
            "at the moment."
        )
    return (lng, lat), area_ha


# Real data sources, keyed by factor id. Empty by default, which is what keeps
# this module free of any Earth Engine import and lets mock_ee_backend.py run
# with no credentials. app.py fills it in at startup via ee_series.install().
#
# A factor present here returns real observations; everything else falls back
# to the generator. Both are labelled in the response, so a half-real
# catalogue is honest rather than confusing.
REAL_SERIES: Dict[str, Any] = {}


def _series_for(factor_id: str, geometry: dict, centroid: tuple, area_ha: float,
                steps: List[str]) -> Dict[str, Any]:
    """Real data where we have it, generated where we don't.

    A failure in the real path falls back to the generator rather than failing
    the whole request — one flaky Earth Engine call should not blank a report
    that has eleven other factors in it. The fallback is recorded in `source`
    and `error`, never hidden.
    """
    fn = REAL_SERIES.get(factor_id)
    if fn is not None:
        t0 = time.perf_counter()
        try:
            points = fn(geometry, steps, area_ha)
            f = catalog.FACTOR_BY_ID[factor_id]
            return {
                "factor_id": factor_id,
                "kind": f["kind"],
                "cadence": f["cadence"],
                "unit": f["unit"],
                "points": points,
                "source": "earth-engine",
                "elapsed_ms": round((time.perf_counter() - t0) * 1000),
            }
        except Exception as e:
            s = series_mod.generate_series(factor_id, centroid, area_ha, steps)
            s["source"] = "generated"
            # Never format the raw exception into a response. Earth Engine
            # puts the credentials dict into some of its error messages, and
            # this string is served straight to the browser.
            s["error"] = ("Earth Engine failed, showing demo data: "
                          + redaction.safe_message(e))
            s["elapsed_ms"] = round((time.perf_counter() - t0) * 1000)
            return s

    s = series_mod.generate_series(factor_id, centroid, area_ha, steps)
    s["source"] = "generated"
    s["elapsed_ms"] = 0
    return s


class CellsRequest(BaseModel):
    geometry: dict
    resolution: int = Field(12, ge=4, le=28)


@router.post("/api/cells")
def get_cells(req: CellsRequest) -> Dict[str, Any]:
    """A grid of cells covering the AOI, each carrying a stable `offset`.

    This is the shape of the H3 aggregate tier (TECHNICAL_PLAN.md §3.4) in
    miniature. Production returns real per-cell values per timestep; here each
    cell returns a fixed deviation from the area mean, and the client renders
    `cell_value = series_mean(t) + offset * spread`.

    The reason for handing back an offset rather than 180 timesteps of values
    per cell is the whole point of the fast tier: one small payload at draw
    time means scrubbing the timeline repaints from memory at 60 fps instead
    of asking the server for anything. The approximation is that within-area
    spatial *pattern* is treated as stable over time while the *level* moves —
    which is right for terrain and roughly right for land cover, and is why
    the result carries `precision: "approx"` until the exact pass lands.
    """
    try:
        centroid, area_ha = _validate_geometry(req.geometry)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    import hashlib

    ring = (req.geometry["coordinates"][0] if req.geometry["type"] == "Polygon"
            else req.geometry["coordinates"][0][0])
    lngs = [float(p[0]) for p in ring]
    lats = [float(p[1]) for p in ring]
    west, east = min(lngs), max(lngs)
    south, north = min(lats), max(lats)

    n = req.resolution
    dx = (east - west) / n
    dy = (north - south) / n

    cells: List[Dict[str, Any]] = []
    for j in range(n):
        for i in range(n):
            w, e = west + i * dx, west + (i + 1) * dx
            s, nn = south + j * dy, south + (j + 1) * dy
            cx, cy = (w + e) / 2, (s + nn) / 2
            if not _point_in_ring(cx, cy, ring):
                continue
            key = f"{round(cx,5)}|{round(cy,5)}".encode()
            h = int.from_bytes(hashlib.sha256(key).digest()[:4], "big") / 2**32
            # Smooth the field a little so neighbouring cells relate to each
            # other, rather than looking like television static.
            h2 = int.from_bytes(hashlib.sha256(key + b"s").digest()[:4], "big") / 2**32
            cells.append({
                "id": f"{i}-{j}",
                "bbox": [round(w, 6), round(s, 6), round(e, 6), round(nn, 6)],
                "offset": round((0.65 * h + 0.35 * h2) * 2 - 1, 4),
            })

    return {"cells": cells, "area_ha": round(area_ha, 2),
            "centroid": {"lng": centroid[0], "lat": centroid[1]}}


def _point_in_ring(x: float, y: float, ring: List[Any]) -> bool:
    """Ray casting. Used to clip the grid to the drawn shape so a freehand
    outline doesn't come back as its bounding box."""
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


@router.post("/api/series")
def get_series(req: SeriesRequest) -> Dict[str, Any]:
    """Monthly series plus the annual rollup, for every requested factor.

    Both are returned in one round trip on purpose: the charts want monthly,
    the attribute table wants annual (decision 5), and making the client fetch
    them separately guarantees they eventually disagree.
    """
    unknown = [f for f in req.factor_ids if f not in catalog.FACTOR_BY_ID]
    if unknown:
        raise HTTPException(status_code=422,
                            detail=f"Unknown factor(s): {', '.join(unknown)}")
    try:
        centroid, area_ha = _validate_geometry(req.geometry)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    steps = series_mod.month_steps(req.start or catalog.TIME_START,
                                   req.end or catalog.TIME_END)

    out: Dict[str, Any] = {}
    for fid in req.factor_ids:
        s = _series_for(fid, req.geometry, centroid, area_ha, steps)
        s["annual"] = series_mod.annual_rollup(s)
        s["meta"] = catalog.resolve(fid)
        out[fid] = s

    return {
        "area_ha": round(area_ha, 2),
        "centroid": {"lng": round(centroid[0], 5), "lat": round(centroid[1], 5)},
        # The frontend badges results with this. Today everything is 'approx';
        # once the exact COG path exists, the refine pass returns 'exact' and
        # the badge flips. Building the field in now means the UI never has to
        # be retrofitted for it.
        "precision": "approx",
        # Which factors came back real, so the UI can say so per column rather
        # than implying the whole report is one thing or the other.
        "real_factors": [k for k, v in out.items() if v.get("source") == "earth-engine"],
        "steps": steps,
        "series": out,
    }
