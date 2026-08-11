# Scanner specification

The product truth for the three launch scanners. Where this and the code
disagree, the code is right and this is a bug.

A scanner is a **configuration** — a vocabulary, a rule sequence, the
investigations those rules raise, the factors it exposes and where it is valid.
The assessment engine, the four finding states, coverage, the claim boundary,
the evidence chain and the brief are shared and know nothing about any
scanner's domain. Adding Habitat required no engine change. Adding Coastal
required no engine change. That is the architectural claim, and it has now been
tested by a domain outside terrestrial vegetation.

| | Land | Habitat | Coastal |
| --- | --- | --- | --- |
| Topics | 7 | 5 | 4 |
| Rules | 25 | 7 | 7 |
| — flagged | 20 | 1 | 2 |
| — informational | 5 | 6 | 5 |
| Factors exposed | 271 | 6 | 7 |
| Coverage | England | England | England |

Forestry, Water and Terrain are registered, carry no content, and are refused
by the API. Registering is not implementing.

---

## Threshold vocabulary

Every threshold in Habitat and Coastal is a **Contour reporting threshold**: a
product decision about when something deserves a professional's attention.

They are **not** regulatory levels, statutory limits, planning requirements or
scientific consensus, and nothing in the product describes them as such. Each
is a named constant, restated beside the measurement in every finding that acts
on it, and carries `threshold_status: product-defined`. A test asserts that.

Land's thresholds predate this vocabulary and several *are* externally defined
(Flood Zone 2 and 3 are Environment Agency designations, not our lines). Those
report what the designation says rather than a threshold we chose.

---

## Land

**Purpose.** Site constraints and land assessment — what constrains what can be
done here.

The reference implementation and the mature scanner. Built from `radar.TOPICS`,
`radar.RULES`, `radar.INVESTIGATIONS` and `catalog.FACTORS` directly rather
than copied, so it is a lens over what already runs.

**Topics.** vegetation · terrain · ground · flood · water · ecology · planning

**Rules.** 25 — 20 flagged, 5 informational. Flood Zone 3 (any intersection),
Flood Zone 2 (5%), standing water, seasonal water, previously developed
ground, brownfield register, steep ground, vegetation decline, SSSI, ancient
woodland, national park, AONB, green belt, conservation area, scheduled
monument, Article 4, TPO, listed buildings, planning pressure, and the
historical vegetation decline contributed by `historical.rules`.

**Coverage.** England — `catalog.ENGLAND_BBOX`.

**Limitations.** Of 271 factors, 28 return real observations and 11 of those
are `verified` (run against the live service) rather than `written`
(implemented and fixture-tested, not yet run live). The remainder are generated
and cannot produce a finding — the real-data rule holds, so a generated factor
reports `not assessed`, never `clear`.

**Changed in this pass:** nothing. Adding two scanners must not alter Land's
behaviour, and `tests/test_three_scanners.py` asserts that a Land assessment is
identical before and after a Habitat or Coastal assessment of the same site.

---

## Habitat

**Purpose.** Ecological condition and habitat investigation.

**Topics.** condition · moisture · cover · water · structure

**Rules.** 7 — 1 flagged, 6 informational.

| Rule | Topic | Factor | Threshold | Raises |
| --- | --- | --- | --- | --- |
| `habitat_vegetation_decline` | condition | `ndvi` | `VEGETATION_CHANGE_INVESTIGATION_THRESHOLD` — ≥ 20% decline | Preliminary ecological appraisal |
| `habitat_ndvi` | condition | `ndvi` | none | — |
| `habitat_moisture` | moisture | `ndmi` | none | — |
| `habitat_structure` | structure | `evi` | none | — |
| `habitat_tree_cover` | cover | `lc_tree_pct` | none | — |
| `habitat_land_cover` | cover | `lc_dominant` | none | — |
| `habitat_water` | water | `water_occurrence` | none | — |

The threshold is **imported** from `historical.rules`, never restated. Two
scanners holding two copies of one number is how they drift.

**Method.** Percentage change in median NDVI from the historical baseline,
under the frozen methodology in `historical/metrics.py`. Sufficiency is
`meets_minimum_evidence` — too few usable years produces `not assessed` rather
than a confident number from three observations.

**What a flag does not establish.** Not evidence of habitat deterioration or
unfavourable condition. A spectral index responds to management, grazing,
cutting and season as readily as to harm.

**Coverage.** England. Not because the factors are England-limited — Sentinel-2,
WorldCover and JRC are global — but because that is where this deployment has
been exercised. Claiming more would assert something untested.

**Limitations.** ERA5-Land (9 km) and MODIS LST (1 km) are implemented and
deliberately excluded: a 9 km pixel over a 20 ha reserve describes a large part
of a county, which is regional context presented as site evidence.

**Not implemented, with the blocker** (`HABITAT_SCANNER.md` §6): fragmentation
and connectivity, land-cover change over time, burn history. None has a
defensible threshold or a suitable factor in this repository today.

---

## Coastal

**Purpose.** Coastal site and frontage assessment.

**This is the scanner that tests the architecture** rather than extending it.
Habitat is still terrestrial vegetation read from the same imagery as Land;
Coastal asks about elevation and water extent. It needed no engine change
either.

**Topics.** exposure · tidal · change · form

**Rules.** 7 — 2 flagged, 5 informational.

