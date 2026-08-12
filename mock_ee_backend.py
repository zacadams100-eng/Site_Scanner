"""
Contour — mock Earth Engine backend
-----------------------------------
A drop-in stand-in for app.py that needs no Earth Engine credentials, no GCP
project and no network access to Google. It mirrors app.py's routes, request
models, response keys and error codes exactly, so the frontend's real-data
code path can be exercised and visually verified before Earth Engine is live.

What is faithful to the real backend:
  * identical route paths, HTTP methods and request bodies
  * identical response keys, and identical *types* — in particular
    landcover_histogram uses string keys and float pixel counts, which is what
    ee.Reducer.frequencyHistogram().getInfo() actually returns
  * identical error contract — a bad geometry is a 500 with {"detail": ...},
    a malformed body is FastAPI's usual 422

What is fake:
  * tile URLs point at real public XYZ basemaps (Esri imagery / OSM) rather
    than earthengine.googleapis.com, so tiles genuinely render in Leaflet
  * statistics are generated, but deterministically per (year, area) and
    within plausible UK ranges — the same drawn shape always returns the same
    numbers, so the report panel is stable across reloads

Every response carries an `X-Contour-Mock: true` header. Nothing but the
header distinguishes these payloads from the real ones, which is the point.

Run locally:
  pip install -r requirements.txt
  uvicorn mock_ee_backend:app --reload --port 8000

Environment overrides (all optional):
  MOCK_TILE_URL_NDVI        XYZ template served by /api/tile/ndvi
  MOCK_TILE_URL_LANDCOVER   XYZ template served by /api/tile/landcover
  MOCK_STATS_ALL_CLASSES    "1" forces all 11 WorldCover classes into every
                            histogram (useful for exercising legend rendering;
                            off by default because a UK site never has
                            mangroves or permanent snow)
  MOCK_LATENCY_MS           artificial delay per request, to make loading
                            states visible in the UI
"""

import asyncio
import hashlib
import math
import os
import random
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from summary import SummaryRequest, generate_summary

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Real, public, key-free XYZ sources. Leaflet substitutes the named
# placeholders, so the {z}/{y}/{x} ordering Esri uses is handled for us.
DEFAULT_TILE_URL_NDVI = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
)
DEFAULT_TILE_URL_LANDCOVER = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"


def _tile_url(layer: str) -> str:
    if layer == "ndvi":
        return os.environ.get("MOCK_TILE_URL_NDVI", DEFAULT_TILE_URL_NDVI)
    return os.environ.get("MOCK_TILE_URL_LANDCOVER", DEFAULT_TILE_URL_LANDCOVER)


def _all_classes_forced() -> bool:
    return os.environ.get("MOCK_STATS_ALL_CLASSES", "").strip() == "1"


def _latency_seconds() -> float:
    try:
        return max(0.0, float(os.environ.get("MOCK_LATENCY_MS", "0"))) / 1000.0
    except ValueError:
        return 0.0


# ESA WorldCover v100/v200 class codes, with the weight each is given when
# generating a histogram for a UK site. Codes are the real ones; the weights
# are what keeps the output plausible for lowland England rather than uniform
# nonsense. Snow (70), mangroves (95) and moss/lichen (100) are weighted to
# zero — they exist in the table so the full code set is representable via
# MOCK_STATS_ALL_CLASSES, not because a Surrey field will ever return them.
WORLDCOVER_CLASSES: Dict[int, Dict[str, Any]] = {
    10: {"label": "Tree cover", "weight": 3.0},
    20: {"label": "Shrubland", "weight": 0.8},
    30: {"label": "Grassland", "weight": 5.0},
    40: {"label": "Cropland", "weight": 4.5},
    50: {"label": "Built-up", "weight": 2.0},
    60: {"label": "Bare / sparse vegetation", "weight": 0.3},
    70: {"label": "Snow and ice", "weight": 0.0},
    80: {"label": "Permanent water bodies", "weight": 0.6},
    90: {"label": "Herbaceous wetland", "weight": 0.4},
    95: {"label": "Mangroves", "weight": 0.0},
    100: {"label": "Moss and lichen", "weight": 0.0},
}

WORLDCOVER_CODES: List[int] = sorted(WORLDCOVER_CLASSES)

# WorldCover is a 10 m product, so one pixel covers 100 m².
WORLDCOVER_PIXEL_AREA_M2 = 100.0

EARTH_RADIUS_M = 6378137.0


# ---------------------------------------------------------------------------
# Request models — byte-for-byte the same as app.py's
# ---------------------------------------------------------------------------
class TileRequest(BaseModel):
    year: int
    month: Optional[int] = None


