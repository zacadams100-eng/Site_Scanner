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
| Open data, live (needs nothing) | 22 | 8.2% |
| ONS, from the scheduled job | 8 | 3.0% |
| Derived from the above | 2 | 0.7% |
| **Real, together** | **56** | **20.8%** |
| Generated, and labelled as such | 213 | 79.2% |

The ONS rows count only once `python3 -m ons.job` has been run somewhere with
open egress; until then those factors keep saying "generated", which is the
whole point of registering on what the store holds rather than on what the
specs hope for. BLOCKERS.md §2 has the arithmetic for getting past this.

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

### ONS — a scheduled spreadsheet job, not an API client

ONS publishes private rents, workplace earnings, the affordability ratio and
the census as **spreadsheets on a release page**, not as API datasets with
stable per-area endpoints. There is nothing for a live client to call, which is
why these factors stayed generated while the rest of this module went real.

`ons/` is the fix the earlier version of this document called for: a scheduled
job (`.github/workflows/ons-refresh.yml`, monthly) downloads each release,
parses it, and writes `data/ons/<dataset>.json`. `ons_store.py` reads those
files at request time — no network, no database, so it works in the serverless
deployment exactly as it does locally.

| Dataset | Publisher | Factors |
| --- | --- | --- |
| Price Index of Private Rents | ONS | `rental_median` |
| House price to earnings ratio | ONS | `affordability_ratio` |
| ASHE place-of-work earnings | ONS | `earnings_median` |
| Census 2021 first results | ONS | `households`, `age_median`, `age_under16_pct`, `age_over65_pct` |
| Indices of Deprivation 2019 | MHCLG | `imd_score` |

Two more are derived from what that puts in the process and are published by
nobody: `rental_growth_yoy`, and `gross_yield` — annual rent over sale price,
combining the stored ONS rent with the live Land Registry median.

**Three limitations that matter.** These are **local authority** figures, so a
5-hectare AOI reports its district; that is real data and it is not a
measurement of the site. Some are **years old** — the census is 2021,
deprivation 2019 — and every value carried across months is flagged
`interpolated` so a chart cannot imply it was measured monthly. And **the URLs
are unverified**: ONS rotates its `/current/` links on each release, and
nothing here has ever been fetched. Run `python3 -m ons.job --check` first.

See BLOCKERS.md §2 for why this reaches 21% real rather than the 50% asked for,
and which eight sources would actually close that gap.

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

---

## Verification log

A verification with no date is a claim, not a record. Each run goes here.

### 2026-08-09 — first live run

Run from Google Cloud Shell (ordinary outbound internet; the usual development
sandbox reaches none of these hosts). AOI: 1.2 km square near Guildford,
51.235 N 0.570 W. Window: six months ending 2026-05.

**21 of 24 open-data checks passed.** Observed values, so a later reader can
tell this from a tick:

| Factor | Observed 2026-05 |
| --- | --- |
| `median_sale_price` | £425,000 |
| `transaction_count` | 32 |
| `new_build_share` | 0.0% |
| `flat_share` | 50.0% |
| `crime_density` | 230.0 per km² |
| `burglary_density` | 5.0 per km² |
| `violent_crime_share` | 24.6% |
| `antisocial_share` | 16.7% |

Nine factors promoted to `verified` in `open_data.VERIFIED`. The catalogue's
verified count moved from **1 to 9** — the first time it has moved since NDVI.

**Not promoted, and why.** `avg_sale_price` is in the same group and almost
certainly worked, but its line was outside the captured output and "almost
certainly" is not the standard. The eleven planning designations and the two
flood-zone factors are in the same position: the report kept only the last 14
lines of the check, so their results scrolled off. `verify.py` now keeps the
whole output. Re-run and they can be promoted properly.

**`price_change_yoy` and `price_growth_5yr` reported FAIL** — "every point is a
gap". Correct arithmetic, wrong question: they derive from 13 and 61 months of
history and the check asked for six. `check_open_data.py` now reports that as
"not testable in this window" and names the `--months` value that would test
it, rather than as a failure.

**The flood-zone attribute check passed**, confirming `flood-risk-type` is the
real attribute name on planning.data.gov.uk. That was the riskiest unverified
guess in the repository — it was taken from a published schema and had never
been seen in a live response, and had it been wrong the app would have been at
risk of reporting 0% flood risk on a floodplain.

