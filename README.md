# Site Scanner — Earth Engine Backend

This is the real data layer behind the Site Scanner demo. It talks to Google
Earth Engine on the server side and hands your frontend either a **tile URL**
(for the map) or a small **JSON of stats** (for the report panel) — never raw
satellite files. Nothing is downloaded by the user's browser.

I could not run or test this against live Earth Engine from within this
sandbox (no network access to Google's servers here), so treat the code as
correct-by-construction from the Earth Engine Python API docs, not
guaranteed to run first try. Budget an afternoon for debugging auth and
quota issues — that's normal for a first Earth Engine integration.

## 1. One-time setup (do this once)

1. **Sign up for Earth Engine** at https://code.earthengine.google.com if you
   haven't already (free, but requires approval — usually near-instant for
   .ac.uk student emails).
2. **Create a Google Cloud project** at https://console.cloud.google.com
   (or reuse one) and enable the **Earth Engine API** for it.
3. **Create a service account**:
   - Console → IAM & Admin → Service Accounts → Create Service Account.
   - Grant it the "Earth Engine Resource Viewer" role (or Editor while testing).
   - Create a JSON key for it and download it. Keep this file secret — never
     commit it to a public repo.
4. **Register the service account with Earth Engine**:
   - Go to https://signup.earthengine.google.com/#!/service_accounts
   - Add the service account's email (found in the JSON key as `client_email`).

## 2. Running locally

```bash
cd ee-backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

export GOOGLE_APPLICATION_CREDENTIALS_JSON="$(cat /path/to/service-account-key.json)"
export EE_PROJECT="your-gcp-project-id"

uvicorn app:app --reload --port 8000
```

Visit http://localhost:8000 — you should see `{"status": "ok", ...}`.

## Running without Earth Engine credentials (mock backend)

`mock_ee_backend.py` is a stand-in for `app.py` that needs no service account,
no GCP project and no network access to Google. Use it to build and verify the
frontend while Earth Engine setup happens in parallel.

```bash
pip install -r requirements.txt      # no extra dependencies needed
uvicorn mock_ee_backend:app --reload --port 8000
```

It serves the same routes, request bodies, response keys and error codes as
`app.py`. The differences are deliberate and limited to two things:

- **Tile URLs point at real public XYZ basemaps** (Esri World Imagery for
  `/api/tile/ndvi`, OpenStreetMap for `/api/tile/landcover`) instead of
  `earthengine.googleapis.com`, so `L.tileLayer(tile_url_template)` genuinely
  renders something.
- **Statistics are generated**, but deterministically per `(year, area)` and
  within plausible UK ranges — the same drawn shape always returns the same
  numbers, so the report panel doesn't flicker between reloads. `area_ha` is a
  real geodesic area of the polygon you send, so it tracks what was drawn.

`landcover_histogram` deliberately reproduces Earth Engine's actual shape:
string class codes mapped to **float pixel counts**, with only the classes
present on that site included. Do not assume all eleven keys exist.

Every response carries an `X-Contour-Mock: true` header, so it is always
obvious which backend answered.

| Env var | Effect |
| --- | --- |
| `MOCK_TILE_URL_NDVI` | Override the XYZ template for `/api/tile/ndvi` |
| `MOCK_TILE_URL_LANDCOVER` | Override the XYZ template for `/api/tile/landcover` |
| `MOCK_STATS_ALL_CLASSES=1` | Force all 11 WorldCover classes into every histogram, for exercising legend rendering |
| `MOCK_LATENCY_MS` | Artificial per-request delay, to make loading states visible |

Switching to the real backend is a one-word change — `uvicorn app:app` instead
of `uvicorn mock_ee_backend:app`. The frontend needs no edit.

## 3. Testing the endpoints

```bash
# Get an NDVI tile URL for 2024
curl -X POST http://localhost:8000/api/tile/ndvi \
  -H "Content-Type: application/json" \
  -d '{"year": 2024}'

# Get stats for a small area near Guildford
curl -X POST http://localhost:8000/api/stats \
  -H "Content-Type: application/json" \
  -d '{
    "year": 2024,
    "geometry": {
      "type": "Polygon",
      "coordinates": [[[-0.58, 51.235], [-0.56, 51.235], [-0.56, 51.245], [-0.58, 51.245], [-0.58, 51.235]]]
    }
  }'
```

The tile endpoint should return something like:
```json
{"tile_url_template": "https://earthengine.googleapis.com/v1/projects/.../maps/.../tiles/{z}/{x}/{y}"}
```

That URL template is what a Leaflet tile layer expects directly.

## 4. Wiring it into the existing frontend

Replace the fake `layerGroups['ndvi']` rectangles in the site-scanner demo
with a real Leaflet tile layer:

```javascript
async function loadRealNDVI(year){
  const res = await fetch('http://localhost:8000/api/tile/ndvi', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({year})
  });
  const {tile_url_template} = await res.json();
  if (window.ndviLayer) map.removeLayer(window.ndviLayer);
  window.ndviLayer = L.tileLayer(tile_url_template, {opacity: 0.6}).addTo(map);
}
```

And for the report panel, call `/api/stats` with the drawn shape's GeoJSON
(Leaflet layers can export this via `layer.toGeoJSON()`) instead of running
the local `pointInAOI` loop over simulated fields.

## 5. Important honesty notes

- **Price and solar layers aren't in this backend.** Earth Engine has no UK
  property price dataset — that needs HM Land Registry Price Paid Data or
  the ONS house price index, joined by postcode/area, from a separate
  source. Solar potential is better sourced from the EU's free PVGIS API
  than approximated from Earth Engine.
- **The flood layer here is an illustrative proxy** (surface water history +
  low elevation), not the Environment Agency's actual flood risk maps. For
  anything real, that data should come from the EA's published flood zone
  layers, not be inferred.
- **Free tier limits**: Earth Engine is free for this kind of use but has
  compute quotas. `reduceRegion` on very large areas or many rapid requests
  can hit rate limits — add caching (even a simple in-memory dict keyed by
  year+geometry hash) before you put this in front of real users.

## 6. Deploying so it's not just "localhost"

Google Cloud Run is the natural fit since you're already using Google Cloud
for the service account: containerize this app, deploy to Cloud Run, and
point your frontend's `fetch` calls at the Cloud Run URL instead of
`localhost:8000`. That's the point at which "the site" genuinely never
requires anyone to download anything — it's a live API behind your map.
