# Deploying Contour

Two pieces, deployed separately:

| Piece | Where | Config |
| --- | --- | --- |
| `app.py` (or the mock) | Google Cloud Run | `Dockerfile` |
| `web/` (the React app) | Vercel | `vercel.json` |

`site-scanner.html` is the original single-file prototype. It still works, but
it predates the catalogue — it calls only `/api/stats`, `/api/summary` and
`/api/tile/*`, and knows nothing about the 118 factors, the monthly timeline,
the attribute table or the charts. `web/` is the deployed frontend; the
prototype is kept for reference.

**Step 2 (Vercel) is done and live at https://site-scanner-pi.vercel.app.**
Step 1 (Cloud Run) is blocked on billing — see below. The commands in step 1
have been run as far as billing allows and are corrected where they were wrong.

What is verified:

- **The image builds and serves.** Built with `docker build` in Cloud Shell and
  run locally; the mock backend answered `/api/catalog` from inside the
  container.
- **The Vercel deploy works**, including the demo page and the MapLibre worker
  files. The deployed `/` renders its map, which is the first proof the worker
  fix holds — that bug only appears behind an SPA catch-all rewrite and cannot
  be reproduced locally.
- **The Dockerfile's module list was missing seven of ten modules.** Everything
  added after the file was written. The container would have died on `import`
  before serving a request. `tests/test_docker_context.py` now walks the import
  graph and fails if the list drifts again.

What is not:

- **Cloud Run has never run.** The service account key, Secret Manager wiring
  and the real Earth Engine path are all unproven in the cloud.

---

## 0. Billing — the current blocker

`gcloud run deploy` fails on `sitescanner-504112` with:

```
ERROR: FAILED_PRECONDITION: Billing account for project '328960690784' is not
found. Billing must be enabled for activation of service(s)
'artifactregistry.googleapis.com,cloudbuild.googleapis.com,run.googleapis.com'
```

Google gates *enabling those services* on a billing account, not just spending,
so the free tier does not get you around it. A billing account with a payment
method has to be attached to the project in the Cloud Console. Nothing in this
repo can work around it, and no flag skips it.

At this app's traffic the running cost is nil — Cloud Run scales to zero and
the free tier is 2M requests a month — but the card still has to be on file.

---

## 1. Backend → Cloud Run

### Deploy the mock first (no Earth Engine needed)

Worth doing before Earth Engine setup finishes: it gets a real HTTPS backend
live so the deployed frontend works end to end, and proves the container,
region and IAM are right before credentials are in the mix.

```bash
gcloud run deploy contour-api \
  --source . \
  --region europe-west2 \
  --allow-unauthenticated \
  --set-env-vars APP_MODULE=mock_ee_backend:app
```

`gcloud run deploy --source .` builds the `Dockerfile` with Cloud Build and
deploys the result — no separate `docker build`/`push`.

### Deploy the real backend

Put the service account key in Secret Manager rather than an environment
variable, so it isn't visible in the Cloud Console or in `gcloud run services
describe` output:

```bash
gcloud secrets create contour-ee-key --data-file=service-account-key.json
gcloud secrets create contour-anthropic-key --data-file=- <<< "$ANTHROPIC_API_KEY"

# Let the service's runtime identity read them
PROJECT_NUMBER=$(gcloud projects describe "$(gcloud config get-value project)" --format='value(projectNumber)')
for s in contour-ee-key contour-anthropic-key; do
  gcloud secrets add-iam-policy-binding "$s" \
    --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --role=roles/secretmanager.secretAccessor
done
```

Then:

```bash
gcloud run deploy contour-api \
  --source . \
  --region europe-west2 \
  --allow-unauthenticated \
  --set-env-vars EE_PROJECT=your-gcp-project-id \
  --set-secrets GOOGLE_APPLICATION_CREDENTIALS_JSON=contour-ee-key:latest \
  --set-secrets ANTHROPIC_API_KEY=contour-anthropic-key:latest \
  --set-env-vars CORS_ALLOW_ORIGINS=https://your-app.vercel.app \
  --memory 1Gi \
  --timeout 120
