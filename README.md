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

## The web app (`web/`)

The React frontend that replaces `site-scanner.html`. Vite + TypeScript +
MapLibre, talking to whichever backend is on port 8000.

```bash
# terminal 1 — the API
uvicorn mock_ee_backend:app --reload --port 8000

# terminal 2 — the frontend
cd web
npm install
npm run dev          # http://localhost:5173
```

Vite proxies `/api` to `127.0.0.1:8000`, so the same build works against a
deployed API without an edit.

What it does today:

- **Draw** a rectangle, circle or freehand shape. Freehand is simplified with
  Douglas-Peucker on release and repaired if it self-intersects, so a scribble
  does not become a 600-vertex polygon that slows every later call.
- **Scrub** 180 monthly steps from 2011 to 2025. The timeline draws the area's
  whole series inside its own track, with a data-availability strip beneath —
  it is a chart you can already read before you touch it. Scrubbing repaints
  the map from memory and issues no requests.
- **Read** an attribute table of one row per year, each expandable into its
  twelve months. Copy pastes as TSV straight into Excel; CSV downloads.
- **See** up to four charts chosen automatically from the selected factors,
  grouped so that two different units never share an axis.
- **Check** every number's source, resolution and licence under Sources.

Keyboard: `←`/`→` step a month, `PgUp`/`PgDn` a year, `Home`/`End` jump to the
ends, `space` plays. The timeline is a real `<input type="range">` underneath
the custom rendering, so screen readers and touch work without reimplementation.

### The data layer

`catalog.py` holds 118 factors resolving to 20 base datasets, only 7 of which
need monthly storage. That split is the point: slope, aspect, ruggedness and
height-above-drainage all come off one elevation raster, and NDVI, NDWI, EVI
and SAVI off the same two Sentinel-2 bands. A factor marked `derived` is
arithmetic applied at read time and costs nothing to store — which is what
makes a 100+ factor catalogue affordable at England scale.

`series.py` generates the monthly series. Optical factors return `null` in
months with too few usable pixels rather than an interpolated guess, and every
point carries a `valid_fraction` so the UI can grey out a number built from a
handful of clear pixels.

`routes_catalog.py` is mounted by **both** `app.py` and `mock_ee_backend.py`,
so the two cannot drift. When the real data layer lands, one function changes:
`_series_for` stops calling the generator and starts issuing the H3 aggregate
query described in `TECHNICAL_PLAN.md` §3.4.

See `TECHNICAL_PLAN.md` for the full architecture, the storage cost arithmetic
and the challenges worth knowing about early.

## Running the test suite

```bash
pip install -r requirements-dev.txt
pytest
```

No credentials, no network, no Earth Engine. `tests/conftest.py` installs a
stand-in `ee` module into `sys.modules` before `app.py` is imported, and serves
`mock_ee_backend`'s payloads through it — so the tests assert against the same
response shapes the real backend produces. The Anthropic client is stubbed the
same way, and `ANTHROPIC_API_KEY` is cleared for every test so a developer with
one exported can't accidentally make live calls.

What's covered: request/response shapes for every endpoint on both backends,
parity between them (routes, request models), the error contract (422 for a
malformed body, 500 with a `detail` for a bad geometry or an upstream
failure), caching, and the summary branch selection.

## Caching

`/api/tile/*` and `/api/stats` are cached in-process, keyed by a hash of the
request (`cache.py`) — the README's own recommendation, now implemented.
Redrawing the same shape or stepping the year slider back and forth no longer
re-runs `reduceRegion`.

`GET /api/cache` reports hits, misses and entry counts. `CONTOUR_CACHE_TTL=0`
disables it; the default TTL is 15 minutes.

Worth being clear about the limit: this is **per-process**. Cloud Run runs
several instances and recycles them, so a cold instance always misses and two
users drawing the same field may not share an entry. It removes the obvious
waste — one person re-examining one site — and nothing more. A shared cache is
the thing that helps at scale.

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
