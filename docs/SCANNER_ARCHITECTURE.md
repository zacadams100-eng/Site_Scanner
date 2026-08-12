# Scanner architecture

**Implemented.** `scanners.py`, `tests/test_scanner_registry.py`,
`tests/test_three_scanners.py`.

How to add a scanner, what a scanner may assume, and what the engine will never
know about it.

---

## A scanner is a configuration

Not a subclass, not a plugin, not a lifecycle. `tests/test_multi_scanner_experiment.py`
measured what was actually required to run a second domain through the engine
and the answer was: a topic dict, a rule sequence and an investigation dict.
Anything more would be an abstraction built for an imagined requirement rather
than a measured one.

Two structures have been added since — `Family` and `Domain` — and neither
introduces behaviour. They are grouping and composition.

---

## Adding a scanner

### If its checks come from the shared rule set

Add a `Domain` naming the core topics it owns:

```python
PLANNING = _scanner(
    "planning", "Planning", "Planning designations, policy and constraint",
    DEVELOPMENT,
    (
        Domain("designations", "Designations and constraints",
               "Green belt, conservation areas, protected landscapes.",
               core_topics=("planning",)),
        Domain("applications", "Applications and history",
               "Planning applications, permissions, refusals and appeals.",
               blocked_by="Requires a planning application source. "
                          "planning.data.gov.uk carries designations but not "
                          "application history; that lives in ~330 separate "
                          "local authority registers with no common API."),
    ),
    coverage_name="England", specialist="Planning consultant",
)
```

That is the whole of it. Planning was built this way and needed no engine
change, no new rule and no new test infrastructure — the checks were already
running inside Land.

### If it brings its own checks

Write a package with `build(Rule, Insufficient)` and name it:

```python
Domain("coastal", "Coastal", "Low-lying exposure and water-extent change.",
       package="coastal.rules",
       extra_factors=("elevation_min", "water_change", ...)),
```

The package must not import `radar`. `build` is called *with* the classes so the
direction of knowledge stays one-way and there is no circular import to work
around. Habitat and Coastal both arrived this way; neither required an engine
change.

### Then

1. Add the scanner to `SCANNERS`.
2. Add a voice in `web/src/lib/scannerVoice.ts` and a palette in `index.css`.
3. If it retires an existing id, add an `ALIASES` entry.
4. If it names a package, add a `COPY` line to the Dockerfile — the test will
   tell you, and it reads the package names from the registry rather than from
   the AST, because a domain names its package as a string.

Nothing else. **There is not one scanner id anywhere in `web/src` except
`scannerVoice.ts`**, which is a presentation lookup table. Components render
whatever the API describes.

---

## What the engine will never know

`tests/test_scanner_registry.py::test_no_shared_module_branches_on_a_scanner_id`
scans every shared module for `== "habitat"` and its variants.
`test_the_engine_does_not_import_the_registry` asserts one-way knowledge: the
registry composes the engine, and the engine must not reach back.

`investigation.py` is the module where generality would be easiest to lose — an
investigation workspace is exactly where someone writes "the site" or "before
development". Its test scans the file for domain vocabulary *and* assembles a
coastal investigation from fabricated metadata to prove the assembly path
carries no land assumptions.

---

## Domains and the honesty of coverage

The unit at which coverage is stated. "Water: partial" is a claim nobody can
check; "Water covers flood, surface water and coastal exposure, and does not
cover groundwater, drainage or catchment" is one a professional can act on —
they know to look elsewhere for the second set today.

`_check_registry` runs at import and refuses:

- a declared domain with no `blocked_by`;
- a scanner with no rules that claims coverage;
- a scanner naming a family that does not exist;
- **a domain naming a package that contributed no rules.**

The last is the subtle one. `radar.rules_from` swallows an ImportError by
design, so a package missing from the image would produce a scanner claiming to
cover coastal exposure and never looking. Failing at import costs a startup;
failing silently costs a false clear.

---

## Versioning

`version` changes when a scanner's rules, thresholds or domains change.
`methodology_version` changes when the *meaning* of an assessment changes — how
coverage is counted, how a state is decided. They are separate because a new
rule and a redefinition of "assessed" are different events for anyone re-reading
an old record.

Land is at `2.0.0`: the taxonomy pass changed what it is. The others are at
`1.0.0`.

---

## The overlap rule

Land presents checks that Water, Ecology and Planning also present. This is
allowed and is the correct behaviour — Land is the sweep.

**A rule must have exactly one definition.** Scanners select from `radar.RULES`
by topic; they never copy. `test_where_land_overlaps_a_specialist_it_is_the_same_rule_not_a_copy`
asserts object identity, and fails loudly if the overlap disappears entirely,
so the test cannot quietly stop asserting anything.

Specialists must stay disjoint from **each other**. Two specialists sharing a
rule id would mean one check wearing two hats.
