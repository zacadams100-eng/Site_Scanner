"""
Site Scanner — Earth Engine backend
------------------------------------
Serves real satellite-derived map tiles and area statistics to the frontend,
so the browser never downloads or processes raw satellite data itself.

Endpoints:
  GET  /                          -> health check
  POST /api/tile/ndvi             -> { tile_url_template } for NDVI in a given year
  POST /api/tile/landcover        -> { tile_url_template } for ESA WorldCover
  POST /api/stats                 -> aggregated stats for a drawn area (polygon)

Run locally:
  pip install -r requirements.txt
  export GOOGLE_APPLICATION_CREDENTIALS_JSON="$(cat service-account-key.json)"
  export EE_PROJECT="your-gcp-project-id"
  uvicorn app:app --reload --port 8000

See README.md for the one-time Earth Engine + service account setup.
"""

import os
import json
import ee
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

from summary import SummaryRequest, generate_summary
from cache import build_cache, cache_key
from geometry import geometry_area_m2

# reduceRegion at scale=10 over a whole county blows past maxPixels or simply
# times out, and Earth Engine reports that as an opaque failure the user reads
# as "the app is broken". Refusing oversized areas with a plain-English message
# is both honest and much cheaper than the quota it saves. Matches the limit
# routes_catalog.py applies to /api/series and /api/cells.
MAX_AREA_HA = 250_000.0

# ---------------------------------------------------------------------------
# Earth Engine auth — uses a service account, NOT a personal Google login.
# This is the piece that has to run server-side; it cannot run in a browser.
# ---------------------------------------------------------------------------
def init_earth_engine():
    key_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    project = os.environ.get("EE_PROJECT")

    if not key_json:
        raise RuntimeError(
            "GOOGLE_APPLICATION_CREDENTIALS_JSON is not set. "
            "Paste the full contents of your service account JSON key into this env var."
        )
    if not project:
        raise RuntimeError("EE_PROJECT is not set — this must be your GCP project ID.")

    key_data = json.loads(key_json)
    credentials = ee.ServiceAccountCredentials(key_data["client_email"], key_data=key_json)
    ee.Initialize(credentials, project=project)


init_earth_engine()

app = FastAPI(title="Site Scanner Earth Engine API")

# In production the browser never calls this service cross-origin: Vercel
# proxies /api/* to Cloud Run, so requests arrive same-origin and CORS is not
# consulted at all. It still matters, because the Cloud Run URL is public and
# --allow-unauthenticated, so a wildcard here is what lets any page on the web
# call this API directly from a visitor's browser and spend our Earth Engine
# quota.
#
# CORS_ALLOW_ORIGINS holds a comma-separated allowlist. Unset means "*", which
# keeps `npm run dev` against a remote backend working; set it on deploy:
#   --set-env-vars CORS_ALLOW_ORIGINS=https://your-app.vercel.app
_origins = os.environ.get("CORS_ALLOW_ORIGINS", "").strip()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins.split(",") if o.strip()] or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class TileRequest(BaseModel):
    year: int
    month: Optional[int] = None  # if omitted, uses the full year as a composite


class StatsRequest(BaseModel):
    year: int
    geometry: dict  # a GeoJSON Polygon, e.g. {"type": "Polygon", "coordinates": [[[lng,lat], ...]]}


# ---------------------------------------------------------------------------
# Helpers — building the actual Earth Engine images
# ---------------------------------------------------------------------------
def sentinel2_composite(year: int, month: Optional[int] = None):
    """Cloud-masked Sentinel-2 median composite for a year (or year+month)."""
    if month:
        start = f"{year}-{month:02d}-01"
        end_month = month + 1 if month < 12 else 1
        end_year = year if month < 12 else year + 1
        end = f"{end_year}-{end_month:02d}-01"
    else:
        start = f"{year}-01-01"
        end = f"{year}-12-31"

    def mask_clouds(img):
        scl = img.select("SCL")
        # SCL classes 8,9,10 are cloud/cirrus/shadow — mask them out
        mask = scl.neq(8).And(scl.neq(9)).And(scl.neq(10))
        return img.updateMask(mask)

    coll = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterDate(start, end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40))
        .map(mask_clouds)
    )
    return coll.median()


