# The evidence model

Contour's core domain specification. Not a style guide and not a set of
preferences — these are invariants, and `tests/test_evidence_model.py` enforces
every one of them by number.

The point of writing them down here is that the reasoning is not obvious from
any single line of code. A future developer reading `radar.py` will find a
function that refuses to produce a result and may reasonably think it is being
unhelpful. It is not. It is the product.

---

## What Contour claims to be

Most site-analysis tools answer *what is here*. Contour answers a harder and
more useful question:

> What have we actually established about this site, what did we check and
> find clear, what did we find concerning, and what could we not establish at
> all — and does that distinction survive all the way into the report?

Everything below exists to keep that last clause true. The distinction is easy
to make in an API response and easy to lose in a UI, an export, a PDF or a
sales deck, and it is worth nothing if it is lost at any of them.

**A clear result means we checked. An empty result means we could not.**

That sentence ships in every `/api/series` response as `radar.principle`, so it
travels with the data rather than living in a design document.

---

## The invariants

Each is enforced by a test named `test_em<N>_...` in
`tests/test_evidence_model.py`. If you are changing behaviour and one of those
fails, the correct response is almost never to change the test.

### EM1 — Generated data cannot trigger a flag

Two thirds of the catalogue is demo data. A flag is judgement-shaped, and
people act on conclusions without checking them. A caveat protects a
*measurement* ("NDVI fell 12%, demo data") far better than it protects a
*recommendation* ("commission a ground investigation, demo data") — the second
has done its damage by the time anyone reads the parenthesis.

### EM2 — Generated data cannot produce `clear`

The load-bearing one. "Generated data indicates no flood risk" is not the same
claim as "we checked the Environment Agency's dataset and found none", and the
two must never render as the same green tick. `clear` requires real **and**
assessed **and** below threshold.

### EM3 — Generated data cannot produce an informational finding

An informational finding is not actionable, which makes it feel harmless. It is
not: "this site averages 61 m elevation" is a fabricated fact about a real
place whether or not anyone acts on it. Informational findings are bound by
exactly the same rule as flags.

### EM4 — Partial topic coverage cannot produce a topic-level `clear`

The same overstatement one level up. A topic with three indicators where one
was read is not a clear topic. It is `partial`, and it says which indicator was
read and which was not.

### EM5 — `verified` means verified in the current runtime

Not merely present in a provenance registry. `REAL_SOURCES` keeps an entry once
an installer has written one; `REAL_SERIES` is what this process can actually
call. A deployment with no Earth Engine credentials implements 27 factors and
can prove none of them. This invariant exists because it was violated: the
capability endpoint reported `verified: true` for a factor whose implementation
had never been installed.

### EM6 — Missing data cannot become zero

A false zero is worse than a labelled gap. An unreadable geometry, a wrong
attribute name, a blocked licence and an empty response must all **raise**
rather than return `0.0`, because 0% reads as a measurement and a measurement
of zero is a strong claim. `open_data._coverage` raises when no feature is
areal; the radar never substitutes a default for a missing level.

### EM7 — No score, rating, grade or overall assessment

The most commercially attractive wrong turn available to this product. A score
hides its own inputs, and the entire argument for the tool is that it shows
them. Coverage is reported as coverage — *how much we could look at* — and
never as quality: a site at 90% coverage is not better than one at 50%, we
simply know more about it.

The test greps the payload keys for `score`, `rating`, `grade`, `suitability`
and `overall`. It exists because "users probably want an overall site score" is
a sentence someone will say, sincerely, in about eighteen months.

### EM8 — Investigations identify what to check, never whether a site is suitable

Naming a survey is not advice. "Commission a flood risk assessment" is a
consequence of an observation; "this site is suitable for development" is a
professional opinion, and it belongs to the person whose name goes on the
report. Every investigation traces to the flags that raised it and stops there.

### EM10 — Comparison describes differences; it never ranks

Comparison may describe differences between sites. It must not produce an
overall ranking, score, grade, suitability assessment, recommendation or
winner, and it must not order sites in a way that implies preference.

EM7 already forbids scores across the whole product. EM10 exists separately
because comparison is the first feature that will actively tempt someone to
break EM7 — the user asks "which is best?" in plain language, the answer feels
helpful, and a sortable total column arrives without anyone deciding to add
ranking.

It carries one further rule that has no equivalent elsewhere: **a flag count
may never be presented without its coverage.** Fewer flags can mean less looked
at, and a comparison that hides that misleads in favour of the least
investigated site. See `COMPARISON_CONTRACT.md`.

### EM9 — Every claim is traceable

Factor, source, publisher, timestamp and assessment state, for every flag,
every informational finding and every factor any rule wanted. The assessment
log is the audit trail: a report read in three months can be *understood*
rather than trusted.

---

## The capability contract

`/api/capabilities` is the contract between backend and frontend. The frontend
must not ask "does this factor exist" — it must ask **what can Contour honestly
claim about this factor right now**, and derive its behaviour from the answer.

The distinction is not academic. It was violated once already: the radar
offered "add this layer" for factors with no real implementation, so the button
led straight to "not assessed — demo data". The UI had inferred a capability
from the catalogue instead of asking what the runtime could do.

Five fields, kept apart because conflating them is how the guessing starts:

| Field | Question it answers |
| --- | --- |
| `implemented` | Is there code to fetch this for real? |
| `real` | Did that code get installed in **this** process? |
| `verified` | Has anyone run it live and checked the answer? |
| `licence_status` | Commercial clearance — `blocked` is refused before fetch |
| `supports_radar` / `supports_investigation` | Does any rule read it, and can that rule raise an investigation? |

**Rule: the UI must never imply an evidence capability the backend does not
possess.** If a control offers an action, the capability payload must say that
action is available.

---

## What this model does not do

It does not make Contour correct. A factor can be real, verified, licensed and
still be measuring the wrong thing; a threshold can be badly chosen; a rule can
be wrong about what a flag implies. These invariants constrain what the system
is permitted to *claim*, not whether the claim is right.

It also does not make Contour compliant. See `LEGAL_RISK_REGISTER.md`.

What it does is make it mechanically difficult for Contour to lie — which is a
narrower promise than trustworthiness, and the only one a piece of software can
actually keep.