class StatsRequest(BaseModel):
    year: int
    geometry: dict


class PriceRequest(BaseModel):
    postcode_district: str


# ---------------------------------------------------------------------------
# Geometry — a real geodesic area, so area_ha actually tracks what was drawn.
# Lives in geometry.py so production routes can use it without importing the
# mock; re-exported here because tests and endpoints below refer to it.
# ---------------------------------------------------------------------------
from geometry import (  # noqa: E402,F401
    _ring_area_m2,
    _polygon_area_m2,
    geometry_area_m2,
    geometry_centroid,
)


# ---------------------------------------------------------------------------
# Deterministic generation
# ---------------------------------------------------------------------------
def _seeded_rng(*parts: Any) -> random.Random:
    """Stable across processes and runs — unlike hash(), which is salted."""
    key = "|".join(str(p) for p in parts).encode("utf-8")
    seed = int.from_bytes(hashlib.sha256(key).digest()[:8], "big")
    return random.Random(seed)


def make_landcover_histogram(rng: random.Random, area_m2: float) -> Dict[str, float]:
    """A frequencyHistogram-shaped dict: string codes -> float pixel counts.

    Only classes actually present are returned, which is what Earth Engine
    does — the frontend must not assume all 11 keys exist.
    """
    total_pixels = max(1.0, area_m2 / WORLDCOVER_PIXEL_AREA_M2)

    force_all = _all_classes_forced()
    weights: Dict[int, float] = {}
    for code, meta in WORLDCOVER_CLASSES.items():
        weight = meta["weight"]
        if force_all:
            weight = max(weight, 0.25)
        if weight <= 0:
            continue
        # Most sites are a mix of two or three classes, not all of them.
        # The cap stays below 1.0 so that even a dominant class can be absent —
        # a purely wooded or purely built-up site has to be reachable.
        if not force_all and rng.random() > min(0.92, 0.25 + weight / 5.0):
            continue
        weights[code] = weight * rng.uniform(0.4, 1.6)

    if not weights:  # never leave a site with no land cover at all
        weights = {30: 1.0}

    total_weight = sum(weights.values())
    histogram: Dict[str, float] = {}
    for code, weight in sorted(weights.items()):
        pixels = round(total_pixels * (weight / total_weight), 4)
        if pixels > 0:
            histogram[str(code)] = pixels
    return histogram


def _ndvi_from_histogram(rng: random.Random, histogram: Dict[str, float], year: int) -> float:
    """NDVI consistent with the land cover, rather than an unrelated number.

    Per-class annual-median NDVI values in the ranges a Sentinel-2 composite
    over lowland England actually lands in.
    """
    per_class = {
        10: 0.80, 20: 0.62, 30: 0.68, 40: 0.58, 50: 0.24,
        60: 0.16, 70: 0.02, 80: -0.05, 90: 0.55, 95: 0.72, 100: 0.30,
    }
    total = sum(histogram.values()) or 1.0
    ndvi = sum(per_class.get(int(c), 0.5) * p for c, p in histogram.items()) / total
    # A little year-on-year drift plus noise, then clamp to the sensor range.
    ndvi += (year - 2020) * 0.004 + rng.uniform(-0.035, 0.035)
    return round(max(-1.0, min(1.0, ndvi)), 4)


def _flood_proxy(rng: random.Random, histogram: Dict[str, float]) -> float:
    """Mirrors app.py's proxy: surface-water occurrence plus a low-lying flag,
    so the range is 0 .. ~1.3 and most inland sites sit well under 0.5."""
    total = sum(histogram.values()) or 1.0
    water_fraction = (
        histogram.get("80", 0.0) + 0.5 * histogram.get("90", 0.0)
    ) / total
    value = water_fraction * rng.uniform(0.6, 1.0) + rng.uniform(0.0, 0.22)
    if rng.random() < 0.12:  # occasional genuinely low-lying site
        value += 0.25
    return round(max(0.0, min(1.3, value)), 4)


def make_stats(year: int, geometry: dict) -> Dict[str, Any]:
    """The full /api/stats payload. Pure and deterministic — tests call this
    directly, without going through HTTP."""
    area_m2 = geometry_area_m2(geometry)
    lng, lat = geometry_centroid(geometry)
    rng = _seeded_rng(year, round(lng, 4), round(lat, 4), round(area_m2, 1))

    histogram = make_landcover_histogram(rng, area_m2)
    return {
        "ndvi_mean": _ndvi_from_histogram(rng, histogram, year),
        "landcover_histogram": histogram,
        "flood_proxy_mean": _flood_proxy(rng, histogram),
        "area_ha": round(area_m2 / 10000.0, 4),
    }


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Contour Earth Engine API (mock)")

