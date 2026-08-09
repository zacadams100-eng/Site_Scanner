# Deployment status

Written while preparing the deployment. Read this before assuming something is
deployed.

## What is done

Deploying no longer requires a Google Cloud account. The API now has a second
home — `api/index.py`, a Vercel serverless function running the same
credential-free backend the local mock runs, mounting the same
`routes_catalog` router the Earth Engine backend mounts. The contract is
identical and the deployment is:

```bash
npm i -g vercel && vercel login && vercel link && vercel deploy --prod
```

No environment variables. No secrets. No second service.

`.github/workflows/deploy.yml` does the same from CI on a manual trigger, after
running the full test suite, once three Vercel secrets exist in the repository
(`VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`).

## What was verified, and how

Vercel's routing is declarative, so the usual way to find out whether it is
right is to deploy and see. `scripts/serve_build.py` reproduces `vercel.json`
locally — static files from `web/dist`, `/demo` to the demo page, `/api/*` into
the function, everything else to `index.html` — and the production bundle was
driven through it in a browser:

| Check | Result |
| --- | --- |
| `/` serves the built app | 200, app boots, no console errors |
| `/api/catalog` through the function | 200, 266 factors, 87 KB |
| `/api/series` through the function | 200, report renders, 15 annual rows |
| `/basemap/england.json` | 200, 605 KB, all four basemap layers install |
| Place labels at national zoom | 16 |
| `/demo` | 200, loads, no console errors |
| Missing asset | 200 of `index.html` — the SPA catch-all, as designed and documented |

`tests/test_serverless.py` covers the function's path handling, including the
three shapes a Vercel rewrite can deliver a path in.

Two bugs were found by doing this rather than by reading:

- **The demo page had no doctype and no charset.** Served from Vercel it
  inherits `charset=utf-8` and looks fine; opened from a `file://` URL — which
  is the demo's whole purpose — every em-dash and pound sign was mojibake.
  Fixed in `demo/build.sh`.
- **`.vercelignore` excluded every Python module.** Correct when the only
  backend was Cloud Run; it would now produce a function that cannot import its
  own catalogue.

## Superseded: the deploy happened on 2026-08-05

**Everything below this heading was true when it was written on 2026-08-04 and
was overtaken the next day.** The app is live at
https://site-scanner-pi.vercel.app; `npx vercel deploy --prod` ships a build.
The deploy took four rounds of configuration failures, all of one shape — an
exclude list written for the repository root applied by a matcher that ignores
depth — and all three ignore files now have tests. See `HANDOFF.md`.

The section that follows is kept as a record of what the blockers were, not as
a statement of what they are. Read it as history.

---

## What was blocked, and why (as of 2026-08-04)

**There is no live URL yet, and I cannot create one.** Two hard blockers, both
external to the repository:

1. **No Vercel account or token.** Deploying requires an authenticated session
   (`vercel login`) or a `VERCEL_TOKEN`. That is an account credential; it
   cannot be created from here.
2. **Network egress is policy-restricted in this environment.** Outbound HTTPS
   goes through a proxy that answers `403` to `CONNECT` for anything outside a
   small allowlist (GitHub, npm, PyPI). `vercel.com`, `api.vercel.com` and
   `*.googleapis.com` are all denied, so even with a token the CLI could not
   reach the API from here.

Everything up to the authenticated call is done and tested. The remaining step
is one command, run anywhere with a normal internet connection and a Vercel
login.

## Cloud Run is still the path for Earth Engine

The serverless function deliberately does not carry `app.py`: `earthengine-api`
and its Google client stack are far too large for a serverless bundle, and the
real backend needs a service-account key that belongs in Secret Manager. That
path is unchanged and documented in DEPLOY.md Path B; it needs a Google Cloud
account, which is the same class of blocker.

Once Cloud Run is up, one rewrite in `vercel.json` points the frontend at it.
Keep `api/index.py` either way — it is what a preview deployment falls back to
when the real backend is down or not yet built.

## The first deploy, step by step

For whoever runs it:

1. `npm i -g vercel && vercel login`
2. `vercel link` — creates `.vercel/project.json`; do not commit it.
3. `vercel deploy --prod` — prints the URL.
4. Check the three things that cannot fail silently:
   ```bash
   URL=https://your-project.vercel.app
   curl -sS "$URL/api/catalog" | head -c 120           # factors, not HTML
   curl -sS -o /dev/null -w '%{http_code} %{size_download}\n' "$URL/basemap/england.json"
   curl -sSI "$URL/" | grep -i content-security-policy
   ```
   A `/api/catalog` that returns HTML means the rewrite matched the SPA
   catch-all instead of the function — see DEPLOY.md, "If the API 404s".
5. Put the URL in README.md and in this file.
