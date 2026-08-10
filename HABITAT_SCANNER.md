# Habitat Scanner — product definition

Scanner #2. Written before the rules, because the rules are the easy part and
the decisions are not.

**The short version: Habitat v1 ships one flagged check and five informational
readings.** That is thin, and it is thin for a reason — most of the ecological
questions a habitat scanner *should* answer cannot be answered defensibly from
the evidence this repository has. Those are named in §6 rather than filled with
invented thresholds.

---

## 1. The professional question

> **What has changed in this habitat's condition, how well is that
> established, and what should an ecologist look at first?**

Habitat is not Land with ecological colours. The differences are real:

| | Land | Habitat |
| --- | --- | --- |
| Subject | a site, parcel or landholding | a habitat parcel, reserve or landscape unit |
| Reader | developer, planner, consultant | ecologist, land manager, conservation practitioner |
| Question | what constrains what can be done here | what has changed in what is here |
| Evidence | designations, planning, flood, market | satellite observation of the surface itself |

The land scanner's ecological content is a *constraint check* — is there an
SSSI, is there ancient woodland. Habitat asks a different question of different
evidence: what do fifteen years of observation say about the vegetation
actually growing here.

## 2. What Habitat explicitly does not promise

- **No habitat classification.** Contour cannot say "this is lowland
  calcareous grassland". UKHab and Phase 1 classification is field survey work.
- **No condition assessment against a standard.** "Favourable condition" is a
  defined term with defined criteria assessed on the ground.
- **No restoration opportunity or priority.** That is a suitability judgement
  and EM8 forbids it — the same reason the land templates were reframed away
  from "is this site worth pursuing".
- **No biodiversity metric.** BNG units are a statutory calculation from a
  habitat classification Contour does not have.
- **No score of any kind** (EM7).

---

## 3. Factor inventory — measured, not assumed

The previous audit claimed "27 relevant Earth Engine factors, no new sources
required". **Verified: 27 exist. "Relevant" needed qualifying.**

The qualifier is **spatial resolution against the size of a habitat parcel**:

| Source | Resolution | Parcel-scale? |
| --- | --- | --- |
| Sentinel-2 | 10 m | **yes** |
| ESA WorldCover | 10 m | yes, but 2 years only |
| JRC surface water | 30 m | yes, for context |
| MODIS LST | 1 000 m | **no — regional** |
| ERA5-Land | 9 000 m | **no — regional** |

A 9 km ERA5 pixel over a 20 ha reserve is one number for a large part of the
county. Reporting it as a property *of the parcel* would be a false precision
of exactly the kind this product exists to avoid. Habitat therefore excludes
ERA5 and MODIS from v1 rather than presenting regional climate as site
evidence.

### Factors Habitat uses

| Factor | Source | Metric | Temporal | Spatial meaning | Used |
| --- | --- | --- | --- | --- | --- |
| `ndvi` | Sentinel-2 | vegetation vigour | 2017-03 → | 10 m, parcel | **rule + informational** |
| `ndmi` | Sentinel-2 | canopy/soil moisture | 2017-03 → | 10 m, parcel | informational |
| `evi` | Sentinel-2 | vigour, dense-canopy corrected | 2017-03 → | 10 m, parcel | informational |
| `lc_tree_pct` | WorldCover | tree cover share | 2020–2021 | 10 m, parcel | informational |
| `lc_dominant` | WorldCover | modal land cover class | 2020–2021 | 10 m, parcel | informational |
| `water_occurrence` | JRC | surface water frequency | 1984–2021 | 30 m, context | informational |

### Factors deliberately excluded

| Factor(s) | Why |
| --- | --- |
| `air_temp_*`, `frost_days`, `growing_degree_days`, `humidity`, `soil_moisture`, `evapotranspiration` | ERA5-Land at 9 km — regional, not parcel |
| `lst_day`, `lst_night`, `lst_diurnal_range` | MODIS at 1 km — regional, not parcel |
| `nbr` | Implemented, but see §6 — burn severity needs dNBR and sourced thresholds |
| `ndbi`, `bare_soil_index`, `ndwi`, `savi`, `msavi`, `gndvi`, `chlorophyll_index` | Real and parcel-scale, but add no question v1 can answer |

Excluding a working factor is a decision, not an oversight. A scanner that
shows every available number is a data browser; one that shows the numbers
behind its questions is an evidence tool.

---

## 4. Topics

Five, each stating what it can and cannot conclude.

