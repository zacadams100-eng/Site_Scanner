# Open data: what is real now, and how far it is proven

`open_data.py` makes 22 catalogue factors return real numbers from UK
government open data. None of them need a key, a quota, or a satellite
licence, so they work in the credential-free backend — the one that runs
locally and in the serverless deployment — as well as in the Earth Engine one.

This file records what each source can answer, what it cannot, and exactly how
far each factor has been proven. Read the last section before telling anyone a
number here is real.

## The arithmetic

| | Factors | Share of 269 |
| --- | --- | --- |
| Earth Engine (needs a service account) | 24 | 8.9% |
| Open data (needs nothing) | 22 | 8.2% |
| **Real, together** | **46** | **17.1%** |
| Generated, and labelled as such | 223 | 82.9% |

The brief was ~9% → ~25%. This lands at 17%. The gap is ONS and EPC, and both
reasons are recorded below rather than rounded away.

## What each source answers

### planning.data.gov.uk — 11 factors, no key

MHCLG's Planning Data Platform. One `entity.geojson` query per dataset per
AOI; designations are static, so a designation series is one value repeated
across the window with `interpolated: false` on every point.

`green_belt_pct`, `conservation_area_pct`, `aonb_pct`, `national_park_pct`,
`sssi_pct`, `ancient_woodland_pct`, `article4_pct`, `brownfield_register_pct`,
`scheduled_monument_pct`, `listed_building_density`, `tpo_density`.

**The limitation that matters:** percentage-of-AOI factors are computed by
sampling a 32×32 grid inside the AOI and counting how many points fall inside
a returned entity — not by clipping polygons and taking areas. For a 1 km AOI
that resolution is about 30 m, which is fine for "roughly a third of this site
is green belt" and wrong for a boundary dispute. `_coverage()` says so in its
docstring, and the honest fix is Shapely on the server, which is a dependency
decision, not an oversight.

### HM Land Registry Price Paid — 7 factors, no key

One SPARQL query against `landregistry.data.gov.uk` returns every residential
transaction in the postcode district, and seven factors are derived from it:
`avg_sale_price`, `median_sale_price`, `transaction_count`, `new_build_share`,
`flat_share`, `price_change_yoy`, `price_growth_5yr`. Selecting all seven costs
one query, not seven — `_group_installer` memoises per AOI.

**The limitation that matters:** Price Paid is published by postcode, and the
smallest reliable unit is the postcode district (`GU1`, not `GU1 3AB`). A
5-hectare AOI therefore reports its district's market, not its own. That is
still useful and it is still real; it is not a valuation of the site. Months
with no sales are gaps, never zeros — a district with no transactions in
January did not sell houses for £0.

### data.police.uk — 4 factors, no key

Street-level crime, one call per month. `crime_density`,
`burglary_density`, `violent_crime_share`, `antisocial_share`.

**Two limitations that matter.** First, cost: a 15-year monthly series is 180
HTTP calls. It is cached per AOI, but the first query for a long window is
slow, and this is the clearest candidate in the catalogue for pre-aggregation
(TECHNICAL_PLAN.md §3.4). Second, accuracy: police.uk anonymises locations by
snapping each crime to a nearby map point, so a small polygon measures its
neighbourhood rather than itself. Below roughly 500 m across, read these as
context, not as site facts. Future months come back as gaps because the data
is published about two months in arrears.

### EPC register — 6 factors, needs a free key

`epc_mean_sap`, `epc_band_mode`, `epc_below_c_share`, `epc_potential_uplift`,
`mean_floor_area`, `heat_pump_share`.

These are **written but not registered** unless `EPC_API_EMAIL` and
`EPC_API_KEY` are set. The key is free and self-service from
[epc.opendatacommunities.org/docs/api](https://epc.opendatacommunities.org/docs/api);
no such account exists yet, and creating one is a registration in someone's
name, which is not a call to make unilaterally. Set the two variables and the
six factors register themselves at startup with no code change.

### ONS — written, not registered

`ons_series()` queries the ONS Beta API for a dataset over the AOI's local
authority. It is not wired to any factor, and that is deliberate: ONS publishes
private rents, workplace earnings and the affordability ratio as **spreadsheets
on a release page**, not as Beta API datasets with stable per-area endpoints.
Registering a factor against a guessed dataset ID would put it in
`real_factor_ids` — a real-data promise made in the UI, before the query — and
then fail on every request. A factor that is going to fall back should not
claim to be real first.

The real fix is a scheduled job that downloads each release, parses it, and
stores it by local authority. That is the ingest tier, and it is the single
largest remaining item for lifting the real share past 25%.

## Verification status: read this

Every factor above is marked `status: "written"`, not `"verified"`. That
distinction is carried through `open_data.SOURCE_STATUS` →
`routes_catalog.REAL_SOURCES` → each factor's `provenance` in `/api/catalog`
→ the factor browser, where the ratio bar splits real into verified and
written and a written factor's dot is hollow rather than filled. It reaches
the user, not just the code.

`python3 scripts/audit_catalogue.py` prints the whole picture and checks it;
`tests/test_catalogue_audit.py` runs the same checks in CI, so a factor cannot
quietly acquire a claim nobody backed.

- **written** — implemented against the API's documented shape and covered by
  tests that feed it recorded fixtures. The parsing is proven. The endpoint is
  not.
- **verified** — someone ran it against the live service and checked the
  answer was plausible.

Nothing here is verified because **the environment these integrations were
written in cannot reach any of the five hosts**. Outbound HTTPS goes through a
proxy that answers `403` to `CONNECT` for anything outside a short allowlist
(GitHub, npm, PyPI). `planning.data.gov.uk`, `landregistry.data.gov.uk`,
`data.police.uk`, `api.postcodes.io` and `epc.opendatacommunities.org` are all
denied. Fixtures were the only honest option.

### Promoting a factor to verified

On any machine with normal internet access:

```bash
python3 scripts/check_open_data.py                  # all sources, Guildford
python3 scripts/check_open_data.py --source police --months 6
python3 scripts/check_open_data.py --json > /tmp/open-data-check.json
```

The script does not report "the request returned 200". For each factor it
asserts the point count matches the requested steps, values fall inside the
catalogue's declared range for that factor, and at least one point is not a
gap — an all-gaps series is the shape a broken query returns and must not read
as success. Exit status is 0 only if every check passed.

When it passes, change that source's `_mark(...)` call in `open_data.py` from
`"written"` to `"verified"` and add a row here:

| Source | Verified on | AOI | By |
| --- | --- | --- | --- |
| _(none yet)_ | | | |

A verification with no date is a claim, not a record.

## If a source breaks

It degrades; it does not fail. `routes_catalog._series_for` catches anything
raised here, falls back to `series.generate_series`, and records both the
fallback (`source: "generated"`) and the cause (`error`) in the response. One
dead endpoint costs one factor its realness for that request — it never blanks
a report that has eleven other factors in it. `tests/test_open_data.py` covers
that contract end to end, because it is the property that makes a half-real
catalogue safe to ship.
