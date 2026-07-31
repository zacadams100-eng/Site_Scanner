# Deploying Contour

Two pieces, deployed separately:

| Piece | Where | Config |
| --- | --- | --- |
| `app.py` (or the mock) | Google Cloud Run | `Dockerfile` |
| `site-scanner.html` | Vercel | `vercel.json` |

Nothing here has been run against a real cloud account — no credentials are
configured yet. Treat the commands as the intended path, not as verified
output, and expect the first deploy of anything to need a round of fixing.

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
  --memory 1Gi \
  --timeout 120
```

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

First put the Cloud Run URL into `vercel.json`, replacing the placeholder in
the `/api/:path*` rewrite:

```bash
API=$(gcloud run services describe contour-api --region europe-west2 --format='value(status.url)')
sed -i '' "s#https://REPLACE-WITH-CLOUD-RUN-URL.a.run.app#${API}#" vercel.json   # GNU sed: drop the ''
```

Then:

```bash
vercel deploy --prod
```

### How the frontend finds the backend

`resolveApiBase()` in `site-scanner.html` takes the first of:

1. `?api=https://host` in the URL — ad-hoc, useful for pointing a deployed page
   at a local backend while debugging
2. `<meta name="contour-api" content="...">` in the page head
3. `http://localhost:8000` when served from localhost; **same-origin otherwise**

Option 3 is why the rewrite matters: on Vercel the page requests `/api/stats`
on its own origin, Vercel proxies it to Cloud Run, and the browser never makes
a cross-origin request. That means **no CORS**, and no backend URL baked into
the HTML. It also means you can lock the backend down — with the proxy in
place, `allow_origins=["*"]` in `app.py` is no longer doing any work and should
be narrowed to your Vercel domain before this is public.

If you'd rather call Cloud Run directly, set the `contour-api` meta tag to the
service URL and drop the `/api` rewrite. Keep the CORS middleware in that case.

---

## 3. Known gaps

- **The CSP in `vercel.json` includes `script-src 'unsafe-inline'`.** The whole
  application is one inline `<script>`, so it cannot be removed without moving
  that code to a separate file. The rest of the policy is real, but don't read
  the presence of a CSP as meaning inline-script injection is mitigated.
- **Leaflet and Turf load from cdnjs**, so the page depends on a third party at
  runtime and the CSP has to allow that origin. Vendoring both into the repo
  would remove the dependency and let `script-src` drop to `'self'`.
- **The Cloud Run service is deployed `--allow-unauthenticated`**, i.e. the API
  is public. It has no rate limiting, and Earth Engine has compute quotas —
  a scraper could exhaust them. Before this is public, put the Cloud Run URL
  behind the Vercel proxy only (above), and consider a per-IP limit.
- **No caching.** Every drawn shape is a fresh `reduceRegion` call, and the
  README already flags Earth Engine's compute quotas. Note that an in-process
  cache buys little here: Cloud Run runs several instances and recycles them,
  so most requests would miss. A shared cache (Memorystore, or Cloud Storage
  keyed by a geometry hash) is the shape that actually helps.