| Rule | Topic | Factor | Threshold | Raises |
| --- | --- | --- | --- | --- |
| `coastal_low_lying` | exposure | `elevation_min` | `COASTAL_LOW_LYING_INVESTIGATION_THRESHOLD` — ≤ 5 m AOD | Coastal flood risk assessment |
| `coastal_water_extent_change` | change | `water_change` | `COASTAL_WATER_EXTENT_CHANGE_INVESTIGATION_THRESHOLD` — ≥ 10 pp, either direction | Coastal process and morphology review |
| `coastal_elevation_min` | exposure | `elevation_min` | none | — |
| `coastal_elevation_mean` | exposure | `elevation_mean` | none | — |
| `coastal_water_occurrence` | tidal | `water_occurrence` | none | — |
| `coastal_water_seasonality` | tidal | `water_seasonality` | none | — |
| `coastal_slope` | form | `slope_mean` | none | — |

**Both flags act on factors no Land rule uses.** Land already owns Flood Zone 2
and 3, standing water and seasonal water; restating those under a coastal
heading would be one check wearing two hats — more findings, no more
information. A test enforces this.

### The two thresholds

**`COASTAL_LOW_LYING_INVESTIGATION_THRESHOLD = 5.0` m AOD. PRODUCT-DEFINED.**

*Why it exists:* five metres is the height at which a coastal flood risk
assessment stops being a formality and becomes a live question for most English
frontages. It is a screening line chosen to be legible and defensible, not
derived.

*What it acts on:* the lowest observed ground elevation in the drawn area.

*What it produces:* a flagged finding raising a coastal flood risk assessment.

*What it does not mean:* not evidence the site floods or will flood. It says
nothing about the defence standard for this frontage or about extreme sea
levels here. **A defended site at 2 m and an undefended site at 2 m read
identically to this check and are not the same risk.** Severity deliberately
does not climb as elevation falls — that would be the rule estimating flood
risk, which it states it cannot do.

*What would replace it:* a site-specific extreme sea level from the Environment
Agency's coastal design levels, plus a defence standard for the frontage.
Neither is in this repository.

**`COASTAL_WATER_EXTENT_CHANGE_INVESTIGATION_THRESHOLD = 10.0` percentage
points. PRODUCT-DEFINED.**

*Why it exists:* large enough over four decades of record to be signal rather
than classification noise, small enough not to miss a gradual trend.

*What it acts on:* JRC Global Surface Water change over the observation record.

*What it produces:* a flagged finding raising a coastal process review.
Symmetric — gain and loss both flag, because a scanner with an opinion about
which direction is bad is making a judgement that belongs to the reader.

*What it does not mean:* **it is not shoreline retreat and must not be read as
an erosion rate.** The JRC record measures where water was detected, not where
the shoreline was. A change can be accretion, erosion, managed realignment, a
new drainage regime, or a change in how the classifier handled a tidal flat. A
test asserts the finding text never uses erosion vocabulary.

### Geometry limitation — read this before selling Coastal

`geometry.py` is polygon-oriented and there is no coastline dataset anywhere in
this repository. Three consequences, stated in `coastal/rules.py`, on the
public Coastal page, and here:

1. **The scanner cannot verify that a site is coastal.** There is no mean-high-
   water line to measure against. "Is this on the coast" is the operator's
   judgement. Run inland, it produces honest readings of an inland site.
2. **It cannot measure shoreline retreat.** That needs a shoreline vector time
   series.
3. **A frontage is assessed as an area, not a corridor.** A long thin polygon
   along a frontage works, but the engine has no concept of alongshore
   distance, so nothing is reported per metre of frontage.

`geometry.py` was **not** rebuilt into a line/corridor system. Doing so to make
Coastal look more sophisticated would have been a large change to a shared
module for one scanner's presentation.

**Coverage.** England, for the same reason as Habitat.

### Capability gaps — questions a coastal scanner should answer and cannot

| Question | Blocker |
| --- | --- |
| How far is the site from mean high water? | No coastline dataset. |
| Has the shoreline retreated, and at what rate? | No shoreline vector time series. |
| What is the wave exposure / fetch here? | No wave or bathymetry data. |
| What is the tidal range? | No tidal data. |
| What is the design extreme sea level? | Not in the repository; needs EA coastal design levels. |
| What defends this frontage, and to what standard? | No defence asset dataset. |
| Is there evidence of saline intrusion? | No groundwater chemistry source. |
| Which Shoreline Management Plan policy unit applies? | No SMP dataset; the investigation names it as a professional step instead. |

Each of these is a gap, not a rule waiting to be written. None was filled with
an invented threshold.

---

## Unresolved product decisions

1. **Is 5 m the right screening height?** It is defensible and it is a
   judgement. It should be validated by a coastal engineer before launch, or
   replaced with EA design sea levels when those are ingested.
2. **Is 10 percentage points the right change threshold?** Chosen against the
   character of the JRC record rather than against a study.
3. **Should Coastal refuse to run on an obviously inland site?** It cannot
   detect one today. Adding a coastline dataset would let it warn; whether it
   should *refuse* is a product call, and refusing on bad geometry data would be
   worse than the current honest reading.
4. **Coverage for Habitat and Coastal is "England because that is where we have
   tested".** The underlying data is global. Widening the claim requires
   exercising it somewhere else, not editing a string.
