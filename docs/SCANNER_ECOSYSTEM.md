# Scanner ecosystem

**Architecture implemented. No marketplace, no contributors, no revenue share.**

What a third party would need in order to contribute a scanner — "Heritage
Scanner v1.2", "Geotechnical Scanner v1.0" — without Site Scanner rewriting its
application.

---

## The contract that already exists

A contributing package implements one function:

```python
def build(rule_class, insufficient_class) -> Sequence[Rule]:
    ...
```

and exports `TOPICS`, `INVESTIGATIONS` and `FACTORS`. It must not import
`radar`; the classes are passed in, so knowledge flows one way.

This is not a contract designed for contributors. It is the contract
`historical.rules` has used since before multi-scanner work began, and it has
now carried two more packages — `habitat.rules` and `coastal.rules` — **with no
engine change for either.** That is the evidence that it would carry a third
party's, and it is stronger evidence than a specification would be, because it
has been exercised rather than imagined.

---

## What is missing before an outside party could use it

Each is a real gap, named rather than glossed:

| Missing | Why it matters |
| --- | --- |
| **Isolation** | `rules_from` imports and calls arbitrary code in-process. A contributed package can read the filesystem and the network. Fine for first-party packages; unacceptable for third-party ones. |
| **Versioning of the contract itself** | `Rule.__init__` is the contract. A signature change today breaks every contributor silently. |
| **Threshold review** | A contributed threshold is a scientific claim. Nothing checks it, and this product's whole discipline is that a threshold says whose it is. |
| **Provenance for contributed sources** | A contributor's factors must carry publisher, endpoint, licence and runtime state to the same standard. Nothing enforces the shape. |
| **Attribution and licensing** | Whose data, under what terms, and who is liable if it is wrong. |
| **Identity** | Who *is* this contributor, and what does the product assert about them by listing their scanner? |

The first two are engineering. The last four are business and legal decisions,
and they are the reason this is architecture rather than a marketplace.

---

## The two roles a specialist could hold

They are different and should not be conflated.

**Contributor** — writes a scanner. Supplies rules, thresholds, factors and a
methodology. Their name attaches to the *instrument*.

**Reviewer** — reviews findings on a specific site. Supplies a registration, a
scope and a statement. Their name attaches to the *evidence*. Modelled in
`review.py`; see `docs/SPECIALIST_REVIEW.md`.

A heritage consultant might do either. The liability is different in each case,
and a product that let one person do both under one label would be obscuring
which they had done.

---

## Where this could go, stated as possibility

Not a plan. Recorded because it is the reason to keep the contract clean:

1. **First-party specialist scanners.** Heritage is the obvious next one — the
   National Heritage List is open data under OGL and the blocker is ingestion
   work, not licensing or sourcing.
2. **Commissioned scanners.** A specialist paid to write one, published by Site
   Scanner, reviewed before it ships. No isolation needed — the review is the
   control.
3. **Third-party scanners.** Needs everything in the table above.
4. **Review as a service.** A professional co-signs findings on a site for a
   fee. Needs `review.py` plus identity, verification and a workflow.

Option 2 is reachable without any of the missing infrastructure, which makes it
the one worth considering first.

---

## What must never happen

- A contributed scanner presenting a finding without a stated threshold, a claim
  boundary and provenance. The evidence principles are not per-scanner.
- A contributor's name on a finding they did not review, or a reviewer's name on
  a scanner they did not write.
- A marketplace listing that implies verification nobody performed. Listing is
  not endorsement, and if the interface cannot make that clear, the listing
  should not exist.