### `condition` — Vegetation condition
- **Question:** has vegetation vigour changed against its own historical
  baseline?
- **Evidence:** `ndvi`, Sentinel-2, 2017 onward, `hist-1` methodology
- **Investigation:** preliminary ecological appraisal
- **Establishes:** a quantified change in a spectral index over a defined
  baseline and recent period, with the observation count behind it
- **Does not establish:** habitat quality, condition status, cause, or that a
  change is ecologically adverse. Vigour falls for management, grazing, crop
  rotation and season as readily as for harm.

### `moisture` — Moisture condition
- **Question:** what does canopy and soil moisture look like across the record?
- **Evidence:** `ndmi`
- **Establishes:** a measured index value and its trend
- **Does not establish:** hydrological status, wetland condition, or drying.
  **No threshold** — see §5.

### `cover` — Land cover context
- **Question:** what is the recorded surface cover, and how much is tree?
- **Evidence:** `lc_dominant`, `lc_tree_pct`
- **Establishes:** the modal WorldCover class and tree share for 2020/2021
- **Does not establish:** habitat type, and **not change** — see §6.

### `water` — Surface water context
- **Question:** how often is surface water present here?
- **Evidence:** `water_occurrence`
- **Establishes:** the share of the record in which water was detected
- **Does not establish:** wetland status or hydrological function.

### `structure` — Vegetation structure
- **Question:** what does the dense-canopy-corrected index show?
- **Evidence:** `evi`
- **Establishes:** a second index reading, less saturated over dense canopy
- **Does not establish:** structure in the ecological sense — canopy layers,
  age, deadwood. The topic is named for what a user is looking for and states
  that the evidence is a proxy at best.

---

## 5. Thresholds

**One threshold, and it is not new.**

### `VEGETATION_CHANGE_INVESTIGATION_THRESHOLD` (reused, not copied)

| | |
| --- | --- |
| Metric | median NDVI, first three usable years vs last three |
| Direction | decline (negative change only) |
| Unit | per cent change from baseline |
| Comparison | `hist-1`, April–September window, medians throughout |
| Value | **−20 %** |
| Type | **Contour reporting threshold — product-defined** |
| Status | **not a regulatory or scientific standard** |
| Provenance | `historical/rules.py`, imported by Habitat rather than restated |
| Rationale | identifies changes large enough to warrant professional investigation, not evidence of ecological degradation |
| Limitation | a spectral index is not a measure of ecological condition; the threshold says when to look, never what was found |

Habitat **imports** the constant. Two scanners with two copies of one number is
how they drift apart, and the first symptom would be a brief and an app
disagreeing about what crossed.

### Thresholds deliberately not created

`moisture`, `cover`, `water` and `structure` produce **informational findings
with no threshold**. Each is a real measurement with no defensible line to draw
from anything in this repository, and an invented line would be the failure
this product spends its architecture preventing.

This follows the decision already taken for LST and built surface: *measure
first, judge only with a defensible basis.*

---

## 6. What Habitat should answer and cannot — yet

Named rather than filled.

| Question | Blocker |
| --- | --- |
| **Fragmentation / connectivity** | Requires patch-level spatial analysis — patch count, edge density, nearest-neighbour distance. The engine reduces a geometry to a series; there is no spatial-pattern capability. **A real engine gap, reported in §9.** |
| **Land cover change** | WorldCover covers 2020 and 2021 only, and those are **v100 and v200 — different products**. Differencing them measures an algorithm change. `ee_series.py` already records this trap. |
| **Burn history** | `nbr` exists, but burn severity needs *differenced* NBR and published severity classes. Neither is in the repository, and inventing dNBR classes would be a scientific claim. |
| **Habitat classification** | Field survey. Not remote sensing. |
| **Restoration opportunity** | A suitability judgement. EM8. Will not be built. |
| **Condition against a standard** | "Favourable condition" has defined criteria assessed on the ground. |

## 7. Coverage

**England**, same bbox as Land — not because Habitat is inherently
England-limited (its factors are global) but because that is where this
deployment has been exercised, and claiming global coverage on the strength of
a global dataset would be asserting something untested.

## 8. Investigation

One, reusing the id and metadata Land already uses because the professional
follow-up is genuinely the same check:

**Preliminary ecological appraisal** — habitat survey, protected species
scoping, and the baseline a BNG calculation is built on.

Triggered only by `habitat_vegetation_decline`. Informational readings raise
nothing, which is correct: a measurement that crossed no threshold prompts no
survey.
