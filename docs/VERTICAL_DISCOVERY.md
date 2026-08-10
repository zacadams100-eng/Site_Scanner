# How land-specific is Contour, actually?

A vertical-discovery exercise, answered from the repository rather than from
intuition. The strategic question was: *is Site Scanner the company, or the
first application of a general geographic evidence engine?*

The code has a clearer opinion than expected.

---

## 1. The engine is already generic — measured by imports

| Module | Domain imports |
| --- | --- |
| `claims.py` | **none** |
| `brief.py` | **none** |
| `geometry.py` | **none** |
| `historical/metrics.py` | **none** (`statistics` only) |
| `historical/rules.py` | `historical.metrics` |
| `radar.py` | `insights` — **does not import `catalog`** |
| `comparison.py` | `radar` |
| `evidence.py` | `catalog`, `licensing` |

The evidence engine — states, coverage, claim boundary, investigations,
comparison, historical metrics, the Brief — has **no knowledge of land,
property or England**. `radar.py` never imports the catalogue; it receives
factors, evidence and thresholds and would run identically over a mine, a
corridor or a coastline.

Only `evidence.py` reaches into `catalog`, and only for display metadata
(factor name, base, licence). That is a presentation dependency, not a
semantic one.

**This was not planned as a platform.** It is a side effect of the discipline
that produced it: every rule that tried to know too much was pushed out of the
engine because it made the engine untestable. The result is that the generality
is real rather than aspirational.

---

## 2. The working satellite half is 100% global

| Registry | Factors | Global sources | UK-only sources |
| --- | --- | --- | --- |
| Earth Engine (`ee_series`) | 27 | **27** | **0** |
| Open data (`open_data`) | 28 | 0 | 28 |

Every Earth Engine implementation — Sentinel-2 (11 indices), ERA5-Land (8),
MODIS LST (3), ESA WorldCover (2), JRC surface water (3) — is a **global**
dataset. None of it knows about England.

That is the half carrying the historical chain, `hist-1`, the baseline
methodology and the CI verification job. **The most developed part of the
product is the part that already works anywhere on Earth.**

The 28 UK-only factors are open-data registries: flood zones, designations,
Land Registry, planning, crime, EPC. Those *are* the land vertical.

Across the whole catalogue: **91 of 271 factors (34%) come from global
sources**; the remaining 180 are UK registries, concentrated in Property
market (17), Planning & consents (17), Buildings & fabric (17) and Community &
services (21) — groups that only exist because the first vertical is land.

---

## 3. Where the UK coupling actually lives

Three places, and they are small:

1. **`catalog.py`** — 45 bases and `ENGLAND_BBOX`.
2. **`open_data.py`** — the UK registry fetchers.
3. **Three data structures inside `radar.py`** — `TOPICS` (flood, water,
   ground, terrain, vegetation, ecology, planning), `INVESTIGATIONS` (flood
   risk assessment, ecological appraisal, ground investigation…) and `RULES`.

Point 3 is the interesting one. `TOPICS` and `INVESTIGATIONS` are
land-development vocabulary living inside an otherwise domain-blind engine —
but they are **data, not logic**. A different vertical would supply a different
dict. `radar.assess()` would not change.

The England gate is one bbox check in `routes_catalog` returning a 400.

---

## 4. The one real architectural blocker: geometry is polygon-only

`geometry.py` raises on anything that is not a `Polygon` or `MultiPolygon`:

```
Unsupported geometry type {geom_type!r} — expected Polygon or MultiPolygon
```

Every downstream assumption follows: `area_ha`, the 250,000 ha AOI limit, the
H3 cell grid, `reduceRegion` over a ring, the coverage fractions.

This is the concrete finding that separates the proposed verticals into two
groups, and it is not a naming problem:

| Vertical | Geographic object | Expressible today? |
| --- | --- | --- |
| Site Scanner | polygon | **yes** |
| Mine Scanner | polygon (licence block / AOI) | **yes** |
| Habitat Scanner | polygon (parcel, reserve) | **yes** |
| Field Scanner | polygon (region) | **yes** |
| Route Scanner | **line + buffer** (corridor) | **no** |
| Coast Scanner | **line** (shoreline) | **no** |

Corridors and coastlines are linear objects. A corridor can be faked as a
buffered polygon, but then "what does this corridor intersect, and where along
it" has no answer — the interesting output is *distance along the line*, which
the current model cannot express. Coastal change is worse: shoreline retreat is
a measurement of how a *line* moved, and a polygon cannot represent it.

So Route and Coast are not "the same engine with different factors". They need
a second geometry model and a per-segment coverage concept. That is a real
piece of work, and it is worth knowing before either appears on a roadmap.

---

## 5. What I cannot answer from here

The discovery exercise asked for scoring across market size, willingness to
pay, competition, credibility and regulatory complexity.

**I have no way to check any of those.** This environment reaches GitHub, npm
and PyPI and nothing else — no market data, no competitor products, no pricing.
Producing a scored table would mean inventing numbers that look researched, in
a document intended to inform a commercial decision. That is the same failure
the product spends its whole architecture preventing, so the table is not here.

What the repository *can* score:

| Vertical | Technical fit today | Data already implemented | Blocker |
| --- | --- | --- | --- |
| Site Scanner | complete | 55 factors | none |
| Habitat Scanner | **high** | vegetation, land cover, water, LST, canopy — all global, all built | vocabulary only |
| Mine Scanner | medium-high | S2 indices, SAR, terrain, water | needs geology/spectral depth |
| Field Scanner | high | terrain, weather, land cover, water | vocabulary only |
| Route Scanner | **low** | factors exist | **linear geometry** |
| Coast Scanner | **low** | water, land cover, temperature | **linear geometry + shoreline method** |

The market claims in the brief — existing UK constraint-screening products,
specialist satellite mining platforms — I take as given and cannot verify.

---

## 6. What the evidence actually suggests

**Habitat Scanner is the cheapest second vertical, by a wide margin.** Its
entire factor set is already implemented and global: NDVI, EVI, NDMI, NBR
(burn), land cover, canopy height, surface water, LST. The historical chain —
baseline, change, sufficiency, threshold — is the ecological question in its
native form. What it needs is a different `TOPICS`/`INVESTIGATIONS` vocabulary
and one or two new rules. **No new data sources, no new geometry, no engine
change.**

That is worth knowing regardless of which vertical is commercially best,
because it means the platform hypothesis is **testable cheaply**. Building a
second vertical is how you find out whether the engine is genuinely reusable,
and doing it against the factor set that is already live and already global is
the lowest-cost version of that experiment.

It would also settle a question no amount of reasoning will: whether
`TOPICS`/`INVESTIGATIONS` living inside `radar.py` is sufficient separation, or
whether a vertical needs its own module. The answer is cheap to obtain and
expensive to guess.

---

## 7. What this does not change

Nothing in this document argues for building any of it now. The immediate
roadmap — Investigation Workspace, then EXPLORE/SCAN/COMPARE — is unaffected,
and both make the engine *more* reusable rather than less: the workspace is a
view over `evidence`/`claims`, and the three-section shell is navigation.

The one thing worth doing early, if the platform framing is taken seriously, is
**not** renaming anything. It is keeping `TOPICS` and `INVESTIGATIONS` as
injected data rather than letting land vocabulary leak further into
`radar.py` — which is a discipline, not a refactor.
