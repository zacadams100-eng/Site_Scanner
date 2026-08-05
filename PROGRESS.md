# Progress log

A running log, appended to each session. Newest entry at the top. Nothing here
is overwritten, so the history of what was true when stays visible.

---

## 2026-08-05 (second pass) — Phase 2, and the gaps the brief still had

Went back through the brief looking for what was genuinely missing rather than
what was already built. Three things were, all in Phase 2.

### Rate limiting (`ratelimit.py`)

There was none, and the API is public, unauthenticated, and calls upstreams
with quotas shared across every user. One script in a loop could spend an
Earth Engine budget that belongs to everybody.

A cost-weighted sliding window per client. Costs are per route because the
routes are not comparable — `/api/catalog` is a cached dictionary at 0.5,
`/api/series` can be twenty-four upstream calls at 6.0. Charging them equally
either throttles browsing or fails to throttle work.

Three decisions worth recording:

- **Sliding window, not a token bucket.** A bucket lets a client spend its
  allowance instantly and then starve, which for an interactive map means the
  fourth shape you draw fails while you watch. A window degrades more gently.
- **Rejected requests are not counted.** Otherwise a client already over the
  limit holds itself over by retrying, turning a one-minute limit into a
  permanent ban.
- **Tracked clients are bounded.** `X-Forwarded-For` is forgeable, so an
  unbounded map of clients would make this middleware the memory exhaustion it
  exists to prevent.

**What it does not do:** the counters live in the process, so on Vercel the
effective limit is per instance, not per deployment. That makes it a guard
against one client hammering one instance, not a global budget. A real budget
needs shared state (Redis, Vercel KV) — a dependency and an account, for a
service with no users yet. `DEPLOY.md` already makes the same argument about
the response cache. Documented rather than dressed up, as the brief asks.

### Staged loading (`LoadingSequence.tsx`)

A frozen "Reading the site…" for eight seconds reads as broken; the same eight
seconds narrated reads as work. The stages are the real ones in the order the
backend performs them, and the sequence holds on its last message rather than
implying completion — the response arriving is the only thing that knows when
it is done. Past nine seconds it says the data source is slow, because at that
point that is more useful than another verb.

### Debouncing (`store.ts`)

Aborting an in-flight request already stopped answers arriving out of order,
but the request had still been *sent* — toggling three factors fired three
round trips, two of which the server did the work for and nobody read. Now
coalesced over 180ms, below the ~250ms where a delay starts to feel like lag.

Implemented with a generation counter rather than a cleared timeout: clearing
a pending timeout leaves its promise permanently unresolved, which quietly
leaks one per keystroke.

### Latency profile — and why the numbers below are not the real ones

Measured locally, 4 factors x 180 months, draw to report:

| | median |
| --- | ---: |
| uncached | 31 ms |
| cached | 31 ms |
| `/api/ask` | 8 ms |

Against targets of 8 s uncached and 2 s cached, that looks like a rout. It is
not, and the number should not be quoted. **This measures `series.py`, the
generator** — the sandbox proxy blocks Earth Engine and all five open-data
hosts, so nothing here touched a network. The real cost of a real factor is
one upstream round trip, and the honest profile needs a machine with open
egress. That, not the arithmetic, is the slow step.

What the measurement does establish: nothing in the app's own request path —
geometry validation, 180-month generation, annual rollup, the cell grid — is
anywhere near the budget. Any latency a user sees is upstream.

### Mobile

Checked at iPhone 13 viewport in a real browser rather than by reading CSS: no
horizontal overflow, tool rail usable, report panel present as a bottom sheet,
viewport meta correct.

### Not attempted, and why

Phase 5's monitoring/alerts, AR mode, multiplayer cursors and cross-site
pattern mining all need something this product does not have — accounts,
persistence, a scheduler, or usage volume. Building any of them now would add
a subsystem with no user. Phase 5's confidence overlays are the best next
candidate: the data already carries `months_observed` and `confidence`, so it
is a rendering job rather than a new pipeline.

---

## 2026-08-05 — Phase 0 inventory, and natural-language querying

### Orientation: the brief describes an older product

The improvement brief describes a Leaflet frontend, `ee-backend/app.py`, a
"Contour" brand on near-black with a gold accent, and `site-scanner.html` as
the live app. None of that is current, and the brief itself says to verify
rather than assume. What is actually here:

| Brief says | Actually |
| --- | --- |
| Leaflet frontend | React + MapLibre GL (`web/`), vector basemap |
| `ee-backend/app.py` | `app.py` at repo root; `mock_ee_backend.py` is the credential-free twin |
| `site-scanner.html` is the app | Kept for reference only; superseded by `web/` |
| Near-black + gold `#D9A83C` | Repaletted — see `BRAND.md`; the gold was deliberately dropped |
| "Year slider, partial" | Full 180-step monthly timeline with scrubbing and sparklines |

