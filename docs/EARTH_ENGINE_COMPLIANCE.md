# Earth Engine — commercial use

**Status: 🔴 BLOCKER for commercial launch. LEGAL REVIEW REQUIRED.**

This is the largest single legal risk in the project, it is not new, and it is
not resolved. `TECHNICAL_PLAN.md §8.9` has recorded it since the architecture
was written.

Nothing in this document is legal advice, and **no Google terms page was
fetched to write it** — this environment cannot reach one. It describes what
the code does, which is verifiable, and what that appears to imply, which is
not.

---

## 1. What the code actually does

Verified by reading `app.py` and `ee_series.py`.

**Authentication.** A service-account key, loaded from
`GOOGLE_APPLICATION_CREDENTIALS_JSON` or globbed from `~/ee-backend/*.json`,
then `ee.Initialize(credentials, project=...)`. The project id comes from
`gcloud`; nothing is hardcoded, because the repository is public.

**The project is registered non-commercial.** That is the crux.

**What is asked of Earth Engine:**

| Call | Where | What leaves Google |
| --- | --- | --- |
| `reduceRegion` | `ee_series.py`, all 27 factors | Aggregate statistics for one drawn polygon — a mean, a frequency histogram, a summed `pixelArea` |
| `getMapId` | `app.py:264`, `app.py:290` | A tile URL for a visualised composite |

**What is not done:** no `Export.*`, no asset creation, no bulk download, no
raw imagery served to the browser, no scraping, no circumvention of anything.
The interactive path returns numbers, not pixels.

**Caching.** `cache.py` holds per-factor series results in process for 15
minutes, keyed on geometry hash. That is a cache of *derived statistics we
computed*, not of Earth Engine imagery.

**The tile path is the exception worth flagging.** `getMapId` returns a Google
tile URL that the browser then fetches directly. Those tiles are rendered
imagery from Earth Engine, displayed inside what is intended to become a paid
product. That is a materially different act from computing a mean, and it is
the part of the current architecture most likely to need changing.

---

## 2. What is at issue

Three questions, none of which this repository can answer:

1. **Does serving derived statistics from a non-commercially-registered
   Earth Engine project to paying customers fall inside or outside the
   permitted use?** The numbers are ours; the compute that produced them is
   Google's.
2. **Does the `getMapId` tile path change the answer?** It puts Google-rendered
   imagery on a customer's screen.
3. **What does the commercial path actually cost?** Earth Engine has paid
   commercial offerings; the tier, the price and whether this product's usage
   pattern fits are all unknown here.

---

## 3. The mitigation that already exists

`ingest/` is the answer this project already built for exactly this: Earth
Engine derives products **in batch**, the results are stored in our own
database, and users are served from our storage rather than from Google on the
request path.

`docs/licensing/DECISION-LOG.md` records the conclusion reached across all six
possible replies to the drafted Google enquiry: **ingest-then-store is
mandatory in four branches and merely advisable in the other two.** So the
architecture is already decided; it is the deployment that has not followed.

`ingest/` is built, tiled, resumable and benchmarked. It has never ingested
anything for real. `BLOCKERS.md §5` explains why — no credentials, so the
fetch stage of the benchmark is a synthetic stand-in.

---

## 4. What has to happen, and by whom

### ACTION REQUIRED FROM OWNER

**Send the Google enquiry.** `docs/licensing/` has it drafted, with the
consequence of every possible reply worked out in advance so nobody
re-litigates the architecture when an answer arrives. It has not been sent.

**Do not enable a paid Earth Engine tier without deciding to.** Per the audit
mandate, that is not a change to make automatically. If commercial eligibility
turns out to require a paid plan, that is a cost decision:

- Expected cost: **unknown**. Not recorded here because guessing at a price is
  the same failure as guessing at a licence.
- Functionality that depends on it: 27 of 55 real factors — every Sentinel-2
  index, all ERA5 climate, MODIS thermal, ESA WorldCover and JRC surface water.
  Roughly half the real catalogue.

**Send the ESA enquiry first.** It is the cheaper question and it may make the
Google one smaller. Also drafted, also unsent.

---

## 5. Recommended architecture

Unchanged from `TECHNICAL_PLAN.md`, and now with a licensing reason as well as
a performance one:

```
Earth Engine (batch, our project)
        ↓  derive products
our storage (COG + H3 aggregates)
        ↓  serve
customer
```

rather than

```
Earth Engine  →  customer request path
```

`BENCHMARK.md` measured the second architecture at tens of seconds and the
first at 1–50 ms, so this is the same conclusion performance already reached.
That is convenient, not evidence — the licensing question stands on its own.

**The tile path needs a decision separately.** Serving `getMapId` tiles into a
paid product is the least defensible thing in the current architecture, and it
is also the easiest to remove: the map works without it, because
`scripts/build_basemap.py` bundles a Natural Earth basemap and the value
overlay is drawn from cell statistics the app computes itself.

---

## 6. What this document does not establish

That any of the above is permitted, or prohibited. Only Google can answer 1
and 2, and only a qualified lawyer should interpret the answer.

**LEGAL REVIEW REQUIRED** before any commercial launch that includes an Earth
Engine factor.
