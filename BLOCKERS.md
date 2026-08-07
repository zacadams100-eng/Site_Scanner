# Blockers

Things that cannot be finished from inside this environment, and what each one
actually needs. Written so nobody has to re-derive them.

Every item here has been taken as far as it can go without the missing piece —
written, tested against fixtures, and wired up so that supplying the missing
piece is the only remaining step.

---

## 1. No outbound network to anything except GitHub, npm and PyPI

**Affects:** the ONS ingest, the five open-data sources, Earth Engine, Vercel.

Outbound HTTPS goes through a proxy that answers `403` to `CONNECT` for
anything outside a short allowlist. Concretely:

```
$ python3 -m ons.job --check
FAIL private_rents    ProxyError: Tunnel connection failed: 403 Forbidden
FAIL affordability    ProxyError: Tunnel connection failed: 403 Forbidden
FAIL earnings         ProxyError: Tunnel connection failed: 403 Forbidden
FAIL census_2021      ProxyError: Tunnel connection failed: 403 Forbidden
FAIL imd_2019         ProxyError: Tunnel connection failed: 403 Forbidden
```

**What this means for the ONS job specifically.** The parser is tested against
workbooks that reproduce each release's shape — preamble rows, four different
names for the area column, suppressed values as `:` and `x`, dates as
`2024 JUL` and `Jul-24`. What is *not* tested is whether today's URL still
resolves, and **ONS rotates its `/current/` links on every release**, so
expect some of the five to be wrong. They are written from ONS's published URL
conventions, not from a successful fetch.

**To unblock:** on any machine with normal internet,

```bash
python3 -m ons.job --check     # which URLs resolve
python3 -m ons.job             # download, parse, write data/ons/*.json
```

Fix any URL that 404s by opening the dataset's landing page — every spec
carries one in `page` for exactly this — and copying the current file link.
The job is deliberately per-dataset: one dead link does not stop the other
four, and a failure leaves the previous data untouched.

The same applies to `scripts/check_open_data.py` for the five live sources,
which is what would promote those 22 factors from `written` to `verified`.

---

## 2. The "50% real" target is arithmetically out of reach from ONS alone

The instruction for the ONS job was to move real coverage "from roughly 17%
toward 50%". It does not, and no amount of spreadsheet ingest would. The
numbers, so the gap is a decision rather than a surprise:

| | Factors | Share of 269 |
| --- | ---: | ---: |
| Real today (Earth Engine 24 + open data 22) | 46 | 17.1% |
| Added by the ONS job once it has run | 8 | |
| Derived from it (`rental_growth_yoy`, `gross_yield`) | 2 | |
| **Real after this work** | **56** | **20.8%** |
| Needed for 50% | 135 | |
| **Still short** | **79** | |

**Why ONS cannot close it.** ONS and MHCLG publish a handful of
local-authority indicators relevant to this catalogue — rents, earnings,
affordability, census age and household structure, deprivation. That is about
a dozen factors, and this job takes essentially all of them. The other 213
generated factors are things ONS does not publish at all: soil texture, flood
depth, grid headroom, canopy height, radon, mobile coverage, chargepoint
density.

**What would actually reach 50%,** in descending order of factors per unit of
work:

| Source | Factors | Cost |
| --- | ---: | --- |
| EPC register | 6 | A free key. Already written; registers itself the moment `EPC_API_EMAIL` and `EPC_API_KEY` exist. |
| Environment Agency (flood zones, water quality, abstraction) | ~18 | Real work; open APIs, no key |
| OS NGD / OS Open (buildings, greenspace, transport) | ~15 | Free API key, generous limits |
| DEFRA / Natural England spatial services | ~12 | Open WFS endpoints |
| BGS (soil, geology, radon) | ~10 | Open, some licensing to confirm |
| DfT / NaPTAN / rail usage | ~10 | Open CSV releases; another spreadsheet job |
| NESO / DNO grid capacity | ~8 | Open, but per-DNO and inconsistent |
| Ofcom / chargepoint registry | ~7 | Open APIs |

Roughly 86 factors across eight sources — which would clear 50%. Each is the
same shape of work as `open_data.py` or `ons/`, so the mechanism exists and it
is a question of how many weeks to spend, not of whether it is possible.

**Nothing was faked to close the gap.** Registering a factor against a source
that cannot answer it would make the catalogue claim real data in the UI and
then fail on every request — worse than the honest label it has now.

---

## 3. Census tenure and qualifications are deliberately not guessed at

