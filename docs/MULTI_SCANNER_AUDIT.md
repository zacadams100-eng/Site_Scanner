# Can this platform carry three scanners?

> **Status: R1–R6 implemented.** `scanners.py` holds the registry; land,
> habitat and coastal are registered; scanner identity is explicit in the API.
> R7 — the actual rules and thresholds for habitat and coastal — is
> deliberately not started. What changed is recorded in §10; the measurement
> below is kept because it is the reason the design is this small.

A measured answer, not an architectural opinion. The method: inject a coastal
scanner and a habitat scanner into the existing engine and see how far they get
before something breaks.

**Result: they get all the way through.** `radar.assess` → `evidence.report` →
`investigation.report` → `brief.build`, with nothing supplied but a topic
vocabulary, a rule set and a factor series. No new module, no branch, no
scanner class. See `tests/test_multi_scanner_experiment.py` — 7 tests, passing.

One seam had to be opened to do it, and it was two lines. Four remain.

---

## 1. What the experiment actually ran

Two fabricated scanners, deliberately unlike each other and unlike land:

| Scanner | Topics | Rule | Factor |
| --- | --- | --- | --- |
| Coastal | shoreline · inundation · sediment | shoreline retreat ≥ 10 m | `shoreline_position` |
| Habitat | condition · connectivity · hydrology | vigour ≤ 0.30 | `ndvi` |

Neither domain exists in `catalog.py`. `shoreline_position` and `tidal_range`
are not factors this repository has ever had.

**What passed, unchanged:**

- Topics assembled from the injected vocabulary
- A coastal flag raised a coastal investigation
- `evidence.report` produced an explorer entry for a coastal factor
- **EM12 held in a domain its clause vocabulary was never written for** — the
  state-generic limitation composed correctly, and the rule's own
  `not_evidence_of` ("not evidence of accelerating erosion") layered on top
- The evidence chain assembled from what the coastal rule recorded
- `brief.build` produced a brief with the coastal finding and its limitation
- A rule that could not run left its topic `not_assessed`, not `clear`
- **EM7 held**: no score, rating or grade appeared anywhere
- Two scanners in one process did not leak into each other
- The land scanner is byte-identical when nothing is injected

The thresholds in the experiment are invented and labelled as such. Inventing a
defensible coastal threshold is a product decision, and the experiment measures
plumbing, not domain modelling.

---

## 2. Component assessment

| Component | Shared | Scanner-specific | Needs abstraction |
| --- | --- | --- | --- |
| `radar.assess` engine | ✓ | | **done** — 2 lines |
| Evidence states / coverage | ✓ | | |
| `claims.py` (EM12 boundary) | ✓ | | |
| `evidence.py` explorer | ✓ | | |
| `investigation.py` workspace | ✓ | | |
| Evidence chain | ✓ | | |
| Evidence gaps | ✓ | | |
| `brief.py` | ✓ | | |
| `historical/` metrics | ✓ | | |
| `geometry.py` | ✓ | | (polygon-only — see §5) |
| `licensing.py`, `redaction.py` | ✓ | | |
| Permalink / state | ✓ | | |
| Frontend shell, Radar, Overview, Workspace, Drawer | ✓ | | |
| **`TOPICS`** | | ✓ | **✓ now injectable** |
| **`RULES`** | | ✓ | already pluggable (`_rules_from`) |
| **`INVESTIGATIONS`** | | ✓ | **✓ still global** |
| Thresholds | | ✓ | carried in `rule_meta` — no change |
| Terminology | | ✓ | carried in metadata — no change |
| `catalog.py` factors | | ✓ | **✓ single catalogue** |
| Map layers | | ✓ | **✓ single layer set** |
| `REAL_SERIES` registry | | ✓ | **✓ single registry** |
| England bbox gate | | ✓ | **✓ hard-coded** |
| Report structure | ✓ | | |
| Scoring infrastructure | — | — | **does not exist, by design (EM7)** |

Note the last row. There is no scoring infrastructure to share or specialise,
and that is deliberate — EM7 forbids it product-wide. A scanner cannot bring
its own score.

---

## 3. Hard-coded single-scanner assumptions

Every one found, in severity order.

### S1 — `radar.INVESTIGATIONS` is a module global · **blocks scanner 2**

`radar.py:119`. The experiment had to `monkeypatch` it. A second scanner cannot
name its own follow-up checks without either mutating a global or having its
investigations pre-merged into the land scanner's dict.

**Seam:** the same treatment `topic_names` just received — an optional
parameter on `assess`, defaulting to the module dict. Roughly the same two
lines.

### S2 — one factor catalogue · **blocks scanner 2**

`catalog.py` is a single flat list of 271 factors with one `ENGLAND_BBOX`, and
`/api/catalog` serves all of it. A coastal scanner would offer a user 17
property-market factors.

