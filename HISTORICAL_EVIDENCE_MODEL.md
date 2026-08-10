# The historical evidence model

Written **before** any historical-analysis code exists, because the decision
that matters is architectural and is cheap now and expensive later.

## The rule

> **Historical analysis is an evidence source, not a finding system.**

```
Sentinel-2 / MODIS
      ↓
historical observations
      ↓
derived temporal metrics        ← this document defines these
      ↓
the evidence model (EM1–EM11)
      ↓
finding: flagged · clear · informational · not assessed
      ↓
the existing investigation engine
```

It introduces **no new finding states, no new severity scale, no second
investigation engine and no separate notion of confidence.** A historical flag
is a flag. The historical page is a richer *view* of evidence that has already
been interpreted by the same rules as everything else.

The failure this prevents is specific and common: a satellite feature that
grows its own interpretation layer, and a product that then holds three
opinions about one site — radar says flagged, history says stable, the report
says concerning. There must be **one interpretation, viewed several ways.**

---

## HE1 — Source provenance

Every historical observation identifies its source, the processing that
produced it, and the endpoint that served it. Sentinel-2 reaches this product
*through Earth Engine*, which does the cloud masking and compositing; a user
told only "Copernicus" would look for the number in the Copernicus Data Space
and find a different one. Publisher and endpoint stay separate fields, as they
already do in `catalog.py`.

## HE2 — Verified source requirement

Generated observations cannot produce a historical finding — flagged, clear
**or** informational. This is EM1–EM3 restated for a subsystem that will be
tempted to treat a smooth synthetic series as "good enough to demo". A
fabricated fifteen-year trend is the most convincing wrong thing this product
could draw.

## HE3 — Temporal coverage

Every metric records how much of the period it actually observed, in two
figures that are not interchangeable:

- **Observation coverage** — usable observations ÷ possible observations.
- **Year coverage** — years meeting the usable-year test ÷ years in the period.

A series that is excellent 2011–2014, poor 2015–2018 and excellent 2019–2026
must not be drawn as a smooth fifteen-year trend. The gap is part of the
result.

## HE4 — Baseline definition

Every change metric declares its baseline period and method explicitly, from
the frozen definitions below. "Vegetation has declined 18% over 15 years" is
not a claim until *declined from what, measured how* is answered, and two
metrics using subtly different definitions of "change" is the specific rot this
invariant exists to prevent.

## HE5 — Minimum evidence

A rule may not evaluate unless its metric's minimum coverage is satisfied.
Below it, the metric exists and the rule does not run.

## HE6 — No-data distinction

No usable observations produce `not_assessed` with reason `no_data` — never
`clear`. EM2 and EM6, restated: a source that was asked and returned nothing
has not cleared anything.

## HE7 — Existing finding semantics

Historical evidence uses the four existing states and no others. No
"trend detected", no "likely", no confidence percentage that is really a fifth
state wearing a number.

## HE8 — Existing investigation engine

Historical flags enter `radar.INVESTIGATIONS` through the same `Rule` interface
as every other factor, and inherit the same tracing: an investigation names the
flags that raised it, and converging evidence promotes medium to high exactly
as it does now.

## HE9 — No causal inference

A metric is an observation. It does not become an environmental conclusion.

| Permitted | Forbidden |
| --- | --- |
| "NDVI has declined 21% relative to the defined historical baseline." | "Vegetation degradation detected." |
| "Median summer land-surface temperature is 1.4 °C above the defined baseline." | "Climate change has warmed this site." |
| "Built-surface index rose 8%." | "The site has been developed." |
| → prompts *ecological assessment* | → asserts a cause nobody measured |

The professional interprets why. Contour states what changed and what that
would normally prompt someone to check — which is EM8 applied to a domain where
causal language is unusually tempting because the physical story feels obvious.

## HE10 — Reproducibility

Every historical result records the methodology version that produced it
(`METHOD_VERSION`), the exact baseline and recent periods used, and the
observation counts behind each. A figure in a report read in three months must
be reproducible, not merely trusted — and when the methodology changes, results
computed under the old one must remain identifiable rather than silently
reinterpreted.

---

## The frozen methodology

