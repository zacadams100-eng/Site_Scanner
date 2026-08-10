# Legal risk register

**Not legal advice. No licence, terms or statute page was fetched to write
this** — the environment it was produced in cannot reach one. It records what
the code does, what the repository asserts, and what follows if those
assertions are correct.

Reviewed 2026-08-09. Review again before any commercial launch.

| ID | Risk | Severity | Probability | Status | Mitigation | Owner action |
| --- | --- | --- | --- | --- | --- | --- |
| L1 | Earth Engine project is registered **non-commercial**; 27 real factors depend on it | **CRITICAL** | Certain (the registration is a fact) | LEGAL REVIEW REQUIRED | `ingest/` batch-derive-then-store is built and is the recorded answer in `docs/licensing/DECISION-LOG.md`; never deployed | Send the drafted Google enquiry. Decide on a paid tier if required — **do not enable automatically** |
| L2 | `getMapId` serves Google-rendered tiles directly into a product intended to be paid | **CRITICAL** | Certain (the code does this) | OPEN | None. The map works without it — `scripts/build_basemap.py` bundles a Natural Earth basemap | Decide whether to remove the tile path before launch. Cheapest single risk reduction available |
| L3 | Sentinel-2 recorded as CC BY-SA 3.0 IGO, `commercial="verify"`; share-alike on a commercial derived product would bite | **HIGH** | Unknown | LEGAL REVIEW REQUIRED | Marked `conditional` in `licensing.py`; still served | Send the drafted ESA enquiry. Cheaper question than L1 and may shrink it |
| L4 | 30 judgement-shaped factors (`suitability`, `risk`, `flag`) are **all generated**, and a demo label protects a recommendation less well than a measurement | **HIGH** | Certain | OPEN | Labelled as demo everywhere; `blocked` mechanism now exists to withhold them | Decide: withhold, reclassify, or rename. See `docs/CLAIMS_AUDIT.md` |
| L5 | 43 of 55 real factors have never been run against their live source | **HIGH** | Certain | INVESTIGATING | `scripts/verify.py`; 12 verified on 2026-08-09 with recorded figures | Keep running it. Each run converts a claim into a record |
| L6 | Licence strings in `catalog.py` were written from documentation by a non-lawyer and **no licence page has ever been fetched** | **HIGH** | Certain | OPEN | `DATA_LICENSING.md` states this on every row; `licensing.py` says so in its payload | Run a licence-URL check from a machine with internet; then a legal read of the four `conditional` bases |
| L7 | OS Data Hub and NESO/DNO terms vary by plan and operator; position for a paid downstream product not established | MEDIUM | Unknown | LEGAL REVIEW REQUIRED | Marked `conditional`; factors not currently real | Resolve before implementing either source |
| L8 | AI could alter a number or drop a caveat when rephrasing | MEDIUM | Low | MITIGATED (by architecture) | Model receives a finished answer and is told not to change figures; `answered_from` stays `series`; deployed URL has no API key | Add the two assertions in `docs/AI_RISK.md §4` |
| L9 | Environmental/planning advice liability from customer-facing wording | **MEDIUM** | Low today | MITIGATED in part | Zero occurrences of the flagged phrases; `insights.py` refuses to narrate noise. `radar.py` names investigations rather than giving opinions, raises flags only from real data, and states in its payload that its thresholds are not regulatory tests | Re-audit when a landing page or pricing page exists. **The radar is the highest-exposure surface in the product** — review its wording before any commercial launch |
| L10 | GDPR — personal data | **LOW** | Low | OPEN | No accounts, no email, no names, no uploads. `telemetry.py` logs route/status/duration only, asserted by test. Saved sites are `localStorage`, never transmitted | Revisit the moment accounts are added; a geometry plus an account is personal data |
| L11 | Geometry sent to a third-party AI provider | **LOW** | None | MITIGATED | Verified: no geometry, coordinates, postcode, site name or marker text ever reaches the model — only aggregates | Keep it that way; add a test |
| L12 | Uploaded EIA/report confidentiality | LOW today | None today | ACCEPTED | No upload path exists. `experiments/eia_library/FINDINGS.md` measured the anonymisation problem and found 30.8% of identifiers survive | Do not build uploads before that is resolved |
| L13 | Cybersecurity / breach exposure | LOW | Low | MITIGATED in part | No accounts, no database, no secrets in the repo; `redaction.py` strips credentials from anything headed for a log or a response; rate limiting is per-instance only | Real limits and a security review before launch |
| L14 | Accessibility (likely obligations for a commercial UK service) | MEDIUM | Certain to apply | **OPEN — not audited** | Focus rings, `aria-live` on status, reduced-motion honoured, keyboard timeline | Not assessed against WCAG. Needs its own pass |
| L15 | No Terms of Service, Privacy Policy, or licence attribution page | **HIGH** | Certain | OPEN | Attribution travels into the UI and every export already | Cannot launch commercially without these. See below |
| L16 | npm/PyPI dependency licences never audited | MEDIUM | Unknown | **OPEN — not audited** | None | Run `pip-licenses` and `license-checker`; `docs/IP_AUDIT.md` not produced |
| L17 | Map tiles, glyphs and geocoding fetched at runtime from third parties | MEDIUM | Certain | OPEN | OpenFreeMap vector tiles, a glyph host, postcodes.io. Attribution shown for Natural Earth and postcodes.io | Check each provider's terms for commercial use |

---

## Documents that do not exist and are required

Per the mandate, placeholders rather than invented legal wording. **None of
these should be drafted by an engineer or by a model.**

- Terms of Service — **DRAFT REQUIRED, LEGAL REVIEW REQUIRED**
- Privacy Policy — required before any account or analytics exists
- Data & licensing attribution page — the content already exists in
  `catalog.py` attributions and could be generated
- AI / analysis disclaimer — needed the moment an API key is set in production
- Acceptable use policy
- Upload & content policy — only if uploads are ever built
- Data Processing Agreement — only for business customers

`docs/LEGAL_DOCUMENTS_REQUIRED.md` was not produced as a separate file; this
list is it.
