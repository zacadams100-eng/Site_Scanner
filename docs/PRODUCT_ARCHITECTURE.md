# Product architecture

**What is actually implemented, and what is not.** Every claim here is checkable
against the code. Where this and the code disagree, the code is right and this
file is a bug.

Written 2026-08-12, at the end of the autonomous transformation pass. See
`docs/AUTONOMOUS_CHANGELOG.md` for what changed in that pass and why.

---

## The shape

```
                    FAMILY          foundation · development · culture · economics
                      │
                    SCANNER         land · water · ecology · planning · …
                      │             a configuration, not a subclass
                      │
                    DOMAIN          flood · coastal · habitat · woodland · …
                      │             the unit at which coverage is honest
                      │
   ┌──────────────────┴───────────────────┐
   │            shared engine             │   radar · evidence · claims
   │  knows no scanner, no domain, no     │   investigation · brief · comparison
   │  family, and never will              │
   └──────────────────┬───────────────────┘
                      │
   SITE EVIDENCE RECORD                       stable ids · provenance · versions
                      │
   ┌──────────────────┼───────────────────┐
   │                  │                   │
 BRIEF            PORTFOLIO           REVIEW
 for a person     for many sites      defined, empty
```

The load-bearing property: **there is no branch anywhere in the shared engine
that asks which scanner is running.** `tests/test_scanner_registry.py` asserts
it structurally across every shared module, and
`tests/test_investigation_workspace.py` proves the point harder by assembling a
coastal investigation from fabricated metadata to show the assembly path
carries no land assumptions.

---

## Layers, and what each is allowed to do

| Layer | Files | May it reach a finding? |
| --- | --- | --- |
| Registry | `scanners.py` | No. It composes; it does not evaluate. |
| Engine | `radar.py` | **Yes. Only here.** |
| Contributing rules | `habitat/`, `coastal/`, `historical/` | Yes, through `radar.rules_from`. |
| Views | `evidence.py`, `investigation.py`, `brief.py`, `site_record.py`, `portfolio.py` | No. Reads over an assembled payload. |
| Claims | `claims.py` | Composes the boundary. Nothing else may word one. |
| Review | `review.py` | No. It records what a person said. |

The rule that keeps this honest: **a second module that could reach a finding
is a second opinion waiting to drift.** Every view module states this in its own
docstring, because the temptation arrives locally — it is always easier to
recompute a number than to thread it through.

---

## The scanner contract

A scanner is a frozen dataclass. Implemented:

```python
Scanner(
    id, name, subject,
    family,                    # organisational only
    domains,                   # the named parts of its subject
    topics, rules, investigations, factors,
    rule_domains,              # rule id → domain that contributed it
    version,                   # did the checks change?
    methodology_version,       # did the meaning of "assessed" change?
    coverage, coverage_name,   # None means none established
    specialist,                # "" where no single discipline owns it
)
```

Derived, never stored: `implemented`, `status` (`live`/`partial`/`planned`),
`built_domains`, `declared_domains`. A stored status is a claim somebody has to
remember to update; a derived one cannot go stale, and it moves in the honest
direction — a scanner that declares a new domain drops to `partial` the moment
it does.

### Domains

Two kinds carry content:

- **core** — topics of the shared rule set, named by id.
- **package** — a contributing rules package, through `radar.rules_from`.

A domain with neither is **declared**, and `scanners._check_registry` refuses
one without a `blocked_by`. An unexplained empty domain is a promise, and this
product does not make them.

### Overlap is deliberate

Land keeps the flood, vegetation, ecology and planning rules that Water, Ecology
and Planning also present. Land is the sweep you run before you know which
specialist question matters, and a professional who runs it and is not told
about Flood Zone 3 because flood "moved to Water" has been failed by a taxonomy.

What makes it safe: **a rule has exactly one definition.** Land and Water share
the same `Rule` object, selected by topic, never copied. Two scanners cannot
disagree about a threshold because there is only one threshold.
`tests/test_three_scanners.py` asserts object identity, not equality.

---

## Registered scanners

| Family | Scanner | Status | Rules | Notes |
| --- | --- | --- | --- | --- |
| Foundation | Land | live | 25 | All 7 core topics, all 271 factors. The sweep. |
| Foundation | Water | partial | 11 | Flood, surface water, coastal. No groundwater, drainage, catchment. |
| Foundation | Ecology | partial | 16 | Habitat, vegetation, designations. No woodland, species, connectivity. |
| Development | Planning | partial | 7 | Designations only. No applications, no policy. |
| Development | Development | planned | 0 | 3 declared domains. |
| Development | Infrastructure | planned | 0 | 4 declared domains. |
| Culture | Heritage | planned | 0 | 4 declared domains. Blocked on ingestion, not licensing. |
| Economics | Market | planned | 0 | 3 declared domains. |

Aliases, resolving to the scanner that absorbed them: `habitat`→ecology,
`forestry`→ecology, `coastal`→water, `terrain`→land. Absent from `ids()`, so a
retired product does not linger in the catalogue. An alias is a door that still
opens, not a product that still exists.

---

## API

| Endpoint | Serves |
| --- | --- |
| `GET /api/catalog` | Factors, scanners, families, coverage, baselines |
| `POST /api/series` | The assessment: radar, evidence, historical, workspace |
| `POST /api/brief` | The Site Investigation Brief — prose, for a person |
| `POST /api/record` | The Site Evidence Record — addressable, for a machine |
| `POST /api/portfolio` | Records in, portfolio view out |
| `GET /api/portfolio/demo` | A labelled demonstration portfolio |
| `POST /api/ask` | Natural-language query over the series |
| `POST /api/compare` | Site against site, or site against England |
| `POST /api/enquiry` | The contact form's receiver |

`/api/brief` and `/api/record` are separate on purpose. A brief is prose in a
fixed editorial order for a human recipient; a record is an addressable document
with stable identifiers and three versions. Collapsing them would give the brief
identifiers nobody reading it needs and the record a section order that means
nothing to a machine.

---

## What is not built

Named rather than implied, because the gaps are the part a reader most needs.

- **No storage.** Records and portfolios are computed and returned. The storage
  decision is bound up with authentication, which does not exist.
  `docs/PORTFOLIO_ARCHITECTURE.md` records what a real store must guarantee.
- **No authentication, accounts or tenancy.**
- **No job queue.** Assessing a thousand sites is a thousand assessments. The
  portfolio counts what has been assessed, not what has been added.
- **No review workflow.** The model exists (`review.py`); nothing submits one.
- **No Earth Engine in production.** Blocked on a Google billing account. 28 of
  Land's 271 factors return real observations and 11 are verified live.
- **No longitudinal comparison.** The record makes it *possible* — stable site
  ids, versions, timestamps — and nothing consumes two records yet.

---

## Testing

```
1053 Python      pytest tests/
 329 frontend    cd web && npm run test
  36 e2e         cd web && npx playwright test
```

The production build is authoritative — `npm run build`, not `tsc --noEmit`.
Both were green while three real UI regressions shipped in this pass; all three
were found by driving the page in a browser.

**Never weaken a test to make a change pass.** Several exist because a bug
shipped past a green suite. When a test becomes false by design — as
`test_the_three_scanners_ask_different_questions` did when the taxonomy
introduced deliberate overlap — find the guarantee it was protecting and assert
that instead. Deleting it throws the guarantee away.