These definitions are the contract. Changing one is a `METHOD_VERSION` bump,
not an edit.

**`METHOD_VERSION = "hist-1"`**

### Seasonal window — declared per metric, never globally

A single window across all metrics would be wrong for at least one of them.
Vegetation and temperature answer different questions and are read in different
months:

| Metric family | Window | Why |
| --- | --- | --- |
| Vegetation (NDVI, EVI, NDMI) | **April–September** | The English growing season. A December NDVI is a real observation of nothing much, and including it makes every site look like it collapses annually. |
| Land surface temperature | **June–August** | Summer heat is the question; annual mean LST mixes it with winter and hides it. |
| Built / bare surface | **All months** | Not seasonal in the same way, and restricting the window would halve an already sparse signal. |

### Usable observation

A monthly value that is present, **not interpolated**, and inside the metric's
seasonal window. Carried-forward values are excluded for the same reason
`insights.py` excludes them: a value held flat across a gap reads as a
measurement and is not one.

### Usable year

A year with **at least 3 usable observations** inside the window (of up to 6
for vegetation, 3 for LST — so an LST year requires all three summer months).

### Baseline and recent periods

- **Baseline** = the **first 3 usable years** of the analysis period.
- **Recent** = the **most recent 3 usable years**.
- The two must not overlap. Where fewer than 6 usable years exist in total, the
  change metric does not evaluate — reason `no_data`.

Three years, not one: a single-year baseline makes the result a function of
whichever year happened to be wet.

### Values

- **Annual value** = median of that year's usable observations.
- **Baseline value** = median of the baseline years' annual values.
- **Recent value** = median of the recent years' annual values.
- **Change** = `(recent − baseline) / |baseline| × 100`, expressed in per cent.
  Where `baseline` is 0 the percentage is undefined and only the absolute
  difference is reported — a percentage change from zero is an infinity dressed
  as a statistic.

Medians throughout, not means: one cloud-contaminated composite should not move
a fifteen-year baseline.

### Minimum evidence (HE5)

A change rule evaluates only when **all** hold:

- ≥ 3 usable years in the baseline period,
- ≥ 3 usable years in the recent period,
- **year coverage ≥ 0.6** across the analysis period.

Otherwise: `not_assessed`, reason `no_data`, with the coverage figures
reported so the user can see how close it came.

---

## What a historical finding looks like

Identical in shape to every other finding, because it *is* one:

```
🔴 Vegetation decline
   NDVI has declined 21% relative to the defined historical baseline
   (0.49 → 0.39).
   Threshold   ≥ 20% decline
   Baseline    2011–2013, 17 usable observations
   Recent      2024–2026, 16 usable observations
   Coverage    13 of 15 years adequately observed (87%)
   Source      Sentinel-2 via Earth Engine · verified live
   Method      hist-1

   Investigation prompted → Preliminary ecological appraisal
```

And the clear state, which carries exactly the same weight:

```
🟢 Vegetation stability
   NDVI change −4% relative to the defined historical baseline.
   Threshold   ≥ 20% decline
   Coverage    14 of 15 years adequately observed (94%)
   Checked · clear
```

And informational, where nothing was tested:

```
🔵 Vegetation history
   Median NDVI 0.47; historical baseline 0.49; change −4%, 2011–2026.
```

The user learns one mental model, and every result in Contour means the same
thing regardless of which sensor it came from.

---

## Implementation shape

Not built yet, deliberately.

```
historical/
    sources/       sentinel2, modis — provenance and fetch
    observations/  vegetation, temperature, surface
    metrics/       baseline, recent, change, trend, coverage
    rules/         vegetation_change, temperature_change
```

Everything in `rules/` produces `radar.Rule` objects. `radar.py` does not learn
that Sentinel-2 exists; it receives factors, evidence and thresholds exactly as
it does today. The historical page is a view over the result.

## Sequence

1. This document. ✅
2. EM11 in `EVIDENCE_MODEL.md` — no UI component decides a finding state. ✅
3. `historical/metrics` and its tests, against the frozen definitions above.
4. `historical/rules`, registered into `radar.RULES`.
5. The historical UI — last, and reading state it never computes.