**Seam:** a scanner declares which factor ids it exposes. The catalogue itself
can stay one file — this is a filter, not a split.

### S3 — one `REAL_SERIES` registry · **blocks scanner 2**

`routes_catalog.REAL_SERIES` is process-global and installed at startup.
Two scanners sharing a process share it. Harmless while factor ids are unique;
a real collision arrives when two scanners want the same id to mean different
things.

**Seam:** namespace by scanner, or accept uniqueness as a rule and test it.
The second is cheaper and probably sufficient.

### S4 — the England gate · **blocks scanner 2 only if it leaves England**

`routes_catalog.py:143` returns 400 with *"Site Scanner only covers England"*
for anything outside `ENGLAND_BBOX`. A habitat or coastal scanner in England is
unaffected. One outside it is refused by a message naming the wrong product.

**Seam:** the coverage bbox becomes part of the scanner's configuration. Small.

### S5 — `comparison.py` reads `radar.TOPICS` directly

`comparison.py:129` and `:194` reach for the globals rather than receiving
them. Comparison across two scanners is meaningless anyway, but it will read
the wrong vocabulary if a second scanner ever calls it.

**Seam:** pass the config through, same as `assess`.

### S6 — one API surface

`/api/series`, `/api/brief`, `/api/compare` take a geometry and factor ids and
assume the land scanner. There is no scanner identifier anywhere in the
contract.

**Seam:** a `scanner` field on the request, defaulting to the land scanner.
This is the largest single change and it is still small — the routes are thin.

### S7 — brand and vocabulary in the shell

The wordmark says "Site Scanner", `BRAND.md` says Site Scanner, exports say
"Site Scanner report", and the templates are land trades. None of this blocks
the architecture; all of it is user-visible if a second scanner ships under the
same shell.

### Not an assumption, worth recording

- **No frontend component hard-codes a topic id.** `Radar.tsx` iterates
  `topics` and renders `t.name`. Checked; nothing to change.
- **Tests reference `radar.TOPICS` by identity** (`set(radar.TOPICS)`), so they
  follow the default and did not need changing. All 831 pass.

---

## 4. The `TOPICS` injection experiment

**Where defined:** `radar.py:103`, a module-level dict.

**Who consumed it:** `radar.py` (7 reads inside `assess`), `comparison.py` (1),
and four tests by identity. Nothing else — not the frontend, not `evidence.py`,
not `brief.py`, not `investigation.py`.

**Can it be injected?** Yes, and it now is:

```python
def assess(report, real_capable=None, *, topic_names=None, rules=None):
    topic_names = TOPICS if topic_names is None else topic_names
    rules = RULES if rules is None else rules
```

Two lines, plus renaming the reads inside `assess`. Every existing caller is
unaffected because the defaults are the module globals.

**One thing it surfaced:** `assess` already used the local name `topics` for
its *output* list, so the injected parameter is `topic_names`. A small naming
collision, but it is the kind of thing that only shows up when you try it —
the first attempt failed with `'list' object has no attribute 'items'`.

**What did not need to change:** the engine below. There is no branch anywhere
in `assess` that asks what a topic means; it collects rules, takes the
strongest state per topic, and reports coverage. That was already true before
this audit — it is the property `docs/VERTICAL_DISCOVERY.md` measured — and the
experiment confirms it operationally rather than structurally.

---

## 5. The one architectural blocker, restated

`geometry.py` accepts only `Polygon`/`MultiPolygon`. A coastal scanner whose
subject is a **shoreline** — a line — cannot express its subject, and shoreline
retreat is a measurement of how a line moved.

The experiment sidestepped this by giving the coastal scanner a polygon AOI and
a `shoreline_position` factor, which is a legitimate modelling choice (assess a
frontage as an area) but not the same product. **A coastal scanner can be built
on polygons; a corridor scanner cannot.**

This is the one item on this page that is a real piece of work rather than a
seam: a second geometry model and per-segment coverage.

---

## 6. Proposed minimal architecture

Not a framework. A dataclass and a default.

```python
@dataclass(frozen=True)
class Scanner:
    id: str                      # "land" | "habitat" | "coastal"
    name: str                    # what the shell says
    topics: Dict[str, str]
    rules: Sequence[Rule]
    investigations: Dict[str, Dict[str, str]]
    factors: Sequence[str]       # the slice of catalog.py it exposes
    coverage: Dict[str, float]   # bbox — replaces ENGLAND_BBOX
```

- `assess(..., topic_names=s.topics, rules=s.rules, investigations=s.investigations)`
- `/api/series` takes `scanner: str = "land"` and looks it up
- `evidence.py`, `investigation.py`, `brief.py`, `claims.py`, `historical/`
  and every frontend component change **not at all**