# Public, unauthenticated, and every series call can reach an upstream with a
# shared quota. See ratelimit.py for what this does and does not protect.
import ratelimit  # noqa: E402

ratelimit.install(app)

# Installed after the limiter so it wraps it: a 429 is part of what a client
# experiences and must be timed too. See telemetry.py.
import telemetry  # noqa: E402

telemetry.install(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    # Without this the browser hides X-Contour-Mock from JavaScript, and the
    # frontend can't tell the mock apart from the real backend.
    expose_headers=["X-Contour-Mock"],
)


@app.middleware("http")
async def mark_and_delay(request: Request, call_next):
    delay = _latency_seconds()
    if delay:
        await asyncio.sleep(delay)
    response = await call_next(request)
    response.headers["X-Contour-Mock"] = "true"
    return response


@app.get("/")
def health():
    return {
        "status": "ok",
        "message": "Contour Earth Engine API is running (MOCK — no Earth Engine)",
        "mock": True,
    }


@app.post("/api/tile/ndvi")
def tile_ndvi(req: TileRequest):
    try:
        if req.month is not None and not 1 <= req.month <= 12:
            raise ValueError(f"month must be between 1 and 12, got {req.month}")
        return {"tile_url_template": _tile_url("ndvi")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tile/landcover")
def tile_landcover(req: TileRequest):
    try:
        if req.month is not None and not 1 <= req.month <= 12:
            raise ValueError(f"month must be between 1 and 12, got {req.month}")
        return {"tile_url_template": _tile_url("landcover")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Mirrors app.py: reduceRegion over a county times out rather than returning
# anything useful, so an oversized area is refused with a plain-English reason
# instead of an opaque failure.
MAX_AREA_HA = 250_000.0


@app.post("/api/stats")
def stats(req: StatsRequest):
    # A malformed geometry keeps its existing contract (500), so only the size
    # check is new and it must not reshape any other failure.
    try:
        area_ha = geometry_area_m2(req.geometry) / 10_000.0
    except Exception:
        area_ha = 0.0
    if area_ha > MAX_AREA_HA:
        raise HTTPException(
            status_code=400,
            detail=(
                f"That area is {area_ha:,.0f} ha, above the {MAX_AREA_HA:,.0f} ha "
                "limit for a live query. Earth Engine would time out rather than "
                "return anything useful. Draw a smaller shape — a field or a farm, "
                "not a county."
            ),
        )

    try:
        return make_stats(req.year, req.geometry)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/summary")
def summary(req: SummaryRequest):
    """Identical to app.py's — the summary layer isn't Earth Engine, so the
    mock delegates to exactly the same code the real backend uses."""
    try:
        return generate_summary(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/stats/price")
def price_stats(req: PriceRequest):
    """Stand-in for the HM Land Registry lookup. Not Earth Engine, but the
    frontend may call it, so the mock answers in the same shape."""
    try:
        district = req.postcode_district.strip().upper()
        if not district:
            raise ValueError("postcode_district must not be empty")
        rng = _seeded_rng("price", district)
        return {
            "postcode_district": district,
            "avg_price": round(rng.uniform(240_000, 685_000), 2),
            "count": rng.randint(40, 900),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Catalogue and time-series routes. Shared verbatim with app.py so the two
# backends cannot drift — see routes_catalog.py.
from routes_catalog import router as catalog_router  # noqa: E402

app.include_router(catalog_router)

# The enquiry form's receiver. Mounted on both backends so the
# contact form works on any deployment, and returns 503 rather than
# a false success where no receiver is configured.
from routes_enquiry import router as enquiry_router  # noqa: E402
app.include_router(enquiry_router)

# The mock has no Earth Engine, but open data needs none either: registering it
# here means the credential-free backend — the one that runs locally and in the
# serverless deployment — still returns real designations, prices and crime
# where the network allows, and falls back to generated data where it does not.
if os.environ.get("MOCK_DISABLE_OPEN_DATA") != "1":
    import routes_catalog as _rc                    # noqa: E402
    try:
        import open_data as _open_data              # noqa: E402
        _open_data.install(_rc.REAL_SERIES, _rc.REAL_SOURCES)
    except Exception:                               # pragma: no cover
        # A missing `requests` must not stop the mock backend booting; that is
        # the one thing it exists to guarantee.
        pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