**ONS: two moved, three rate limited.** `private_rents` and `imd_2019` return
404 and genuinely need new URLs. `affordability`, `earnings` and `census_2021`
returned 429 — Too Many Requests — which is not a dead link, and the check now
backs off and retries rather than reporting all five as broken.

**Earth Engine was never actually tested.** It reported a failure that was
really a setup step: `GOOGLE_APPLICATION_CREDENTIALS_JSON` was not loaded.
`verify.py` now checks the variable the app actually reads and says
`source ./setup.sh` instead of showing red.

### 2026-08-09 (second run) — the planning designations

`check_open_data.py --source planning`, same AOI. **12 of 13 passed, and that
number is misleading.**

| Factor | Observed | Promoted? |
| --- | --- | --- |
| `conservation_area_pct` | 53.3% | yes |
| `scheduled_monument_pct` | 0.9% | yes |
| `green_belt_pct` | 0.8% | yes |
| `article4_pct` | 0.0% | no |
| `national_park_pct` | 0.0% | no |
| `aonb_pct` | 0.0% | no |
| `sssi_pct` | 0.0% | no |
| `ancient_woodland_pct` | 0.0% | no |
| `listed_building_density` | 0.0 | no |
| `tpo_density` | 0.0 | no |
| `flood_zone2_pct` | 0.0% | no |
| `flood_zone3_pct` | 0.0% | no |
| `brownfield_register_pct` | **TypeError** | bug, fixed |

**Why ten passes were not promoted.** `planning_series` returns 0.0 when the
platform sends back no entities. That is the right answer for a Guildford site
with no SSSI on it — and it is also exactly what a *misspelled dataset name*
returns. The two are indistinguishable from outside, so a run that only ever
saw zero has confirmed the code path and established nothing about whether we
asked for the right dataset.

Only the three non-zero results prove the query finds and clips real entities.
`check_open_data.py` now marks an all-zero result `~ok` and says so, rather
than letting it read as a verification.

**To settle the other nine:** run over somewhere they must be non-zero.

```bash
python3 scripts/check_open_data.py --source planning --lat 50.90 --lon -0.60
```

That is inside the South Downs — national park and AONB both have to be
non-zero there, and a zero would be a real finding.

**The bug.** `brownfield_register_pct` died with
`TypeError: object of type 'float' has no len()`. The brownfield land register
publishes **points**, not polygons, and every fixture in the test suite was
written as a polygon, so `_coverage` reached `len()` on a coordinate. Fixed —
and deliberately fixed to *raise* rather than skip the points and return 0.0,
because "no brownfield land here" is a claim and "we cannot read this answer"
is a different one. The factor now falls back to labelled demo data until
someone implements it against the register's area attribute.

### 2026-08-09 (third run) — the biggest bug yet, found by a bad test location

The South Downs run never reached a single designation:

```
FAIL  locate — OpenDataError: no postcode near this area
Every other source is keyed off this lookup; stopping.
```

**`locate()` sent no `radius`, so postcodes.io used its 100 m default.** Any
AOI whose centroid sat more than 100 m from a postcode raised — and almost
every non-spatial source is keyed off this lookup, so roughly twenty factors
failed at once.

The AOIs that fail are farms, development plots, solar sites, woodland: open
countryside, which is most of what this product is for. A land-analysis tool
that cannot locate a field.

It could not have been found any other way. The sandbox cannot reach
postcodes.io, so no fixture would have caught it, and the default test AOI is
inside Guildford where a postcode is always within 100 m. It took one run over
real countryside.

**Fixed** by widening the search — 100 m, 500 m, 2,000 m (the API maximum) —
and then falling back to the outward-code endpoint, which is coarser but is
exactly what the Land Registry district query already uses, so the price
factors keep working on a moor.

The result now carries `within_m` and `precision`. That is not bookkeeping: a
site joined to a price index from a postcode 40 m away and one joined from
4 km away are different claims, and the second should be visible to whoever
reads the number. Surfacing it in the UI is not yet done.

An area with no outcode within 25 km still raises, and says "is this area
offshore?" — widening a search must not turn a genuine "this is the sea" into
a confident guess at a district 30 km away.
