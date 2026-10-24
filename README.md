# Contour — desk study map

Red line in, finished designations-and-constraints map out.

This repo used to be Site Scanner, a satellite-statistics app (NDVI,
temperature, price per m²). It is now the tool behind the one product on the
website: a £150 designations and constraints map for UK ecology and planning
consultancies. The satellite code is gone from `main`'s working tree; it is
still in git history up to commit `5e4e012` if it is ever needed.

It reads **30 official layers live** from Natural England, the Environment
Agency, Historic England, the Forestry Commission, Defra and councils (via
planning.data.gov.uk), all under the Open Government Licence. It then makes:

- **PDF**: A4 landscape. Page 1 is the map at a standard printed scale with
  the red line, a key showing only what is on the map, and the headline
  findings. The pages after it hold the full findings schedule with limitations.
- **GeoPackage**: every layer in British National Grid, styled for QGIS. It
  also opens in ArcGIS Pro, though without the styles.
- **JSON record**: what was asked, what each publisher returned and when.
  Keep it with the order.

No Earth Engine, no satellite statistics, no scores.

## Run it

```bash
pip install -r requirements-dev.txt
python -m pytest                       # 13 tests, fictional data, no network

# list the 30 layers
python -m sheet layers

# make a sheet (GeoJSON, KML, GeoPackage or zipped shapefile)
python -m sheet make red-line.geojson --title "Land at Home Farm, Dorking" --ref ORD-001 --out jobs/ORD-001
```

`make` exits with code **3** if any layer was *not assessed*. Check those
layers before you send anything to a client.

### The map app (internal)

Draw the red line on a satellite map, make the sheet, see every finding on the
map, download the PDF, GeoPackage and record.

```bash
cd web && npm install && npm run build && cd ..
uvicorn sheet.api:app --port 8000      # then open http://localhost:8000
```

While working on the interface, run `cd web && npm run dev` as well and open
http://localhost:5173. It proxies to the API on :8000.

Basemaps on screen: Esri satellite (the ArcGIS World Imagery tiles), satellite
with labels, Esri topographic, OpenStreetMap and light grey. These are for
drawing only. The PDF uses its own basemap (below).

**Do not put the app on the internet.** It has no login. Customers order on the
website; you make the sheet.

### Settings

- `OS_API_KEY` adds an OS basemap to the PDF. A free OS Data Hub key works,
  because only open zoom levels are requested. Without one, the PDF map
  renders on a 1 km grid.
- `CONTOUR_CONTACT` puts your email in the User-Agent so publishers can reach
  you if something goes wrong.
- `CONTOUR_FIXTURES=<folder>` reads fictional fixture layers instead of the
  publishers, for working offline. Make the folder with
  `python -m tests.fixtures_build demo-fixtures`. Everything made this way is
  watermarked TEST DATA, and the app shows a TEST DATA badge.

## The rules it keeps

1. **Not assessed is never clear.** If a query fails, the sheet says
   "Not assessed" in red, with the reason. It never says "none found".
2. **Council layers carry a caveat.** Not every council publishes conservation
   areas, tree preservation orders, Green Belt or local green space to
   planning.data yet. A nil return on those layers says "confirm locally".
3. **Test data cannot pass as real.** Fixture runs are watermarked
   *TEST DATA — NOT REAL* on every page.
4. **No score, rating or suitability verdict.** The sheet only says what is
   there and how far away it is.
5. **Attribution stays on every sheet.** OGL and OS credits are printed on
   the PDF. Don't remove them.

## Files

| File | What it does |
|---|---|
| `sheet/layers.py` | The 30 layers, their sources, search radii and styles. Edit this to add or drop one. |
| `sheet/fetch.py` | Live queries (planning.data entity API, ArcGIS FeatureServer), plus present / none found / not assessed. |
| `sheet/findings.py` | Distances, directions and the plain-English lines. |
| `sheet/render.py` | The PDF. |
| `sheet/gpkg.py` | GeoPackage plus QGIS styles. |
| `sheet/basemap.py` | Optional OS Light basemap for the PDF. |
| `sheet/api.py` | API for the map app; serves `web/dist` once built. |
| `sheet/static/index.html` | Bare fallback draw page, used before `web/` is built. |
| `web/` | The map app (React + MapLibre). |
| `examples/guildford.geojson` | Example red line that CI makes a real sheet for. |
| `tests/` | `python -m pytest`. Fictional fixtures, no network. |

## CI makes a real sheet on every push

The tool was written where the publishers couldn't be reached. GitHub's
runners can reach them, so the **Live sheet** job makes a real sheet for
`examples/guildford.geojson` on every push:

- Download the PDF, GeoPackage and JSON from the run's **Artifacts**.
- Any layer that came back not assessed appears as a warning with its reason.

Add an `OS_API_KEY` repository secret to get the OS basemap on that sheet.

## Still to check on the first real runs

- The ArcGIS layers (priority habitat, SSSI impact risk zones, GCN areas, main
  river, surface water) return `f=geojson`, and their label fields come
  through. If a label shows as "Unnamed area", open the JSON record or the
  GeoPackage and add the right field name to `label_fields` in `layers.py`.
- The planning.data entity API answers WKT `intersects` queries for each dataset.
- The OS basemap tiles line up with the red line on the PDF (the tile origin
  is documented in `basemap.py`).
- The search radii (10 km / 2 km / 1 km / 500 m / 250 m) are product
  defaults, not regulatory thresholds. Ask the first clients whether they
  match how they work.
