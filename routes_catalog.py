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


def _series_for(factor_id: str, centroid: tuple, area_ha: float,
                steps: List[str]) -> Dict[str, Any]:
    """The one function that becomes a database query in production."""
    return series_mod.generate_series(factor_id, centroid, area_ha, steps)


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
        s = _series_for(fid, centroid, area_ha, steps)
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
        "steps": steps,
        "series": out,
    }
