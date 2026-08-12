# The Site Evidence Record

**Implemented.** `site_record.py`, served at `POST /api/record`, 30 tests in
`tests/test_site_evidence_record.py`.

The canonical form of one assessment: what was observed about a place, when, by
which scanner, at which version, from which source, and what a professional was
told it did and did not establish.

---

## Why it exists separately from the brief

The product already assembles all of this — `radar` reaches the findings,
`evidence` joins them to their sources, `brief` composes what leaves the
building. What none of them produces is a form that is **stable, addressable and
comparable over time**. They all shape one assessment for a particular screen.

The difference appears as soon as there are two assessments. *"Has this site
changed since March?"* cannot be answered from two briefs, because a brief is
prose in a fixed order whose identifiers are internal to one run. It can be
answered from two records.

That is why this was built before anything needed it. **A longitudinal record
can only be assembled from assessments that were recorded comparably at the
time.** Nothing retrofits it. The records not kept today are the ones that can
never be compared tomorrow.

---

## Structure

```
record_id · record_schema · engine_version
  site          id (content hash) · name · geometry · area · centroid
  scanner       id · family · version · methodology_version · status · domains
  assessed_at
  observations  [ factor · state · reason · source · claims ]
  findings      [ id · factor · domain · severity · statement · threshold · rule ]
  investigations[ id · name · priority · raised_by ]
  gaps          factors[] · by_reason · domains[] · counts
  coverage
  review        status · statement · reviews[] · unreviewed_findings[]
  limits · principle
```

Flat lists, related by identifier rather than by nesting. A record is read by
machines as often as by people, and a portfolio counting evidence gaps across a
thousand sites should not have to walk a tree to find them.

---

## The two identifiers

### `site_id` — a stable identifier for a piece of ground

A SHA-256 content hash of the geometry, rounded to six decimal places (~0.1 m),
prefixed `site_`.

Content-hashed rather than assigned, because **the same field assessed in March
and in August must be one site**. A UUID or a counter would give one piece of
ground two identities and silently break every comparison — and silently is the
problem: each record would look correct alone and no two would ever match.

The rounding absorbs the float noise a permalink round-trip or a redrawn polygon
introduces, and sits far below the accuracy of any source here, so it cannot
merge two genuinely different sites. Both directions are tested.

### `record_id` — a stable identifier for one assessment

A content hash of the site, scanner, versions and evidence — deliberately **not**
the clock.

Excluding the timestamp means two identical assessments collapse to one record
rather than filling a portfolio with duplicates that each look new. Including
the evidence means a record **cannot be edited without becoming a different
record**, which is the property an auditable trail actually needs. The specific
edit worth catching — turning a gap into a clear result — is tested.

---

## The three versions

A reader of a two-year-old record asks three different questions, and collapsing
them into one makes none of them answerable:

| Field | Answers |
| --- | --- |
| `scanner.version` | Did the checks change? |
| `scanner.methodology_version` | Did the meaning of "assessed" change? |
| `record_schema` | Did the shape of this document change? |

`engine_version` is a fourth, for changes to the shared machinery that affect
every scanner at once.

A record states the schema it was written under, so a reader can tell "this
field was absent" from "this field was empty" — different facts about a site,
indistinguishable without it.

---

## `gaps.domains` — the field to defend

The record carries the shape of its own ignorance.

Water returning no groundwater finding looks **identical** whether groundwater
was clear or was never asked. Nothing in an assessment payload distinguishes
them, because there is nothing to point at — no rule ran, no factor was
consulted, no gap was recorded. The only place that distinction can live is the
registry, and the record reads it from there.

This is the single most valuable field in the document for a professional
deciding whether to rely on it.

---

## What it deliberately does not do

- **No score, index or rollup**, at any level. The record is the most tempting
  place in the product to add one — structured, comparable, sortable — which is
  exactly why a test greps the served document for one.
- **No comparison against another record.** Comparing two records is a real
  feature; it belongs to whatever holds a series of them. A record that
  described its own change would need another record inside it.
- **No invented reviewer.** Every record carries `review.empty_block()`.

---

## What a store must guarantee

Not built. When one arrives:

1. **Records are immutable.** A correction is a new record, not an edit. The
   `record_id` already enforces this — an edited record is a different one.
2. **`site_id` is the grouping key**, not a row id. Two records for one site is
   the normal case.
3. **Nothing is deduplicated across sites by name.** Names are user text and two
   sites can share one.
4. **A retired scanner's records stay readable.** `site_record.build` accepts
   `scanner=None` and is tested for it; a store must not join through a live
   registry to render an old record.
