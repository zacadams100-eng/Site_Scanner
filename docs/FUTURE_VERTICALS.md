# Future verticals

**None of this is implemented.** This document exists so that architectural
decisions can be checked against where the product might go — not to imply any
of it is planned, resourced or coming.

The test each entry is written to answer: *does anything in the current
architecture foreclose this?* Where the answer is yes, it says so.

---

## Status vocabulary

| | |
| --- | --- |
| **Registered** | A scanner exists in `scanners.py` with declared domains and stated blockers |
| **Reachable** | Would need a new scanner, but no engine change |
| **Needs work** | Would need something the architecture does not have |

---

## Registered today

| Scanner | Family | Blocked on |
| --- | --- | --- |
| Development | Development | Building footprints (licence unresolved); change-detection method unwritten |
| Infrastructure | Development | No national DNO dataset; utility networks released per enquiry. Transport is the tractable one — OS Open Roads is open |
| Heritage | Culture | **Ingestion work only.** The National Heritage List is open under OGL |
| Market | Economics | Deliberate: transactions beside a site invite reading as valuation. Needs a claim boundary written before the feature |

Heritage is the nearest. Its blocker is work, not permission — which is a
materially different position from Infrastructure's, and the reason each domain
records its specific blocker rather than a shared "not built yet".

---

## Reachable — a scanner, no engine change

**Energy** — solar, wind, battery storage, grid, heat networks, EV.
Constraint-and-context evidence: irradiance, slope, aspect, grid proximity,
designations. All within the existing model. *Grid capacity is the hard part and
belongs to Infrastructure.*

**Transport** — roads, rail, ports, airports, corridors. OS Open Roads and rail
network data are open.

**Natural resources** — agriculture, forestry, minerals, peat, soil, water
resources. Land classification and peat mapping are published.

**Public sector** — local authority portfolios, environmental monitoring,
climate adaptation, regeneration. This is a **portfolio** use case rather than a
scanner one, and it is the closest fit to what exists: a local authority has
hundreds of sites, a statutory duty to know about them, and no system that
holds them.

---

## Needs work

**Property and development appraisal.** Housebuilding, logistics, data centres,
land funds. The evidence is reachable; the *appraisal* is not, and the boundary
between them is exactly where this product would break its own rules. A
development appraisal is a professional judgement.

**Finance.** Lending, asset management, insurance, environmental due diligence.
Two hard requirements the product does not meet: a defensible statement of
completeness ("these are all the constraints"), which nothing here can make, and
audit-grade retention, which needs storage. *Institutional buyers would also
require review co-signing, which is modelled and not built.*

---

## Professions the architecture would need to serve

Ecologists · heritage consultants · archaeologists · arboriculturists ·
geotechnical engineers · hydrologists · flood consultants · landscape architects
· planning consultants · transport consultants · environmental consultants ·
surveyors.

Two roles per profession, and they are different — contributing a scanner, and
reviewing findings on a site. Both are modelled; see
`docs/SCANNER_ECOSYSTEM.md`.

---

## What would foreclose all of this

Recorded as the actual risk, since that is what this document is for:

1. **A site score.** It would have to be defined per vertical, would be wrong in
   each, and every subsequent vertical would inherit it.
2. **A scanner id branch in the engine.** The moment `if scanner == "heritage"`
   appears in a shared module, each new vertical becomes a refactor rather than
   a registry entry. Tested against structurally.
3. **Fabricated data in any vertical.** One invented planning history would make
   every other vertical's evidence unbelievable, because a buyer cannot audit
   which parts were real.
4. **Storage built around a single tenant.** The portfolio model assumes many
   sites; a store that assumes one owner per site would foreclose public-sector
   and fund use cases both.
