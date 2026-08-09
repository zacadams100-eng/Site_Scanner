# Legal action plan

Ranked by what stops a commercial launch, not by effort.

**Not legal advice.** No licence or terms page was fetched to produce this.

---

## 🔴 BLOCKER — do not sell this functionality until resolved

| | Action | Why |
| --- | --- | --- |
| B1 | **Send the Google Earth Engine enquiry** (`docs/licensing/`, drafted, unsent) | The project is registered non-commercial and 27 of 55 real factors depend on it. Nothing in the repository can resolve this. |
| B2 | **Decide on the `getMapId` tile path** | Google-rendered imagery served into a paid product. The least defensible thing in the architecture and the easiest to remove — the map already has a bundled basemap. |
| B3 | **Send the ESA/Copernicus enquiry** (drafted, unsent) | Sentinel-2 recorded as CC BY-SA 3.0 IGO. Cheaper question than B1, and may shrink it. |
| B4 | **Terms of Service and Privacy Policy** | A commercial service cannot launch without them, and they must not be written by an engineer or a model. |

---

## 🟠 HIGH — before public commercial launch

| | Action | Why |
| --- | --- | --- |
| H1 | **Decide what happens to the 30 generated judgement factors** | "Contamination status" and "Subsidence risk" from `series.py`. A demo label protects a measurement better than a recommendation. Withhold, reclassify or rename — `docs/CLAIMS_AUDIT.md` has the options. |
| H2 | **Verify the licence strings** | All 45 were written from documentation by a non-lawyer, and none has been checked against a licence page. |
| H3 | **Keep running `scripts/verify.py`** | 43 of 55 real factors have still never been run against their live source. |
| H4 | **Audit dependency licences** | Never done. `pip-licenses`, `license-checker`. |
| H5 | **Check runtime third parties** — OpenFreeMap tiles, the glyph host, postcodes.io | Fetched on every session; terms unread. |

---

## 🟡 MEDIUM — during development

| | Action |
| --- | --- |
| M1 | Accessibility pass against WCAG. Never assessed. |
| M2 | The two AI assertions in `docs/AI_RISK.md §4` — caveat survives a rephrase, no new numerals appear. |
| M3 | Rate limiting backed by shared state rather than per-instance counters. |
| M4 | Generate the attribution page from `catalog.py`, as `DATA_LICENSING.md` now is. |

---

## 🟢 LOW — later

| | Action |
| --- | --- |
| G1 | Data Processing Agreement template, if business customers appear. |
| G2 | Upload/content policy, only if uploads are ever built. |
| G3 | Formalise the derived-metric naming so Contour metrics are never mistaken for official government ones. |

---

## Top 10, in order

1. **Send the ESA enquiry.** Five minutes, drafted, and it is the cheapest
   thing on this page that reduces a CRITICAL risk.
2. **Send the Google enquiry.** Same, and it is the one that decides whether
   half the real catalogue can be sold.
3. **Decide on the tile path.** An engineering decision you can take without
   waiting for anyone; removes a CRITICAL exposure.
4. **Decide what happens to the 30 judgement factors.** The largest
   customer-facing risk that is entirely within your control.
5. **Run `scripts/verify.py` again.** Every run turns claims into records, and
   43 factors are still claims.
6. **Get Terms and a Privacy Policy drafted by a solicitor.** Not by me.
7. **Verify the licence strings** against the actual licence pages.
8. **Audit dependency licences.**
9. **Check the runtime third parties** — tiles, glyphs, geocoder.
10. **Accessibility pass.**

Items 1–3 cost under an hour between them and remove or shrink two of the four
blockers. That is the highest-leverage hour available to this project right now.

---

## Costs

**Unknown, deliberately.** Earth Engine has paid commercial offerings; the
tier, the price and whether this usage pattern fits are all unrecorded here,
because guessing at a price is the same failure as guessing at a licence.

What is known: if a paid tier is required, **27 of 55 real factors depend on
it** — every Sentinel-2 index, all ERA5 climate, MODIS thermal, ESA WorldCover
and JRC surface water. Roughly half the real catalogue.

Solicitor time for B4 is the other certain cost.

**Nothing has been enabled, purchased or agreed.** Per the mandate, none of
that happens without you.
