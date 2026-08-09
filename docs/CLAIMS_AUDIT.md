# Claims audit

What this product says to a customer, and what it can support.

---

## The headline finding

**All 30 judgement-shaped factors are generated. Not one is real.**

Searched `catalog.py` for factors whose id or name implies an assessment
rather than a measurement — `suitability`, `_score`, `risk`, `flag`,
`potential` — and cross-referenced against the registry of real
implementations. The result:

| | |
| --- | --- |
| Judgement-shaped factors | 30 |
| Backed by real data | **0** |

Including: `solar_farm_suitability`, `battery_site_suitability`,
`data_centre_suitability`, `warehouse_suitability`,
`woodland_creation_suitability`, `contamination_flag`, `subsidence_risk`,
`landslide_score`, `ground_risk_score`, `insurance_peril_score`,
`surface_water_risk`, `reservoir_risk`, `radon_potential`,
`bng_uplift_potential`.

### Why this is worse than a generated measurement

Every one of these is labelled demo data, correctly and in several places. The
honesty architecture is working. But **a demo label protects a measurement
better than it protects a recommendation**, and the difference is not covered
anywhere in the current design.

If NDVI reads 0.43 and says "demo data", a reader discounts the number and
keeps a true belief: *this product measures vegetation*.

If "Contamination status" reads a value and says "demo data", a reader
discounts the number and keeps a belief that is **not** true: *this product
assesses contamination*. The category itself is the claim, and the caveat does
not reach it.

That matters most on exactly the factors where being wrong is expensive.
Subsidence, contamination, flood and ground risk are the four things a
purchaser actually relies on, and all four are `series.py` output.

**Recommendation — needs an owner decision, not an automatic change:**

1. Treat generated judgement factors as a distinct class from generated
   measurements, and say so at the point of selection rather than only on the
   result.
2. Or withhold them until real, using the `blocked` mechanism now in
   `licensing.py`. This is the safe option and it costs 30 catalogue entries.
3. Or rename them descriptively — "Solar aspect (modelled)" rather than "Solar
   farm suitability" — so the name states a computation rather than a verdict.

Not done automatically: removing or renaming 30 factors is a product decision.

---

## What the copy gets right

Searched the whole frontend and backend for the phrases this audit flags as
liability-creating:

`suitable for development` · `suitable for construction` · `low flood risk` ·
`planning approval` · `development ready` · `risk-free` · `guaranteed` ·
`100% accurate` · `most accurate` · `environmentally safe` ·
`no ecological constraints` · `legally compliant` ·
`professional environmental assessment`

**Zero occurrences.** The customer-facing copy is already evidence-shaped, and
several parts of it are unusually careful:

- `insights.py` refuses to narrate noise, requires |t| ≥ 2 for a trend, and
  makes a step change beat a straight line before naming one.
- The flood proxy is labelled *"NOT Environment Agency flood zone data"*
  inside the AI prompt itself.
- Every automatically generated sentence about a demo factor carries "demo
  data — generated, not observed" **inside the sentence**, so no layout can
  drop it.

This is a good position to be starting from, and it should not be eroded.

---

## Wording that would benefit from tightening

Low priority, recorded so it is not lost.

| Location | Current | Concern | Suggested |
| --- | --- | --- | --- |
| `permalink.ts` template blurb | "Is this site worth pursuing — value, constraints and consent history?" | A question, not a claim. Fine, but it frames the product as answering it. | Leave; revisit if the templates gain summary verdicts. |
| `permalink.ts`, `peril-screen` | "Flood, subsidence and wind in one pass, for underwriting." | Names a regulated use — underwriting — for factors that are entirely generated. | Reword to describe the layers rather than the professional use, until they are real. |
| `permalink.ts`, `contamination` | "What was here before, and does it need investigating?" | Implies a screening opinion on contamination. | "Historic land use layers for the area" is defensible; the current wording is not, on generated data. |
| Gallery empty state | "Everything else — the layers, the fifteen-year record, the report — follows from the shape." | Accurate. | Leave. |

---

## Marketing claims

`docs/MARKETING_CLAIMS_AUDIT.md` was **not** produced as a separate document,
because there is no marketing copy in this repository to audit — no landing
page, no pricing page, no external site. The nearest thing is `README.md` and
the template blurbs above, both covered here.

When a landing page exists, it needs its own pass. The three template blurbs
above are the shape of claim that will want checking.
