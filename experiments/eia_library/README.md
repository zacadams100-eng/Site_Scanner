# Spike: is a shared EIA library safe to build?

**This is a measurement, not a feature.** Nothing here is imported by the app,
mounted on a route, or shipped. It exists to answer one question before anybody
writes an upload button.

The competitive context doc puts a user-contributed library of environmental
assessments at item 11 and is explicit that the incentive, attribution and
anonymisation design must be settled *first* — "do not build the raw upload
mechanic before that design is settled, or the feature launches empty and never
recovers". Of the five prerequisites it names, one is a safety gate rather than
a design preference:

> automatic stripping of client/site-identifying detail

If that cannot be done reliably, the feature is not "less good". It is a
mechanism for publishing a developer's client list, unbuilt land holdings and
protected-species locations to strangers, under this project's name. So it gets
measured before it gets built.

## What is tested here

| | Question | File |
| --- | --- | --- |
| A | Can identifiers be stripped from EIA text without destroying the findings? | `deidentify.py`, `corpus.py` |
| B | Does the retained *geometry* re-identify the site anyway? | `spatial.py` |

`python3 -m experiments.eia_library.report` runs both and prints the numbers.
`tests/test_eia_deid.py` runs the same checks in CI.

## What is not tested here, and why

**Cold-start seeding.** The doc wants the library pre-filled with public-sector
EIAs so it does not launch empty. Whether enough exist in a machine-readable
form is a question about the outside world, and this sandbox's proxy refuses
every host that could answer it (`BLOCKERS.md §1`). Untested, and it is the
other thing that decides whether this feature is viable.

**PDF extraction.** Worth measuring, but it is downstream of the safety gate:
there is no point proving we can read an EIA if we cannot then publish it.

**Give-to-get and attribution.** Incentive design. Not a thing code can answer.

## How much this test is worth

Less than it looks, and the asymmetry is the point.

The corpus in `corpus.py` was written by the same author as the redactor it
scores. That makes a **failure meaningful and a pass weak**: if the redactor
leaks on text written by someone who knew what the redactor does, it will
certainly leak on a real consultancy's report. A clean score proves only that
the obvious cases are handled.

This is the same trap as `scripts/check_real_ndvi.py`, recorded under "A tick
is not a verification" in `HANDOFF.md`: the first NDVI run printed a tick
because every value fell inside −1..1, which a pipeline averaging unmasked
cloud passes comfortably. So the corpus is split — `DEV_CORPUS` was used while
writing the redactor, `HELDOUT_CORPUS` was written first and not looked at
again until the redactor was finished. The held-out number is the one to quote.

A real answer needs a few hundred genuine EIA PDFs and somebody who is not the
author checking the output. That is the next step if these numbers justify one.