```

Set `CORS_ALLOW_ORIGINS` once you know the Vercel domain — it takes a
comma-separated list, and unset means `*`. Step 2 explains why it matters even
though the proxy means the browser never makes a cross-origin request.

Note the deploy prints the service URL — you need it for step 2.

**Why those flags.** `--memory 1Gi` because `earthengine-api` pulls in the
Google API client stack and the 512Mi default is tight. `--timeout 120`
because `reduceRegion` over a large polygon can take a while; Cloud Run's
60s default would cut it off.

**A missing secret is a startup crash, not a 500.** `app.py` calls
`init_earth_engine()` at import time, so a missing or malformed
`GOOGLE_APPLICATION_CREDENTIALS_JSON` fails the container before it serves
anything, and Cloud Run reports a failed revision. That is the intended
behaviour — it fails loudly instead of serving broken tiles — but it does mean
"deploy succeeded, service is red" points at credentials first. Check with:

```bash
gcloud run services logs read contour-api --region europe-west2 --limit 50
```

`ANTHROPIC_API_KEY` is different: it's optional. Without it `/api/summary`
returns a deterministic paragraph rather than failing.

### Verify

```bash
API=$(gcloud run services describe contour-api --region europe-west2 --format='value(status.url)')
curl -sS "$API/"
curl -sS -X POST "$API/api/tile/ndvi" -H 'Content-Type: application/json' -d '{"year":2024}'
```

A response carrying `X-Contour-Mock: true` means the mock is deployed, not the
real backend — check `APP_MODULE`.

---

## 2. Frontend → Vercel

`vercel.json` is already set up for the Vite build. It installs and builds
`web/`, publishes `web/dist`, and proxies `/api/*` to Cloud Run. The only thing
you have to change is the backend URL.

First put the Cloud Run URL into `vercel.json`, replacing the placeholder in
the `/api/:path*` rewrite:

```bash
API=$(gcloud run services describe contour-api --region europe-west2 --format='value(status.url)')
sed -i "s#https://REPLACE-WITH-CLOUD-RUN-URL.a.run.app#${API}#" vercel.json   # macOS: sed -i ''
```

Then:

```bash
npx vercel deploy --prod
```

### What the first deploy actually took

Four things went wrong, all in configuration rather than code:

1. **`sudo npm i -g vercel` → `sudo: npm: command not found`.** Cloud Shell's
   Node lives under `$HOME` and `sudo` drops it from `PATH`. Use `npx vercel`,
   or `npm i -g vercel` without `sudo`.
2. **Project names must be lowercase.** `SiteScanner` is rejected; the error
   arrives after the settings prompts, so you answer them twice.
3. **`Error: fetch failed`** on upload — `.vercelignore` did not exclude
   `node_modules`, so it tried to send 244 MB.
4. **The build failed in seven seconds with only an exit code.** `.vercelignore`
   uses gitignore syntax, so a bare `scripts/` matched `web/scripts/` as well
   as the root one, and `web/scripts/copy-maplibre-worker.mjs` never reached
   the builder. Root-only patterns need a leading slash.

Answer **no** to "Customize settings?" — `vercel.json` already has them, and
the CLI's "Detected FastAPI" guess is wrong and harmless. Answer **no** to
"Connect detected Git repository?" until the branch is merged, or Vercel will
build `main` instead of what you have locally.

Vercel runs, from the repo root:

```
installCommand   npm --prefix web ci
buildCommand     cp demo/site-scanner-demo.html web/public/demo.html
                 npm --prefix web run build
outputDirectory  web/dist
```

Build it locally first if you want to see it fail faster — `npm --prefix web
run build` is the same command, and `tsc -b` runs ahead of Vite so a type error
stops the deploy rather than shipping.

### What ends up deployed

| Path | What |
| --- | --- |
| `/` | The React app. Talks to Cloud Run through the `/api` proxy. |
| `/demo` | The self-contained demo. No backend, no network — useful for sharing a link that cannot break because the API is down. |
| `/assets/*` | Hashed JS and CSS, cached immutably for a year. |

### How the frontend finds the backend

It doesn't, and that is the point. The app requests `/api/series` on its own
origin; Vercel proxies it to Cloud Run. The browser never makes a cross-origin
request, so:

- **no CORS**, and no backend URL baked into the bundle;
- CORS on `app.py` is doing nothing for *your* frontend once the proxy is in
  place — but the Cloud Run URL is still public and unauthenticated, so a
  wildcard is what lets any other page on the web call this API from a
  visitor's browser and spend your Earth Engine quota. Set
  `CORS_ALLOW_ORIGINS` to your Vercel domain on deploy. Note this narrows the
  browser path only; `curl` ignores CORS entirely, so it is not a substitute
  for the rate limiting in §3;
- you can point a preview deployment at a different backend by changing one
  line of `vercel.json`, with no rebuild of the app itself.

In development, `web/vite.config.ts` proxies `/api` to `127.0.0.1:8000`, so the
same relative paths work locally with no build-time switch.

### Deploying the old prototype instead

If you would rather prove the Cloud Run wiring with something that has no build
step, `site-scanner.html` still deploys standalone. Set `outputDirectory` to
`"."`, drop `installCommand` and `buildCommand`, and add
`{ "source": "/", "destination": "/site-scanner.html" }` as the first rewrite.
It needs `script-src 'unsafe-inline'` and the cdnjs origin in the CSP, both of
which the current policy has dropped.

---

## 3. Known gaps

- **The SPA catch-all rewrite masks 404s.** `/(.*)` → `/index.html` means any
  missing asset returns index.html with a 200 rather than a 404. That is how a
  missing MapLibre worker chunk turned into a silently blank map during
  development of this config: the worker fetched HTML, failed to parse, and no
  console error or map error event was raised — the map simply rendered
  nothing while the rest of the app looked perfectly healthy. If something is
  mysteriously absent at runtime, check the Network tab for a 200 that returned
  HTML before assuming the code is wrong. `scripts/copy-maplibre-worker.mjs`
  and `MapCanvas.tsx` carry the full write-up.
- **`style-src` still allows `'unsafe-inline'`.** MapLibre positions markers,
  controls and the canvas by setting style attributes, which CSP counts as
  inline style. `script-src` is now `'self'` — the prototype needed
  `'unsafe-inline'` there because it was one giant inline `<script>`, and the
  Vite build removed that. Inline *style* injection is a much smaller surface
  than inline script, but it is not nothing.
- **`worker-src` allows `blob:`.** MapLibre builds its tile worker from a blob
  URL, so this cannot be dropped without patching MapLibre.
- **The basemap is fetched from `tile.openstreetmap.org` at runtime**, so the
  page depends on a third party and `img-src`/`connect-src` have to allow it.
  OSM's tile usage policy does not cover production traffic — before this has
  real users, move to your own TiTiler instance or a paid tile provider. The
  `/demo` page has no such dependency, which is why its CSP is far tighter.
- **The Cloud Run service is deployed `--allow-unauthenticated`**, i.e. the API
  is public. It has no rate limiting, and Earth Engine has compute quotas —
  a scraper could exhaust them. Before this is public, put the Cloud Run URL
  behind the Vercel proxy only (above), and consider a per-IP limit.
- **No caching.** Every drawn shape is a fresh `reduceRegion` call, and the
  README already flags Earth Engine's compute quotas. Note that an in-process
  cache buys little here: Cloud Run runs several instances and recycles them,
  so most requests would miss. A shared cache (Memorystore, or Cloud Storage
  keyed by a geometry hash) is the shape that actually helps.