def ndvi_image(year: int, month: Optional[int] = None):
    composite = sentinel2_composite(year, month)
    return composite.normalizedDifference(["B8", "B4"]).rename("NDVI")


def landcover_image(year: int):
    """ESA WorldCover only has 2020 and 2021 editions — fall back to nearest."""
    version = "v200" if year >= 2021 else "v100"
    return ee.ImageCollection(f"ESA/WorldCover/{version}").first().select("Map")


def flood_proxy_image():
    """Illustrative flood-risk proxy: JRC surface water occurrence + low elevation.
    This is NOT a substitute for the Environment Agency's flood risk maps —
    use their published flood zone data for anything real."""
    water = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0)
    elevation = ee.Image("USGS/SRTMGL1_003").select("elevation")
    low_lying = elevation.lt(20)  # crude low-elevation flag
    return water.divide(100).add(low_lying.multiply(0.3)).rename("flood_proxy")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
# Earth Engine has compute quotas and reduceRegion is slow over large areas.
# Redrawing the same shape, or stepping the year slider back and forth, would
# otherwise re-run the whole computation each time. Per-process only — see
# cache.py for what that does and doesn't buy.
TILE_CACHE = build_cache()
STATS_CACHE = build_cache()


# Catalogue and time-series routes — shared verbatim with mock_ee_backend.py
# so the two cannot drift. Nothing in there imports Earth Engine; when the real
# data layer lands, routes_catalog._series_for becomes the H3 aggregate query.
from routes_catalog import router as catalog_router  # noqa: E402

app.include_router(catalog_router)

# Swap the generator for real Earth Engine data where we have an implementation
# (NDVI today). Anything not registered keeps returning demo data and says so,
# so the catalogue can go real one factor at a time instead of in one jump.
import routes_catalog  # noqa: E402
import ee_series  # noqa: E402

ee_series.install(routes_catalog.REAL_SERIES, routes_catalog.REAL_SOURCES)

# Public open data — designations, prices, crime, energy performance. Needs no
# credentials, so it is registered here and in the serverless function alike.
# See open_data.py for what each source can and cannot answer.
import open_data  # noqa: E402

open_data.install(routes_catalog.REAL_SERIES, routes_catalog.REAL_SOURCES)


@app.get("/")
def health():
    return {"status": "ok", "message": "Site Scanner Earth Engine API is running"}


@app.get("/api/cache")
def cache_info():
    """Hit/miss counters, so cache behaviour is observable in a deployed
    instance rather than guessed at."""
    return {
        "tiles": TILE_CACHE.info(),
        "stats": STATS_CACHE.info(),
        "series": routes_catalog.SERIES_CACHE.info(),
    }


class PriceRequest(BaseModel):
    postcode_district: str  # e.g. "GU1" — full postcodes are too granular for area stats


