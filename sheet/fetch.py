"""
Pull each layer live from its publisher.

Every layer ends in exactly one of three states, and the sheet shows which:

  present       — features found within the layer's search radius
  none_found    — the publisher answered, and there was nothing there
  not_assessed  — the query failed, timed out, or the data was unusable

A failure is never reported as "none found". That is the one rule this file
exists to keep (carried over from Site Scanner's "not assessed ≠ clear").
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from .geometry import query_wkt, search_area, to_bng, to_wgs
from .layers import LAYERS, PLANNING_API, Layer

USER_AGENT = "Contour desk-study sheet (contact: set CONTOUR_CONTACT)"
TIMEOUT_S = 40
MAX_PAGES = 25

PRESENT, NONE_FOUND, NOT_ASSESSED = "present", "none_found", "not_assessed"

# Layers published by local authorities are not complete nationally: a council
# that has not uploaded its conservation areas returns nothing, which is not
# the same as there being none. These say so on the sheet.
PARTIAL_COVERAGE = {"Local planning authority", "Responsible authority"}


@dataclass
class Feature:
    geom: BaseGeometry          # British National Grid
    label: str
    props: Dict[str, Any]


@dataclass
class LayerResult:
    layer: Layer
    status: str
    features: List[Feature] = field(default_factory=list)
    error: str = ""
    fixture: bool = False       # True = test data; the sheet is watermarked
    fetched_at: str = ""

    @property
    def partial_coverage(self) -> bool:
        return self.layer.publisher in PARTIAL_COVERAGE


def _label(props: Dict[str, Any], fields: List[str]) -> str:
    for f in fields:
        v = props.get(f)
        if v not in (None, ""):
            return str(v).strip()
    return ""


def _features_from_geojson(fc: Dict[str, Any], layer: Layer, area: BaseGeometry) -> List[Feature]:
    out = []
    for f in fc.get("features", []):
        if not f.get("geometry"):
            continue
        g = shape(f["geometry"])
        if g.is_empty:
            continue
        g = to_bng(g)
        if not g.is_valid:
            g = g.buffer(0)
        if not g.intersects(area):
            continue   # bbox queries over-fetch; keep only what is truly in range
        props = f.get("properties") or {}
        label = _label(props, layer.label_fields)
        out.append(Feature(g, layer.label_template.format(label) if label else "", props))
    return out


class Fetcher:
    """Live fetcher. Swap `session` for a fake in tests."""

    def __init__(self, session: Optional[requests.Session] = None, contact: str = ""):
        self.s = session or requests.Session()
        ua = USER_AGENT if not contact else f"Contour desk-study sheet ({contact})"
        self.s.headers.update({"User-Agent": ua, "Accept": "application/geo+json, application/json"})

    # --- planning.data.gov.uk --------------------------------------------------
    def _planning(self, layer: Layer, area: BaseGeometry) -> Dict[str, Any]:
        feats: List[Dict[str, Any]] = []
        url: Optional[str] = PLANNING_API
        params: Optional[Dict[str, Any]] = {
            "dataset": layer.dataset,
            "geometry": query_wkt(area),
            "geometry_relation": "intersects",
            "limit": 500,
        }
        for _ in range(MAX_PAGES):
            r = self.s.get(url, params=params, timeout=TIMEOUT_S)
            r.raise_for_status()
            fc = r.json()
            if fc.get("type") != "FeatureCollection":
                raise ValueError("planning.data did not return a FeatureCollection")
            feats.extend(fc.get("features", []))
            nxt = (fc.get("links") or {}).get("next")
            if not nxt or not fc.get("features"):
                break
            url, params = nxt, None
            time.sleep(0.2)   # the API asks for polite rate-limiting
        else:
            raise RuntimeError(f"more than {MAX_PAGES} pages — narrow the search")
        return {"type": "FeatureCollection", "features": feats}

    # --- ArcGIS FeatureServer --------------------------------------------------
    def _arcgis(self, layer: Layer, area: BaseGeometry) -> Dict[str, Any]:
        minx, miny, maxx, maxy = to_wgs(area).bounds
        feats: List[Dict[str, Any]] = []
        offset = 0
        for _ in range(MAX_PAGES):
            params = {
                "where": "1=1",
                "geometry": f"{minx},{miny},{maxx},{maxy}",
                "geometryType": "esriGeometryEnvelope",
                "inSR": 4326,
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": "*",
                "outSR": 4326,
                "returnGeometry": "true",
                "resultOffset": offset,
                "resultRecordCount": 1000,
                "f": "geojson",
            }
            r = self.s.get(f"{layer.url}/query", params=params, timeout=TIMEOUT_S)
            r.raise_for_status()
            fc = r.json()
            if "error" in fc:
                raise RuntimeError(f"ArcGIS error: {fc['error'].get('message', fc['error'])}")
            page = fc.get("features", [])
            feats.extend(page)
            more = fc.get("exceededTransferLimit") or (fc.get("properties") or {}).get("exceededTransferLimit")
            if not more or not page:
                break
            offset += len(page)
        else:
            raise RuntimeError(f"more than {MAX_PAGES} pages — narrow the search")
        return {"type": "FeatureCollection", "features": feats}

    def fetch(self, layer: Layer, site: BaseGeometry) -> LayerResult:
        area = search_area(site, layer.search_m)
        stamp = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
        try:
            fc = self._planning(layer, area) if layer.source == "planning" else self._arcgis(layer, area)
            feats = _features_from_geojson(fc, layer, area)
        except Exception as e:  # any failure is NOT ASSESSED, never "clear"
            return LayerResult(layer, NOT_ASSESSED, error=f"{type(e).__name__}: {e}"[:300], fetched_at=stamp)
        return LayerResult(layer, PRESENT if feats else NONE_FOUND, feats, fetched_at=stamp)


class FixtureFetcher:
    """Reads <layer_id>.geojson (WGS84) from a folder instead of the network.

    For tests and demos only. Every result is flagged, and the sheet carries a
    TEST DATA watermark — fixture data may never pass as a real finding.
    A missing file means the layer is NOT ASSESSED, not clear.
    """

    def __init__(self, folder: Path):
        self.folder = Path(folder)

    def fetch(self, layer: Layer, site: BaseGeometry) -> LayerResult:
        p = self.folder / f"{layer.id}.geojson"
        if not p.exists():
            return LayerResult(layer, NOT_ASSESSED, error="no fixture file", fixture=True)
        area = search_area(site, layer.search_m)
        feats = _features_from_geojson(json.loads(p.read_text()), layer, area)
        return LayerResult(layer, PRESENT if feats else NONE_FOUND, feats, fixture=True,
                           fetched_at="fixture")


def fetch_all(site: BaseGeometry, fetcher=None, layers=None, workers: int = 6) -> List[LayerResult]:
    """All layers, a few at a time. Order follows the layer list."""
    fetcher = fetcher or Fetcher()
    layers = layers or LAYERS
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda l: fetcher.fetch(l, site), layers))