Several Phase 1–4 items were already done before this session: the cache layer
(`cache.py`, keyed on geometry hash + factor + range), CSV/PDF-style export
(`web/src/lib/exports.ts`), compare mode (`Compare.tsx`), permalink round-trip
(`lib/permalink.ts` with tests), boundary upload, anomaly-style callouts
(`insights.py`), and CI (`.github/workflows/ci.yml`).

### The single most important fact: what is real

Measured, not estimated — `scripts/audit_catalogue.py` and the registries in
`routes_catalog.REAL_SERIES`.

| | Count | Notes |
| --- | ---: | --- |
| Factors in the catalogue | 269 | `catalog.py`, 44 bases |
| Have a real implementation | **46** | 17% of the catalogue |
| — Earth Engine | 24 | `ee_series.FACTOR_COVERAGE` |
| — Open data | 22 | `open_data.py`: planning.data.gov.uk, Land Registry, police.uk |
| Return generated data | 223 | `series.py`, labelled `source: "generated"` everywhere |

**On the deployed URL, only the 22 open-data factors can be real.** The 24
Earth Engine factors need `app.py`, a service account and a container; the
Vercel function deliberately excludes `app.py` and `ee_series.py` because
`earthengine-api` will not fit a serverless bundle. Cloud Run is blocked on
Google requiring a billing account before Cloud Run, Cloud Build or Artifact
Registry can be enabled at all — see `DEPLOY.md §0`. Nothing in this repo can
work around that.

Only **1** factor is marked `verified` rather than `written` (NDVI, checked by
hand against live Earth Engine). The other 45 are implemented and unit-tested
but have not been confirmed against the live upstream. `scripts/check_open_data.py`
and `python3 -m ons.job --check` are what turn `written` into `verified`, and
both need ordinary internet — this sandbox's proxy blocks the upstreams.

Eleven Sentinel-2 factors carry a licence warning: `sentinel2_sr` is recorded
as CC BY-SA 3.0 IGO with `commercial="verify"`, and share-alike on a commercial
derived product would be a real constraint. `docs/licensing/DECISION-LOG.md`
has the branches. Still unresolved.

### Built this session: natural-language querying

The brief calls this "the single highest-differentiation feature". It did not
exist — no `/api/ask`, no query input, nothing.

`nlq.py` parses a question against the catalogue and answers it **from the
series**, not from a language model. That ordering is the whole design:

- The parser picks factors and a time range from the question text.
- The answer is computed arithmetically from the returned annual rollups.
- A model, when `ANTHROPIC_API_KEY` is set, only ever *rephrases* an answer
  that was already computed. It is never asked what the numbers are.

So the deployed URL — which has no API key — gives real answers, and a wrong
model cannot invent a number. This matches the rule the project already holds
for `/api/summary`: `generated_by` says who wrote the prose, and the prose is
constrained by data either way.

Refusals are part of the feature. The answer says so when the underlying
factor is generated, when the year range has no observations, and when a
change is too small relative to the year-to-year spread to be worth calling a
trend. Narrating noise would be the easiest way to make this feature
impressive and useless.

### Decisions and trade-offs

**Deterministic parsing over model-based routing.** A model would parse more
phrasings, but it cannot run on the deployed URL, and a feature that only
works with a key is a demo. Token-overlap scoring against factor name, group
and synonyms covers the phrasings in the brief's own example ("has tree cover
dropped near this site since 2019?"). The model path is an enhancement, not a
dependency.

**Answers use the annual rollup, not the monthly series.** Monthly values
carry seasonality that swamps a trend — a February-to-August comparison is a
season, not a change. The rollup already handles partial years and carries
`months_observed`, which the answer uses to caveat itself.

### What I would do next

1. Resolve the Sentinel-2 licence question. An hour of reading, and it gates
   commercial use of 11 factors.
2. Run `scripts/check_open_data.py` somewhere with ordinary internet — that
   moves 22 factors from `written` to `verified`, or names which integrations
   are wrong. Expect some URLs to have moved.
3. Earth Engine on Cloud Run, once billing exists. The image builds and serves;
   only billing is missing.

### Risks worth knowing

- The open-data factors call third-party APIs at request time. They are cached,
  but a slow upstream is a slow response, and `data.police.uk` in particular is
  not fast.
- Earth Engine remains registered non-commercial. `TECHNICAL_PLAN.md §8.9` and
  `BLOCKERS.md` cover the mitigation (ingest-then-store), which is built but
  unused.
