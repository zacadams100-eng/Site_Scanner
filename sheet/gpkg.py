"""
GeoPackage export in British National Grid, styled for QGIS.

One table per layer that returned features, plus the red line and the
search rings. Styles go in the `layer_styles` table QGIS reads on open, so
the client sees the same colours as the PDF. ArcGIS Pro opens the data
(it ignores QGIS styles).
"""

import sqlite3
from typing import List
from xml.sax.saxutils import quoteattr

import geopandas as gpd
from shapely.geometry import LineString
from shapely.geometry.base import BaseGeometry

from .fetch import PRESENT, LayerResult
from .geometry import BNG, search_area

HATCH_TO_QGIS = {None: "solid", "///": "f_diagonal", "//": "f_diagonal", "\\\\\\": "b_diagonal",
                 "\\\\": "b_diagonal", "xx": "diagonal_x", "++": "cross", "..": "dense6",
                 "oo": "dense5", "--": "horizontal"}
MARKER_TO_QGIS = {"o": "circle", "^": "triangle", "s": "square"}


def _rgba(hex_: str, alpha: float = 1.0) -> str:
    if hex_ == "none":
        return "0,0,0,0"
    h = hex_.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"{r},{g},{b},{int(round(alpha * 255))}"


def _opt(name, value):
    return f'<Option type="QString" name="{name}" value={quoteattr(str(value))}/>'


def qml(style, kind: str) -> str:
    if kind == "line":
        sym_type, cls = "line", "SimpleLine"
        opts = [_opt("line_color", _rgba(style.edge)), _opt("line_width", round(style.width * 0.3528, 2)),
                _opt("line_width_unit", "MM"), _opt("line_style", "solid")]
    elif kind == "point":
        sym_type, cls = "marker", "SimpleMarker"
        opts = [_opt("name", MARKER_TO_QGIS.get(style.marker, "circle")), _opt("color", _rgba(style.fill)),
                _opt("outline_color", _rgba(style.edge)), _opt("size", 2.2), _opt("size_unit", "MM")]
    else:
        sym_type, cls = "fill", "SimpleFill"
        has_fill = style.fill != "none"
        pattern = HATCH_TO_QGIS.get(style.hatch, "solid") if style.hatch else ("solid" if has_fill else "no")
        colour = _rgba(style.fill, style.alpha) if has_fill and not style.hatch else _rgba(style.edge, 0.8)
        opts = [_opt("color", colour if pattern != "no" else "0,0,0,0"), _opt("style", pattern),
                _opt("outline_color", _rgba(style.edge)),
                _opt("outline_width", round(style.width * 0.3528, 2)), _opt("outline_width_unit", "MM"),
                _opt("outline_style", "solid")]
    return (
        '<!DOCTYPE qgis PUBLIC \'http://mrcc.com/qgis.dtd\' \'SYSTEM\'>'
        '<qgis version="3.28.0" styleCategories="Symbology">'
        '<renderer-v2 type="singleSymbol" forceraster="0" symbollevels="0" enableorderby="0">'
        f'<symbols><symbol type="{sym_type}" name="0" alpha="1" clip_to_extent="1" force_rhr="0">'
        f'<layer class="{cls}" enabled="1" pass="0" locked="0"><Option type="Map">{"".join(opts)}</Option></layer>'
        '</symbol></symbols></renderer-v2></qgis>'
    )


def _as_lines(b):
    from shapely.geometry import MultiLineString
    parts = [b] if b.geom_type in ("LineString", "LinearRing") else list(b.geoms)
    return MultiLineString([LineString(p.coords) for p in parts])


def write_gpkg(path, site: BaseGeometry, results: List[LayerResult]) -> List[str]:
    from .layers import Style
    written = []
    styles = []

    def _write(name, gdf, style, kind):
        gdf.to_file(path, layer=name, driver="GPKG", engine="pyogrio")
        written.append(name)
        styles.append((name, qml(style, kind)))

    # red line and rings
    _write("red_line", gpd.GeoDataFrame({"name": ["Red line"], "area_ha": [round(site.area / 1e4, 3)]},
                                        geometry=[site], crs=BNG),
           Style("none", "#e41a1c", None, 0.0, 1.6), "polygon")
    # LineString, not LinearRing: GDAL has no LinearRing layer type (it crashes on one).
    rings = [_as_lines(search_area(site, d).boundary) for d in (1000, 2000)]
    _write("search_rings", gpd.GeoDataFrame({"distance_m": [1000, 2000]}, geometry=rings, crs=BNG),
           Style("none", "#1c1f1d", None, 0.0, 0.5), "line")

    for r in results:
        if r.status != PRESENT:
            continue
        rows = []
        for f in r.features:
            rows.append({"label": f.label, "layer": r.layer.name, "publisher": r.layer.publisher,
                         "distance_m": round(site.distance(f.geom), 1),
                         "within_red_line": site.intersects(f.geom), "geometry": f.geom})
        gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=BNG)
        _write(r.layer.id, gdf, r.layer.style, r.layer.geom)

    _add_styles(path, styles)
    return written


def _add_styles(path, styles):
    con = sqlite3.connect(path)
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS layer_styles (
            id INTEGER PRIMARY KEY AUTOINCREMENT, f_table_catalog TEXT(256), f_table_schema TEXT(256),
            f_table_name TEXT(256), f_geometry_column TEXT(256), styleName TEXT(30), styleQML TEXT,
            styleSLD TEXT, useAsDefault BOOLEAN, description TEXT, owner TEXT(30), ui TEXT(30),
            update_time DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        con.execute("""INSERT OR IGNORE INTO gpkg_contents (table_name, data_type, identifier)
                       VALUES ('layer_styles', 'attributes', 'layer_styles')""")
        for name, q in styles:
            geom_col = con.execute("SELECT column_name FROM gpkg_geometry_columns WHERE table_name=?",
                                   (name,)).fetchone()[0]
            con.execute("""INSERT INTO layer_styles (f_table_catalog, f_table_schema, f_table_name,
                           f_geometry_column, styleName, styleQML, styleSLD, useAsDefault, description, owner)
                           VALUES ('', '', ?, ?, ?, ?, '', 1, 'Contour sheet style', '')""",
                        (name, geom_col, name, q))
        con.commit()
    finally:
        con.close()
