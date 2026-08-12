# Connecting Earth Engine

**Status: not connected in any environment Claude can reach.** This document
exists so a human can unblock it in one pass. Every step below has been read
out of the code rather than remembered.

Until this is done, the product runs on `mock_ee_backend`, every check reports
"no signal", and no product screenshot can honestly be taken.

---

## What you need

| | What | Where it comes from |
| --- | --- | --- |
| 1 | A Google Cloud project | console.cloud.google.com — note the **project ID**, not the display name |
| 2 | Earth Engine API enabled on it | console.cloud.google.com/apis/library/earthengine.googleapis.com |
| 3 | Earth Engine registration for the project | signup.earthengine.google.com — a project must be registered for commercial or noncommercial use before the API answers |
| 4 | A service account | IAM → Service Accounts → Create |
| 5 | That service account registered with Earth Engine | The account's email must be added at code.earthengine.google.com as an EE user, or every call returns a permission error that reads like a billing problem |
| 6 | A JSON key for it | Service account → Keys → Add key → JSON |

Step 5 is the one that is usually missed. A correctly created service account
with a valid key still cannot call Earth Engine until it is registered.

---

## Wiring it up

`app.py` reads exactly two environment variables:

```bash
export GOOGLE_APPLICATION_CREDENTIALS_JSON="$(cat service-account-key.json)"
export EE_PROJECT="your-gcp-project-id"
```

`GOOGLE_APPLICATION_CREDENTIALS_JSON` is the **contents** of the key file, not
a path to it. This is deliberate — it is what a serverless platform can hold as
a secret — and it is the most common mistake when setting this up by hand.

Then run the real backend instead of the mock:

```bash
python3 -m uvicorn app:app --port 8000
```

### It fails at import, not at request time

`app.py` calls `init_earth_engine()` while the module is being imported. With
either variable missing you get a `RuntimeError` before the server starts, and
uvicorn exits. That is intended: a backend that starts without credentials and
then fails every request would look like an outage rather than a configuration
problem.

So "uvicorn exited immediately" is the expected symptom of a missing variable,
not a broken install.

---

## Confirming it actually worked

The mock stamps every response with a header. The real backend never sets it.

```bash
curl -sD- localhost:8000/api/catalog -o /dev/null | grep -i contour-mock
```

- **`x-contour-mock: true`** → you are still on the mock. The real backend is
  not running, whatever the terminal says.
- **no output** → the real backend answered.

Then check that real factors actually resolve:

```bash
curl -s "localhost:8000/api/catalog?scanner=land" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); s=d['summary']; \
    print('real', s['real_factor_count'], 'verified', s['verified_factor_count'])"
```

The frontend shows a **DEMO DATA** badge whenever the header is present, so the
interface itself is a reliable check: if the badge is gone, the header is gone.

---

## What to expect once it is connected

**Not a full report.** Of Land's 271 factors, 28 have a real implementation and
11 of those are `verified` — actually exercised against the live service. The
rest are generated and will continue to report "not assessed", because
generated data may never produce a finding.

That is the honest picture and the radar is built to show it. Do not select a
narrow factor set to make the report look fuller — the coverage figure exists
precisely so a thin assessment cannot be mistaken for a clean site.

## Cost

Earth Engine bills per compute unit against the project in `EE_PROJECT`. The
series cache (`routes_catalog.SERIES_CACHE`) exists because adding a twelfth
factor to a report would otherwise re-run the eleven already on screen. Keep it.