`ons/datasets.py` ingests the Census 2021 first-results release, which carries
population, households and age structure. Tenure (`tenure_owner_pct`,
`tenure_social_pct`, `tenure_private_rent_pct`), `economically_active_pct` and
`degree_qualified_pct` are in **separate topic-summary releases** whose URLs
could not be confirmed from here.

Five more factors, and it is one dictionary entry each in `ons/datasets.py`
once someone can open the ONS site and copy the right link. Guessing at them
would have produced five specs that fail on every run and five factors that
promise data they cannot deliver.

---

## 4. ~~No Vercel account, so there is still no live URL~~ — RESOLVED 2026-08-05

**This is done.** The app is deployed at https://site-scanner-pi.vercel.app and
`npx vercel deploy --prod` from the repo root ships a new build. The frontend
and the credential-free API both run there; only Earth Engine does not, and
that is §5's problem, not this one.

This entry sat here stale for two days after the fact, contradicting
`HANDOFF.md` on the same page. It is kept rather than deleted because a
blocker's history is the useful part: it was written 2026-08-04, the deploy
landed 2026-08-05, and nobody came back to it.

*(Not re-verified from this sandbox — `vercel.com` is behind the same proxy
block as everything in §1, so this records what the deploy session reported,
not a fresh check of the URL.)*

---

## 5. No Earth Engine credentials, so the fetch stage is unmeasured

`docs/INGEST-BENCHMARK.md` measures the whole pipeline with a synthetic
generator standing in for the fetch. That stand-in is 22% of measured time and
it is the one number in the benchmark that means nothing — a real Earth Engine
export for one tile could plausibly take minutes and dominate everything else.

Every other stage is real: COG writing, H3 aggregation, the database merge,
and the tiled-versus-untiled equivalence are all measured against actual work.

**To unblock:** a service-account key, and then re-run the benchmark. It is one
command and the write-up says exactly which figures to replace.

---

## 6. The Sentinel-2 licence question is a decision, not a task

`docs/licensing/DECISION-LOG.md` has both emails drafted and the architectural
consequence of every possible reply worked out in advance. Nobody in this
environment can send an email or accept a licence. Send the ESA one first — it
is the cheaper question and it may make the Google one unnecessary.

---

## 7. The EA's spatial layers need their service names confirmed

Four factors now come from the Environment Agency's **Hydrology API** —
`ea_rain_total`, `ea_rain_max_daily`, `ea_rain_wet_days`, `ea_rain_dry_days`
in `ea_hydrology.py`. That API is keyless, documented, and returns JSON, so it
could be written against its reference with reasonable confidence.

The rest of the EA's catalogue is **not** in that shape. Flood Zone 2 and 3,
Risk of Flooding from Surface Water, reservoir inundation, abstraction
availability and water stress are published as *spatial* services — WFS and
OGC API Features under `environment.data.gov.uk/spatialdata/…` — and each one
is addressed by a service path and a typename that could not be confirmed from
here, because the host is behind the same proxy block as everything else in §1.

**They were deliberately not registered.** BLOCKERS §2 already states the rule
and it applies exactly: registering a factor against an endpoint that cannot
answer it makes the catalogue claim real data in the UI and then fail on every
request, which is worse than the honest "generated" label those six carry now.
Guessing six typenames would have produced six factors that 404 forever and a
coverage figure that looked better than the product.

**To unblock,** on any machine that can reach the host:

```bash
curl -s "https://environment.data.gov.uk/spatialdata/flood-map-for-planning-rivers-and-sea-flood-zone-3/wfs?service=WFS&request=GetCapabilities" | grep -i '<Name>'
```

That prints the real typenames. The six factors below are the ones waiting on
them; each needs a polygon intersection against the AOI and a percentage,
which is exactly what `open_data.planning_series` already does for the eleven
planning designations — the mechanism exists, only the addresses are missing.

| Factor | Layer needed |
| --- | --- |
| `flood_zone2_pct` | Flood Map for Planning, Flood Zone 2 |
| `flood_zone3_pct` | Flood Map for Planning, Flood Zone 3 |
| `surface_water_risk` | Risk of Flooding from Surface Water |
| `reservoir_risk` | Risk of Flooding from Reservoirs |
| `abstraction_availability` | Water resource availability (CAMS) |
| `water_stress_class` | Water stressed areas |

Roughly a day's work once the names are known, and it would take real coverage
from 50 factors to 56.

**`spi_3month` is a separate refusal, and not a blocker.** A proper SPI needs
a gamma distribution fitted per calendar month and transformed to a normal
deviate. A z-score of three-month totals is not that — rainfall is strongly
right-skewed, so the two disagree most in the dry tail the index exists to
measure. It stays generated until someone implements the real thing.
