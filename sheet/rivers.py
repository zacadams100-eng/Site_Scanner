"""
Names for main rivers.

The Environment Agency's main river service carries no names (only STATUS
and LENGTH_KM), so a sheet could only say "Main river, 577 m S". OS Open
Rivers names its watercourses and is free under the OGL. Each main river
line takes the name of the OS watercourse it runs along.

OS Open Rivers is a national download, read from a local GeoPackage:

    scripts/get_open_rivers.sh            # once; about 100 MB
    export CONTOUR_OPEN_RIVERS=data/oprvrs_gb.gpkg

Without the file, rivers stay "Main river": nothing breaks, nothing is guessed.
"""

import os
from pathlib import Path
from typing import List, Optional

from shapely.geometry.base import BaseGeometry

MATCH_M = 25          # how close an OS watercourse must run to the EA line
MIN_SHARE = 0.3       # and along how much of its length (or 50 m, if less)


def open_rivers_path() -> Optional[Path]:
    p = os.environ.get("CONTOUR_OPEN_RIVERS", "")
    return Path(p) if p and Path(p).is_file() else None


def _name_column(cols) -> Optional[str]:
    lower = {c.lower(): c for c in cols}
    for want in ("name1", "watercourse_name", "name"):
        if want in lower:
            return lower[want]
    return None


def name_main_rivers(results, area: BaseGeometry, path: Optional[Path] = None) -> int:
    """Rename main river features from OS Open Rivers. Returns how many were named."""
    path = path or open_rivers_path()
    r = next((x for x in results if x.layer.id == "main_river" and x.features), None)
    if not path or r is None:
        return 0
    import geopandas as gpd
    import pyogrio
    layer = next((n for n, _ in pyogrio.list_layers(path) if "link" in n.lower()), None)
    os_links = gpd.read_file(path, layer=layer, bbox=tuple(area.buffer(MATCH_M).bounds))
    col = _name_column(os_links.columns)
    if os_links.empty or not col:
        return 0
    os_links = os_links[os_links[col].notna() & (os_links[col].astype(str).str.strip() != "")]
    named = 0
    for f in r.features:
        zone = f.geom.buffer(MATCH_M)
        best, best_len = None, 0.0
        for name, geom in zip(os_links[col], os_links.geometry):
            share = geom.intersection(zone).length
            if share > best_len:
                best, best_len = str(name).strip(), share
        # Running alongside for a real stretch, not just crossing at a confluence.
        if best and best_len >= min(MIN_SHARE * f.geom.length, 50):
            f.label = best
            named += 1
    return named