@app.post("/api/stats/price")
def price_stats(req: PriceRequest):
    """Real average sale price for a postcode district, from HM Land Registry's
    free, open Price Paid Data — no API key required. This is a separate,
    non-Earth-Engine data source; property prices aren't a satellite dataset."""
    import requests

    district = req.postcode_district.strip().upper()
    query = f"""
    PREFIX ppi: <http://landregistry.data.gov.uk/def/ppi/>
    SELECT (AVG(?amount) AS ?avgPrice) (COUNT(?tx) AS ?count)
    WHERE {{
      ?tx ppi:pricePaid ?amount ;
          ppi:transactionDate ?date ;
          ppi:propertyAddress ?addr .
      ?addr <http://www.w3.org/2000/01/rdf-schema#label> ?label .
      FILTER(STRSTARTS(?label, "{district}"))
      FILTER(?date > "2023-01-01"^^<http://www.w3.org/2001/XMLSchema#date>)
    }}
    """
    try:
        resp = requests.get(
            "https://landregistry.data.gov.uk/landregistry/query",
            params={"query": query, "output": "json"},
            timeout=15,
        )
        resp.raise_for_status()
        bindings = resp.json()["results"]["bindings"]
        if not bindings:
            return {"postcode_district": district, "avg_price": None, "count": 0}
        row = bindings[0]
        return {
            "postcode_district": district,
            "avg_price": float(row["avgPrice"]["value"]) if row.get("avgPrice") else None,
            "count": int(row["count"]["value"]) if row.get("count") else 0,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tile/ndvi")
def tile_ndvi(req: TileRequest):
    try:
        key = cache_key("tile", "ndvi", req.year, req.month)
        cached = TILE_CACHE.get(key)
        if cached is not None:
            return cached

        img = ndvi_image(req.year, req.month)
        vis_params = {"min": -0.1, "max": 0.9, "palette": ["8a6d3d", "c9a758", "7aa854", "2d5c3a"]}
        map_id = ee.Image(img).getMapId(vis_params)
        result = {"tile_url_template": map_id["tile_fetcher"].url_format}
        TILE_CACHE.set(key, result)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tile/landcover")
def tile_landcover(req: TileRequest):
    try:
        key = cache_key("tile", "landcover", req.year, req.month)
        cached = TILE_CACHE.get(key)
        if cached is not None:
            return cached

        img = landcover_image(req.year)
        # ESA WorldCover has a built-in palette in its metadata; a simple generic
        # palette is used here for clarity.
        vis_params = {
            "min": 10, "max": 100,
            "palette": [
                "006400", "ffbb22", "ffff4c", "f096ff", "fa0000",
                "b4b4b4", "f0f0f0", "0064c8", "0096a0", "00cf75", "fae6a0",
            ],
        }
        map_id = ee.Image(img).getMapId(vis_params)
        result = {"tile_url_template": map_id["tile_fetcher"].url_format}
        TILE_CACHE.set(key, result)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/stats")
def stats(req: StatsRequest):
    """Server-side aggregation — the browser only ever receives a handful
    of numbers here, never raw imagery or pixel data."""
    # A malformed geometry keeps its existing contract (a 500 from the
    # ee.Geometry call below, mirrored by the mock) — only the size check is
    # new, and it has to not change the shape of any other failure.
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
        key = cache_key("stats", req.year, req.geometry)
        cached = STATS_CACHE.get(key)
        if cached is not None:
            return cached

        geom = ee.Geometry(req.geometry)

        ndvi = ndvi_image(req.year)
        ndvi_mean = ndvi.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=geom, scale=10, maxPixels=1e9
        ).get("NDVI")

        lc = landcover_image(req.year)
        lc_hist = lc.reduceRegion(
            reducer=ee.Reducer.frequencyHistogram(), geometry=geom, scale=10, maxPixels=1e9
        ).get("Map")

        flood = flood_proxy_image()
        flood_mean = flood.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=geom, scale=30, maxPixels=1e9
        ).get("flood_proxy")

        area_ha = geom.area().divide(10000)

        result = ee.Dictionary({
            "ndvi_mean": ndvi_mean,
            "landcover_histogram": lc_hist,
            "flood_proxy_mean": flood_mean,
            "area_ha": area_ha,
        }).getInfo()

        STATS_CACHE.set(key, result)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/summary")
def summary(req: SummaryRequest):
    """Writes the report panel's one-paragraph site note. Not Earth Engine —
    this takes the already-computed figures and turns them into prose.

    The Anthropic API key stays server-side; see summary.py. With no key set,
    a deterministic paragraph is returned instead of failing.
    """
    try:
        return generate_summary(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
