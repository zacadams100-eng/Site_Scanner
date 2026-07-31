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

# Allow the frontend (served from anywhere during development) to call this API.
# Lock this down to your real domain before going live.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
@app.get("/")
def health():
    return {"status": "ok", "message": "Site Scanner Earth Engine API is running"}


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
        img = ndvi_image(req.year, req.month)
        vis_params = {"min": -0.1, "max": 0.9, "palette": ["8a6d3d", "c9a758", "7aa854", "2d5c3a"]}
        map_id = ee.Image(img).getMapId(vis_params)
        return {"tile_url_template": map_id["tile_fetcher"].url_format}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tile/landcover")
def tile_landcover(req: TileRequest):
    try:
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
        return {"tile_url_template": map_id["tile_fetcher"].url_format}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/stats")
def stats(req: StatsRequest):
    """Server-side aggregation — the browser only ever receives a handful
    of numbers here, never raw imagery or pixel data."""
    try:
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

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
