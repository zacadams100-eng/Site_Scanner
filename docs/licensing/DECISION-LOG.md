# Licensing decision log

Two questions block selling this product. Neither can be answered from inside
the repository — both need a reply from an organisation — so this file records
what we will do for **each possible answer**, decided in advance. The point is
that when the replies arrive, nobody has to re-reason the architecture under
time pressure; they look up the answer and execute.

Drafts to send: `email-google-earth-engine.md`, `email-copernicus-sentinel-2.md`.
Send the Copernicus one first — see "Order" below.

## The two questions

| # | Question | Asked of | Sent | Replied | Answer |
| --- | --- | --- | --- | --- | --- |
| Q1 | Does batch-derivation-then-serve need a commercial Earth Engine licence, and at what cost? | Google Earth Engine | _not yet_ | | |
| Q2 | Is Sentinel-2 CC BY-SA 3.0 IGO or the Copernicus data policy, and does a spatial mean count as a derived work? | ESA / Copernicus Data Space | _not yet_ | | |

## Order: send Q2 first

Q2 is the cheaper question and it changes what Q1 is worth. Eleven of the 24
Earth Engine factors are Sentinel-2 indices, and they are the ones people
actually use. If Copernicus confirms commercial reuse with attribution only,
those eleven can be sourced directly from the Copernicus Data Space with no
Google involvement at all, and Q1 shrinks to covering ERA5-Land, MODIS and
WorldCover — none of which need Earth Engine either, since all three have
direct public distributions.

That is worth saying plainly: **a clean answer to Q2 may make Earth Engine
optional rather than negotiable.** Do not spend money on Q1 before Q2 comes
back.

## Q1 — Earth Engine: what we do for each answer

### A. "Batch derivation does not require a commercial licence"

The best case, and the least likely.

- Keep Earth Engine as the ingest engine.
- **Ingest-then-store becomes mandatory anyway** — this answer is conditional
  on users never touching Earth Engine, so the on-request path in `app.py`
  must be retired, not merely deprecated. Leaving it enabled would make us
  non-compliant by accident the first time someone runs it in production.
- Action: make `ingest/run.py` the only Earth Engine caller, and put a hard
  guard in `app.py` so a request path cannot reach `ee_series.py` without an
  explicit environment override.

### B. "Commercial licence required, and the price is acceptable"

- Buy it. Keep Earth Engine.
- **Ingest-then-store becomes optional** — a legitimate engineering choice
  rather than a legal requirement. It should still be done, for latency and
  quota, but it stops being a blocker for the first paying customer.
- Action: record the licence, its scope and its renewal date here. Note
  whether the licence covers derived-product redistribution (question 4 in the
  draft), because that governs whether CSV export of NDVI is allowed.

### C. "Commercial licence required and the price is not acceptable", or no reply

Treat silence past **six weeks** as this answer. Do not wait longer; the cost
of waiting is building more on a foundation we might remove.

- **Earth Engine is dropped from the product path entirely.**
- Every one of the 24 Earth Engine factors is re-sourced:

  | Group | Factors | Replacement |
  | --- | --- | --- |
  | Sentinel-2 indices | 11 | Copernicus Data Space / Sentinel Hub open data, subject to Q2 |
  | ERA5-Land monthly + daily | 8 | Copernicus Climate Data Store directly |
  | MODIS LST | 3 | NASA LP DAAC / AppEEARS directly — public domain |
  | ESA WorldCover | 2 | esa-worldcover.org GeoTIFFs — CC BY 4.0 |

- **Ingest-then-store becomes mandatory and structural**, not an optimisation.
  None of those replacements offer a server-side reduce-over-polygon API. They
  give you pixels. Something has to fetch, composite and aggregate them to a
  grid before a user can query them, and that something is `ingest/`.
- This is the outcome the architecture should be biased towards, because it is
  the one where the work already done matters most.

## Q2 — Sentinel-2: what we do for each answer

### A. "Copernicus data policy; commercial reuse permitted; attribution only"

- Correct `catalog.py`: `sentinel2_sr` and `sentinel1_sar` get the Copernicus
  licence and `commercial: "yes"`.
- Sentinel-2 direct becomes the primary source for the eleven indices, and
  Earth Engine's necessity drops accordingly.

### B. "CC BY-SA 3.0 IGO applies, and it reaches derived statistics"

The expensive case. Share-alike on our outputs would mean a customer's
exported NDVI CSV carries a share-alike obligation, which most commercial
customers will not accept.

- Keep `commercial: "verify"` — but change it to a warning the user sees,
  not a metadata field, on any export containing a Sentinel-2 factor.
- Evaluate Landsat (USGS, public domain, 30 m) as the primary optical source.
  Coarser and slower — 16 days against 5 — but unencumbered. For monthly
  composites over a site of a few hectares the resolution loss is real but not
  fatal, and it is better than a licence we cannot honour.

### C. "CC BY-SA applies but does not reach aggregated statistics"

- The likely middle answer. Keep Sentinel-2, keep the attribution, and record
  the reasoning **here with the date and the person who gave it**, because it
  is exactly the kind of interpretation that gets questioned in due diligence.
- Do not redistribute imagery or tiles, ever — that is where share-alike would
  bite. The catalogue's `stored: true` flag on Sentinel-2 must not be read as
  permission to serve pixels.

## The standing conclusion

Across the six branches above, **ingest-then-store is mandatory in four and
merely advisable in two.** Nothing on the table makes it wrong. That is enough
to justify treating `ingest/` as the real architecture and the on-request Earth
Engine path in `app.py` as a prototype that survived — which is how
TECHNICAL_PLAN.md §3 already describes it, and which the benchmark work in
`BENCHMARK.md` should be read against.

## What is already settled and needs no email

- **ERA5-Land** — Copernicus C3S, commercial use permitted with attribution.
- **MODIS LST** — NASA/USGS, public domain.
- **ESA WorldCover** — CC BY 4.0.
- **All 22 open-data factors** (`docs/OPEN-DATA.md`) — Open Government Licence
  v3.0, which permits commercial use with attribution. This is the only part
  of the catalogue with no licensing question outstanding at all, which is a
  second reason to keep growing it.
- **Natural Earth basemap** — public domain (CC0).
- **MapLibre GL JS** — BSD.

---

_Maintained by hand. When a reply arrives, fill in the table at the top, write
the date, and act on the branch — do not re-derive it._
