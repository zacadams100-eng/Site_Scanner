# The comparison contract

Written **before** the feature, because comparison is the first thing Contour
will build that actively tempts a developer to break the evidence model.

`EVIDENCE_MODEL.md` EM7 forbids scores. Comparison is where a user will ask for
one in plain language — *"so which site is best?"* — and where the answer feels
obvious, helpful, and like the whole point of the screen. It is none of those
things, and this document exists so that the reasoning survives the person who
wrote it.

Enforced by `EVIDENCE_MODEL.md` **EM10** and `tests/test_comparison_contract.py`.

---

## What comparison is

**Evidence comparison, not site comparison.** Contour does not answer *which
site wins*. It answers *how do the evidence profiles differ*.

That is not a hedge. It is the more useful answer, because the thing a land
agent actually needs before a meeting is not a verdict — they can form that
themselves in about four seconds — it is a defensible statement of what is
known about each parcel and where the knowledge runs out.

---

## The trap this document exists to prevent

**Fewer flags can mean less looked at.**

```
Site A   4 flagged   18 observed   6 not assessed
Site C   0 flagged   11 observed  13 not assessed
```

Site C looks better. Site C is not better; Site C is *less examined*. Any
comparison that reports flag counts without reporting coverage alongside them
is actively misleading, and it will mislead in the direction of the least
investigated site — which is the most dangerous possible direction for a tool
whose users are deciding where to spend money.

**Therefore: no flag count may ever be presented without its coverage.** Not in
the API, not in the UI, not in an export. Where coverage differs between sites,
the comparison must say so explicitly and unprompted.

---

## The three layers

### Layer 1 — Evidence summary

Pure counts, no interpretation.

```
Site A   4 flagged · 18 observed · 2 informational · 6 not assessed
Site B   2 flagged · 23 observed · 3 informational · 3 not assessed
```

### Layer 2 — Topic comparison

The underlying evidence, per topic, with each site's assessment state beside
its value. A value is shown only where that site actually observed it.

```
Flood            A — 31%        B — 0%         C — not assessed
Evidence status  A — 2/2        B — 2/2        C — 0/2
```

### Layer 3 — Factual differences

Generated only from deterministic comparisons of values both sites observed.

- *"Site A has 31% Flood Zone 3 coverage compared with 0% for Site B."* ✅
- *"Site C has no high-severity flags."* ✅
- *"Site B observed 23 indicators; Site C observed 11."* ✅
- *"Site C is the strongest candidate."* ❌
- *"Site C is therefore the best site."* ❌
- *"Site A is unsuitable for development."* ❌

---

## What can be compared

| | |
| --- | --- |
| **Compared** | Values of the *same factor* where **every** site being compared observed it |
| | Counts — flags, observed, informational, not assessed |
| | Topic coverage fractions |
| | Which investigations were raised, and by what |
| **Not compared** | A factor one site observed and another did not — that is reported as a *coverage difference*, never as a value difference |
| | Values from different factors, however similar |
| | Anything generated, at either end |

**A comparison across unequal evidence is a coverage finding, not a value
finding.** If Site A observed Flood Zone 3 and Site B did not, the honest output
is "Site B did not assess Flood Zone 3", never "Site A has more flood risk than
Site B".

---

## What can be calculated

Differences, counts and set operations. Nothing else.

- Arithmetic difference between two observed values of one factor.
- Counts of flags, by severity.
- Coverage fractions.
- Set difference of raised investigations.

**Explicitly forbidden:** weighted composites, normalisation across factors,
any function that maps several factors onto one number, and any ordering of
sites by such a number. If a calculation's output is a single figure per site
that increases as the site gets "better", it is a score, whatever it is called.

---

## What language can be generated

Comparative *quantity* is permitted. Comparative *judgement* is not.

| Permitted | Forbidden |
| --- | --- |
| lowest, highest, fewer, more, most, least | best, worst, better, strongest, weakest |
| observed, not assessed, no live source | suitable, unsuitable, viable, developable |
| "has 31% compared with 0%" | recommended, preferred, ideal, optimal |
| "has no high-severity flags" | winner, top, leading, favourable |
| "assessed 23 indicators; C assessed 11" | rank, ranking, score, grade, rating |

The distinction is that a quantity statement can be checked against a number on
the same screen, and a judgement cannot be checked against anything.

Sites are never returned in an order that implies preference. Where an order is
needed, it is the order the user supplied.

---

## How partial evidence is represented

Every site in a comparison carries its own coverage, and every topic row shows
each site's assessment state. A topic where the sites have different coverage
is marked `not_comparable` and says why.

The comparison payload carries `coverage_warning` whenever the sites' observed
counts differ by more than a trivial margin — and the UI must show it beside
the counts, not below the fold.

---

## How investigations differ

Investigations are listed per site with the flags that raised them, exactly as
in a single-site radar. The comparison may state that an investigation was
raised for one site and not another. It may **not** infer from that which site
is cheaper, faster, less risky or more attractive to develop — those are
professional judgements about cost and risk, and Contour does not make them.

---

## Sequence

1. This document. ✅
2. EM10 and `tests/test_comparison_contract.py`.
3. The comparison engine, conforming to both.
4. UI — last, and only once the above are green.

The order matters. Built UI-first, the natural shape of a comparison table is a
column of sites and a row of totals, and the eye demands that the totals be
sortable. By the time anyone notices, sorting *is* ranking and the argument for
removing it is "a document said so" rather than "a test fails".
