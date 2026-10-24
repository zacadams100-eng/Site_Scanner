"""Red line handling: read any boundary, work in British National Grid."""

import math
from pathlib import Path
from typing import Any, Dict, Union

from pyproj import Transformer
from shapely import wkt as shapely_wkt
from shapely.geometry import shape, mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

BNG = "EPSG:27700"
WGS84 = "EPSG:4326"

import threading

import shapely

# pyproj transformers must not be shared between threads; layers are fetched
# in parallel, so each thread gets its own pair.
_local = threading.local()


def _tr(name: str, src: str, dst: str):
    t = getattr(_local, name, None)
    if t is None:
        t = Transformer.from_crs(src, dst, always_xy=True)
        setattr(_local, name, t)
    return t


def _apply(g: BaseGeometry, t) -> BaseGeometry:
    return shapely.transform(g, lambda x, y: t.transform(x, y), interleaved=False)


def to_bng(g: BaseGeometry) -> BaseGeometry:
    return _apply(g, _tr("bng", WGS84, BNG))


def to_wgs(g: BaseGeometry) -> BaseGeometry:
    return _apply(g, _tr("wgs", BNG, WGS84))


def _looks_like_bng(g: BaseGeometry) -> bool:
    minx, miny, maxx, maxy = g.bounds
    return maxx > 180 or maxy > 90 or minx < -180


def site_from_geojson(obj: Dict[str, Any]) -> BaseGeometry:
    """GeoJSON Feature / FeatureCollection / geometry → polygon in BNG.

    Coordinates are taken as WGS84 unless they are obviously grid metres.
    """
    t = obj.get("type")
    if t == "FeatureCollection":
        geoms = [shape(f["geometry"]) for f in obj["features"] if f.get("geometry")]
    elif t == "Feature":
        geoms = [shape(obj["geometry"])]
    else:
        geoms = [shape(obj)]
    g = unary_union(geoms)
    if g.is_empty:
        raise ValueError("The red line is empty.")
    g = g if _looks_like_bng(g) else to_bng(g)
    return _as_area(g)


def site_from_file(path: Union[str, Path]) -> BaseGeometry:
    """Any vector file a client might send: GeoJSON, KML, GeoPackage, zipped shapefile."""
    import geopandas as gpd
    gdf = gpd.read_file(str(path))
    if gdf.empty:
        raise ValueError(f"No features in {path}")
    if gdf.crs is None:
        g = unary_union(gdf.geometry)
        g = g if _looks_like_bng(g) else to_bng(g)
    else:
        g = unary_union(gdf.to_crs(BNG).geometry)
    return _as_area(g)


def _as_area(g: BaseGeometry) -> BaseGeometry:
    if g.geom_type in ("LineString", "MultiLineString"):
        # A closed line drawn as a line (common from CAD) — close it.
        from shapely.ops import polygonize
        polys = list(polygonize(g))
        if not polys:
            raise ValueError("The red line is a line that does not close into an area.")
        g = unary_union(polys)
    if g.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError(f"The red line must be an area, got {g.geom_type}.")
    if not g.is_valid:
        g = g.buffer(0)
    return g


def search_area(site: BaseGeometry, radius_m: float) -> BaseGeometry:
    """Site plus radius, in BNG. Radius 0 means the red line itself."""
    return site.buffer(radius_m, quad_segs=8) if radius_m > 0 else site


def query_wkt(area_bng: BaseGeometry) -> str:
    """Short WGS84 WKT for URL queries — simplified so the URL stays small."""
    g = area_bng.simplify(5) if area_bng.length > 0 else area_bng
    g = to_wgs(g.convex_hull if len(shapely_wkt.dumps(g)) > 6000 else g)
    return shapely_wkt.dumps(g, rounding_precision=6)


def bearing_word(site: BaseGeometry, other: BaseGeometry) -> str:
    """Eight-point compass direction from the site centre to the nearest part."""
    from shapely.ops import nearest_points
    c = site.centroid
    p = nearest_points(c, other)[1]
    dx, dy = p.x - c.x, p.y - c.y
    if abs(dx) < 1 and abs(dy) < 1:
        return ""
    ang = (math.degrees(math.atan2(dx, dy)) + 360) % 360
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int((ang + 22.5) // 45) % 8]


def area_ha(g: BaseGeometry) -> float:
    return g.area / 10_000


def to_geojson_wgs(g: BaseGeometry) -> Dict[str, Any]:
    return mapping(to_wgs(g))
