"""One call from red line to finished files."""

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from shapely.geometry.base import BaseGeometry

from .fetch import Fetcher, LayerResult, fetch_all
from .findings import build_findings, counts
from .layers import LAYER_BY_ID
from .rivers import name_main_rivers
from .geometry import area_ha, search_area, to_geojson_wgs
from .gpkg import write_gpkg
from .render import render_sheet


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:50] or "site"


def make_sheet(site: BaseGeometry, out_dir, title: str, client_ref: str = "",
               fetcher=None, display_m: float = 500, os_key: Optional[str] = None,
               results: Optional[List[LayerResult]] = None, on_done=None) -> Dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    made_at = dt.datetime.now()
    stem = f"{made_at:%Y%m%d}-{slug(title)}"

    # The draw page fetches first so it can put the same features on its map.
    if results is None:
        results = fetch_all(site, fetcher or Fetcher(), on_done=on_done)
    # River names from OS Open Rivers, when the file is present.
    name_main_rivers(results, search_area(site, LAYER_BY_ID["main_river"].search_m))
    findings = build_findings(results, site)

    # When a layer's features come back without a label, keep one example of
    # what the publisher did send, so the right field can go in label_fields.
    unlabelled = {}
    for r in results:
        f = next((f for f in r.features if not f.label or f.label == r.layer.default_label), None)
        if f and r.layer.label_fields:
            unlabelled[r.layer.id] = {k: str(v)[:60] for k, v in f.props.items()}

    pdf = out / f"{stem}.pdf"
    info = render_sheet(pdf, site, results, findings, title, client_ref, display_m, os_key, made_at)
    gpkg = out / f"{stem}.gpkg"
    if gpkg.exists():
        gpkg.unlink()
    write_gpkg(gpkg, site, results)

    record = {
        "title": title,
        "client_ref": client_ref,
        "made_at": made_at.isoformat(timespec="seconds"),
        "area_ha": round(area_ha(site), 3),
        "red_line_wgs84": to_geojson_wgs(site),
        "scale": info["scale"],
        "basemap": info["basemap"],
        "test_data": info["fixture"],
        "counts": counts(findings),
        "findings": [
            {"layer": f.layer_id, "name": f.name, "group": f.group, "status": f.status,
             "search_m": f.search_m, "on_site": f.on_site, "summary": f.summary(max_items=50),
             "error": f.error,
             "unlabelled_fields": unlabelled.get(f.layer_id, {})}
            for f in findings
        ],
        "files": {"pdf": pdf.name, "gpkg": gpkg.name},
    }
    # Kept with every job: what was asked, what each publisher returned, when.
    (out / f"{stem}.json").write_text(json.dumps(record, indent=2))
    record["files"]["json"] = f"{stem}.json"
    return record
