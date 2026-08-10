# Factor classification — measurement, derived metric, judgement

Twenty-six factors in `catalog.py` carry names shaped like conclusions —
`suitability`, `score`, `potential`, `developable`, `best`. A differentiation
audit raised them because a catalogue full of verdicts describes Contour as a
land-opportunity platform regardless of what the evidence model says.

They are **not all the same problem**, and a mass rename would have destroyed
real information. This document classifies each one and says what should happen
to it.

**None of the 26 is currently a live factor.** All are generated demo data
(28 of 273 factors are real). Nothing here is being claimed about any site
today; every risk below is latent.

---

## The test used

> Does the factor's own definition require Contour to decide what counts as
> *good*?

- **No, and it has an external definition** → `MEASUREMENT`
- **No, but it combines inputs under weights someone chose** → `DERIVED_METRIC`
- **Yes** → `JUDGEMENT`

The unit is the strongest signal. `ha`, `%`, `kWh/kWp/yr`, `t/ha` describe the
world. `0–1` and `0–100` almost always mean someone normalised several things
against each other, and the interesting question is who chose the weights.

---

## JUDGEMENT — 5 factors

Each answers "is this site good for X". That is the one question Contour
exists not to answer, and no amount of provenance makes it safe.

| Factor | Declared as |
| --- | --- |
| `solar_farm_suitability` | "Irradiance, slope, aspect and grid distance combined" |
| `battery_site_suitability` | "Flat ground, grid headroom and access combined" |
| `woodland_creation_suitability` | "Soil, slope and designation constraints combined" |
| `warehouse_suitability` | "Flat, dry, accessible ground of usable shape" |
| `data_centre_suitability` | "Power, water, fibre and flood risk combined" |

These are per-site suitability scores. A user reading
`solar_farm_suitability: 0.81` has been given a recommendation, and the fact
that it arrives as a factor rather than as a headline makes it *harder* to
argue with, not easier.

**Recommendation: do not implement.** Not rename — implementing them at all
means shipping the thing EM7 and EM8 exist to prevent. Their inputs are already
in the catalogue as separate real measurements (`solar_ghi`, `slope_mean`,
`grid_headroom`, `flood_zone3_pct`), which is the honest form: show the
components, let the professional weigh them.

Guarded by `tests/test_factor_classification.py`, which asserts none is live or
read by a rule. See "The EM7 collision" below.

---

## DERIVED_METRIC — 10 factors

Legitimate to publish, but only with the methodology attached. Each combines
inputs under weights, and the weights are the claim.

| Factor | Unit | Who chose the weights |
| --- | --- | --- |
| `ground_risk_score` | 0–100 | **Contour** — "GeoSure bands combined into one screening number" |
| `insurance_peril_score` | 0–100 | **Contour** — "flood, subsidence and wind combined" |
| `solar_aspect_score` | 0–1 | **Contour** — aspect and shade into "favourability" |
| `transit_access_score` | 0–100 | **Contour** — stop density and service frequency |
| `timber_access_score` | 0–1 | **Contour** |
| `last_mile_score` | 0–1 | **Contour** |
| `freight_access_score` | 0–1 | **Contour** |
| `walk_score` | 0–100 | Third party — *Walk Score* is a proprietary index; **name needs a trademark check** |
| `rooftop_solar_potential` | MWh/yr | Contour — requires deciding which roof planes are "suitable" |
| `bng_uplift_potential` | units/ha | Defra metric defines the units; "creatable" assumes an intervention |

**`insurance_peril_score` is the most serious.** It combines *different perils*
into one number for a site. That is a site score with a narrower noun, and it
is the closest thing in the catalogue to the thing §14 forbids outright.
`ground_risk_score` is the same shape within one hazard family.

**Recommendation:** these need a published methodology and a `method_version`
before they could ever go live, exactly as `hist-1` does for historical
metrics — a composite without a stated formula is an opinion with a decimal
point. Until then they stay generated. `insurance_peril_score` and
`ground_risk_score` should be reconsidered on principle rather than fixed:
a cross-peril composite may simply not belong in this product.

`solar_aspect_score`'s note says "favourability", which is a judgement word
inside a `DERIVED_METRIC`; it sits on the boundary and should be re-read when
its methodology is written.

---

## MEASUREMENT — 11 factors

Real quantities with external definitions. The names look like judgements
because the *published dataset* names them that way, and renaming would break
the link to the source.

| Factor | Unit | Why it is a measurement |
| --- | --- | --- |
| `radon_potential` | % | Share of homes above the **statutory** action level — an external threshold, not Contour's |
| `solar_pv_potential` | kWh/kWp/yr | PVGIS model output, physical unit |
| `epc_mean_sap` | SAP | Mean of an externally defined rating |
| `epc_potential_uplift` | SAP points | Gap between two figures printed on the certificate |
| `imd_score` | score | ONS Index of Multiple Deprivation — "score" is the dataset's own word |
| `shrink_swell_score` | 0–5 | BGS GeoSure band, externally classified |
| `landslide_score` | 0–5 | BGS GeoSure band, externally classified |
| `bmv_land_pct` | % | Defra ALC grades 1–3a. "Best and most versatile" is the **statutory term** |
| `yield_potential_wheat` | t/ha | Modelled attainable yield (SoilGrids) |
| `yield_potential_grass` | t DM/ha | Modelled dry matter production |
| `developable_area` | ha | Measures **unbuilt area** — see below |

**Two naming problems worth fixing, without changing what is measured:**

- **`developable_area`** measures "area with no building on it — before
  constraints". It is unbuilt area. Calling it *developable* asserts that it
  could be developed, which is a planning judgement Contour has not made and
  cannot make. **Rename to `unbuilt_area`.** This is the audit's case A: a
  genuine measurement wearing a conclusion's name.
- **`shrink_swell_score` / `landslide_score`** are GeoSure *bands* on a 1–5
  scale, not scores. `_band` or `_class` would say what they are and would stop
  them reading as a Contour-computed number.

`bmv_land_pct` and `imd_score` keep their names. Quoting a statutory or
published term is not Contour making a judgement, and renaming would sever the
link to the source — which the evidence model cares about more.

---

## The EM7 collision

`tests/test_evidence_model.py` bans these substrings in **payload keys**:

```python
BANNED = ("score", "rating", "grade", "suitability", "overall", "index_of", "health")
```

`radar.assess()` puts factor ids into payload keys. No rule reads any of the 26
today, so EM7 passes. **The day one of them goes live and a rule reads it, EM7
fails on a legitimate factor name** — and the obvious fix under deadline is to
weaken the banned list, which is how the no-score invariant dies.

**EM7 is not weakened.** Instead `tests/test_factor_classification.py` asserts
the `JUDGEMENT` set is never live and never read by a rule, so the collision
cannot arise from that direction. For `MEASUREMENT` factors whose external
names contain a banned word (`imd_score`, `shrink_swell_score`,
`landslide_score`), the collision is real and unresolved — it should be settled
by renaming the *factor* to say what it is (`_band`), never by editing EM7.

---

## Summary

| Class | Count | Action |
| --- | --- | --- |
| `JUDGEMENT` | 5 | Do not implement. Guarded by test. |
| `DERIVED_METRIC` | 10 | Need published methodology + version before going live. Two need reconsidering on principle. |
| `MEASUREMENT` | 11 | Retain. Two renames for clarity; two keep external names deliberately. |

No factor has been renamed or removed by this document. It records the
classification and the reasoning so the decision can be made once rather than
re-derived.
