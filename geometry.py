"""
Site Scanner — geodesic geometry helpers
----------------------------------------
Extracted from mock_ee_backend.py so that production routes can use them
without importing the mock. Area is computed on the sphere, not in Web
Mercator, because Mercator overstates area badly with latitude — see
TECHNICAL_PLAN.md 8.3. A hectare figure that silently grows as you move north
is worse than no figure at all.
"""

import math
from typing import Any, List

EARTH_RADIUS_M = 6378137.0


def _ring_area_m2(ring: List[Any]) -> float:
    """Spherical polygon area for a closed linear ring of [lng, lat] pairs."""
    if not isinstance(ring, (list, tuple)) or len(ring) < 4:
        raise ValueError("Linear ring must be a closed list of at least 4 positions")

    total = 0.0
    for i in range(len(ring) - 1):
        p1, p2 = ring[i], ring[i + 1]
        if len(p1) < 2 or len(p2) < 2:
            raise ValueError("Each position must be [longitude, latitude]")
        lon1, lat1 = math.radians(float(p1[0])), math.radians(float(p1[1]))
        lon2, lat2 = math.radians(float(p2[0])), math.radians(float(p2[1]))
        total += (lon2 - lon1) * (2.0 + math.sin(lat1) + math.sin(lat2))
    return abs(total * EARTH_RADIUS_M * EARTH_RADIUS_M / 2.0)


def _polygon_area_m2(rings: List[Any]) -> float:
    """Outer ring minus any holes."""
    if not rings:
        raise ValueError("Polygon has no coordinates")
    area = _ring_area_m2(rings[0])
    for hole in rings[1:]:
        area -= _ring_area_m2(hole)
    return max(0.0, area)


def geometry_area_m2(geometry: dict) -> float:
    """Area of a GeoJSON Polygon or MultiPolygon, in square metres.

    Raises ValueError on anything malformed, which the endpoints turn into the
    same 500 that ee.Geometry() failures produce in app.py.
    """
    if not isinstance(geometry, dict):
        raise ValueError("geometry must be a GeoJSON object")

    geom_type = geometry.get("type")
    coords = geometry.get("coordinates")
    if coords is None:
        raise ValueError("geometry is missing 'coordinates'")

    if geom_type == "Polygon":
        return _polygon_area_m2(coords)
    if geom_type == "MultiPolygon":
        return sum(_polygon_area_m2(poly) for poly in coords)
    raise ValueError(
        f"Unsupported geometry type {geom_type!r} — expected Polygon or MultiPolygon"
    )


def geometry_centroid(geometry: dict) -> tuple:
    """Rough centroid of the first ring — only ever used to seed the RNG."""
    coords = geometry.get("coordinates") or []
    ring = coords[0] if geometry.get("type") == "Polygon" else coords[0][0]
    lngs = [float(p[0]) for p in ring]
    lats = [float(p[1]) for p in ring]
    return (sum(lngs) / len(lngs), sum(lats) / len(lats))