The land scanner becomes `SCANNERS["land"]` built from today's globals, which
keeps the defaults honest rather than duplicating them.

**What this deliberately does not add:** a scanner base class, a plugin loader,
a registry with lifecycle hooks, or per-scanner frontends. The measurement says
none of those are needed, and adding them would be the premature abstraction
the brief warns against.

---

## 7. Required before a three-scanner launch

| # | Change | Size |
| --- | --- | --- |
| R1 | `Scanner` config object and registry | small |
| R2 | Inject `INVESTIGATIONS` (S1) | ~2 lines |
| R3 | Scanner-scoped factor list (S2) | small |
| R4 | `scanner` field on the API contract (S6) | small |
| R5 | Coverage bbox from config (S4) | small |
| R6 | Shell names the active scanner (S7) | small, user-visible |
| R7 | Two real scanners' rules and thresholds | **the actual work** |

R7 is the honest one. The architecture is nearly ready; **the domain content is
not**, and it cannot be rushed — every threshold is a product decision that has
to be defensible, and inventing them to fill three scanners would break the
principle the whole product rests on.

## 8. Nice to have, can wait

- Namespaced `REAL_SERIES` (S3) — a uniqueness test is enough for now
- `comparison.py` config injection (S5) — cross-scanner comparison is
  meaningless anyway
- Per-scanner map layer sets — the layer list is already user-chosen
- Linear geometry (§5) — only if a corridor or shoreline-as-line scanner is
  wanted

---

## 9. Which scanner should be second

**Habitat**, and the experiment strengthens the case rather than merely
repeating it.

- Its factors are **already implemented and already global**: NDVI, EVI, NDMI,
  NBR, land cover, canopy height, surface water, LST — 27 Earth Engine
  implementations, none of which knows about England.
- It needs **no new geometry**: a reserve or parcel is a polygon.
- It needs **no new data sources**, so nothing is blocked on the network
  constraints in `BLOCKERS.md`.
- The historical chain — baseline, change, sufficiency, threshold — *is* the
  ecological question in its native form.

Coastal is the better *strategic* differentiator and the worse second scanner:
it wants linear geometry to be itself, and shoreline extraction is a method
this repository has not built.

Development/land suitability should **not** be scanner three. Under EM7 and EM8
it cannot answer the question its name promises, and the templates were just
reframed away from exactly that language. The land scanner already is the
development scanner, honestly named.

Suggested three: **Land (Site Scanner) · Habitat · Coastal** — with coastal
third, after the geometry question is answered.


---

## 10. What was implemented (R1–R6)

| | Change | Where |
| --- | --- | --- |
| R1 | Frozen `Scanner` config + registry; land built from the existing globals | `scanners.py` |
| R2 | `assess(..., investigations=...)`, defaulted to the module dict | `radar.py` |
| R3 | A scanner sees only its own factors; the catalogue is scoped | `routes_catalog.py` |
| R4 | `scanner` on every assessment request, resolved once, 400 on unknown | `routes_catalog.py` |
| R5 | Coverage from the scanner; `None` means none established | `routes_catalog.py` |
| R6 | The shell shows the active scanner | `App.tsx`, `types.ts`, `index.css` |

**Land is a lens, not a copy.** `LAND.topics is radar.TOPICS` — asserted by
test. A copied configuration would drift, and the first symptom would be a rule
that runs in tests and not in production.

**Habitat and coastal are registered and empty.** No topics, no rules, no
factors, `coverage=None`. An unbuilt scanner is refused with a reason rather
than returning an empty report, because a report with no findings from a
scanner that cannot assess anything is indistinguishable from a clean subject.

**Two bugs the implementation surfaced**, both use-before-assignment: the
scanner-scoped factor check landed above the line that resolves the scanner, in
two separate routes. Caught by the suite, not by reading.

### What is enforced

- `test_no_shared_module_branches_on_a_scanner_id` — no `== "habitat"` in any
  of the seven shared modules.
- `test_the_engine_does_not_import_the_registry` — one-way knowledge; the
  registry composes the engine, never the reverse.
- `test_land_is_unchanged_by_a_habitat_request_between_it` — the isolation
  test. Shared mutable configuration would show up here.
- `test_switching_scanners_needs_no_monkeypatching` — the measurement that made
  this work necessary, now impossible to regress.

### Remaining single-scanner assumptions

S3 (`REAL_SERIES` is process-global) and S5 (`comparison.py` reads
`radar.TOPICS`) are unchanged and still on the nice-to-have list. Neither
blocks a second scanner: factor ids are unique today, and cross-scanner
comparison is meaningless. The linear-geometry blocker in §5 is unchanged and
still the one item that is real work rather than a seam.
