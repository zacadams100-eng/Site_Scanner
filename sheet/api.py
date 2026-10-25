"""
Small web wrapper: draw a red line in the browser, get the sheet back.

    uvicorn sheet.api:app --port 8000      →  http://localhost:8000

This is the internal tool for making sheets. It is not the shop: customers
order on the marketing site and never see this page. Do not expose it to
the internet without putting a login in front of it.

The map app in web/ is served from web/dist once built (`npm run build`).
Before that, a plain one-page draw tool in static/ stands in.

CONTOUR_FIXTURES=<folder> reads layers from fixture files instead of the
publishers — for working on the interface offline. Every sheet made that way
is watermarked TEST DATA and the app shows a TEST DATA badge.
"""

import os
import uuid
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from shapely.geometry import mapping

from .fetch import PRESENT, Fetcher, FixtureFetcher, LayerResult, fetch_all
from .geometry import site_from_geojson, to_wgs
from .layers import GROUPS, LAYERS
from .make import make_sheet

JOBS = Path(os.environ.get("CONTOUR_JOBS", "jobs")).resolve()
FIXTURES = os.environ.get("CONTOUR_FIXTURES", "")
DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
MAX_HA = 5_000
app = FastAPI(title="Contour sheet")


class SheetRequest(BaseModel):
    red_line: dict
    title: str
    client_ref: str = ""
    context_m: float = 500


def _fetcher():
    if FIXTURES:
        return FixtureFetcher(Path(FIXTURES))
    return Fetcher(contact=os.environ.get("CONTOUR_CONTACT", ""))


def _map_features(results: List[LayerResult]) -> Dict[str, Any]:
    """What each layer returned, in WGS84, for the map. Simplified to ~2 m:
    enough for the screen, and it keeps a busy 10 km search small."""
    out = {}
    for r in results:
        if r.status != PRESENT or not r.layer.on_map:
            continue
        out[r.layer.id] = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"label": f.label},
             "geometry": mapping(to_wgs(f.geom.simplify(2, preserve_topology=True)))}
            for f in r.features]}
    return out


@app.get("/api/info")
def info():
    return {"test_data": bool(FIXTURES), "max_ha": MAX_HA, "groups": GROUPS}


@app.get("/api/layers")
def layers():
    return [{"id": l.id, "name": l.name, "group": l.group, "search_m": l.search_m,
             "publisher": l.publisher, "on_map": l.on_map, "geom": l.geom,
             "style": {"fill": l.style.fill, "edge": l.style.edge, "alpha": l.style.alpha,
                       "hatched": l.style.hatch is not None}}
            for l in LAYERS]


@app.post("/api/sheet")
def sheet(req: SheetRequest):
    try:
        site = site_from_geojson(req.red_line)
    except Exception as e:
        raise HTTPException(400, f"Red line not usable: {e}")
    if not req.title.strip() or not req.client_ref.strip():
        raise HTTPException(400, "A sheet needs a site title and an order reference.")
    if site.area > MAX_HA * 10_000:
        raise HTTPException(400, f"Red line over {MAX_HA:,} ha — split it up.")
    job = uuid.uuid4().hex[:10]
    results = fetch_all(site, _fetcher())
    rec = make_sheet(site, JOBS / job, req.title, req.client_ref,
                     display_m=req.context_m, results=results)
    rec["job"] = job
    rec["urls"] = {k: f"/files/{job}/{v}" for k, v in rec["files"].items()}
    rec["map"] = _map_features(results)
    return rec


@app.get("/files/{job}/{name}")
def files(job: str, name: str):
    p = (JOBS / job / name).resolve()
    if JOBS not in p.parents or not p.is_file():
        raise HTTPException(404)
    return FileResponse(p, filename=name)


@app.get("/{path:path}", include_in_schema=False)
def index(path: str):
    if DIST.is_dir():
        f = (DIST / path).resolve()
        if path and DIST in f.parents and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
    return HTMLResponse((Path(__file__).parent / "static" / "index.html").read_text())
