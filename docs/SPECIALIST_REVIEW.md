# Specialist review

**Model implemented, deliberately empty.** `review.py`, 23 tests in
`tests/test_review.py`. No reviewer accounts, no workflow, no submissions.

```
machine assessment  →  professional review  →  co-signed evidence
      exists              modelled                   not built
```

---

## Why an empty model is worth building

The alternative is worse in a specific way. A record whose review status is
**unrepresentable** can only ever be machine output: there is no field to put a
review in, so "no professional has seen this" and "a professional saw this and
agreed" render identically as silence.

That silence is the failure this codebase spends its effort preventing, applied
to the reviewer instead of the check. So `unreviewed` is a **state**, carried
explicitly on every record.

`declined` is kept apart from `unreviewed`. A professional who looked and would
not sign has told you the most valuable thing a review can say, and collapsing
that into "not reviewed" would discard it.

---

## What a review must contain

Refused if any is missing — not recorded with a blank. An endorsement that
*looks* verifiable and is not transfers confidence without transferring
responsibility, which is worse than no review at all.

| Field | Why required |
| --- | --- |
| `reviewer_name` | An anonymous endorsement is not one |
| `registration` | "MCIEEM" is a claim; "MCIEEM 12345" is a claim a reader can check, and checkability is the entire value of a co-sign |
| `discipline` | So a reader can tell whether the scope was within it |
| `scope` | Which findings. See below |
| `statement` | What they are actually saying. "Reviewed" is not a finding |
| `reviewed_at` | A review is a statement about evidence at a moment, and evidence changes |

---

## Scope is the field that matters most

A professional reviews *some* of a record, not all of it. An ecologist can speak
to a habitat finding and not to a flood-zone intersection.

A review recorded without a scope would put one specialist's name under every
finding in the document — including ones outside their discipline, and including
ones they never saw.

So `scope` is a list of finding ids, and `apply` **refuses** a review naming a
finding the record does not contain. That check is the one thing standing
between a co-sign and a signature on a blank page.

A review also carries the `record_id` it was made against, and cannot be
attached to a different one. Evidence changes; reattaching a review to a later
record would silently endorse findings the reviewer never saw.

---

## Two properties to defend

**A partly-reviewed record must not read as reviewed.** The unreviewed findings
are named, and the statement says "1 of 2 findings have been reviewed... the
remaining 1 carries no professional review and remains a machine assessment."
Same discipline the rest of the product applies to evidence.

**Co-signed means both.** A reviewed finding keeps its rule, threshold and
evidence in full. Dropping the machine provenance would make the endorsement
unverifiable — there would be nothing left to check it against.

---

## The specialist map is advisory

`SCANNER_SPECIALISTS` names the discipline that would *ordinarily* own a
scanner's findings. It is never enforced: whether a particular professional is
competent to review a particular finding is their judgement and their liability,
not a lookup this product is entitled to make.

Land has no entry. It spans ground conditions, terrain, flood, vegetation,
ecology and planning, and naming one discipline for it would be an invented
claim about who can sign the whole thing.

---

## What a real workflow needs

Not built, and each depends on a decision the product cannot make alone:

1. **Identity.** Who verifies that this person holds this registration? CIEEM,
   RICS, RTPI and CIfA each publish a register; none has an API this product has
   integrated.
2. **Authentication.** A review is worthless if anyone can submit one under
   another person's name.
3. **What a co-sign means contractually.** Is the reviewer accepting liability
   for the finding, for the interpretation, or only stating that they read it?
   This is a question for a lawyer and a professional body, not an engineer.
4. **Immutability and withdrawal.** A review is frozen once made. A reviewer who
   changes their mind needs a way to withdraw that is visible rather than silent.
5. **Fee handling**, if review is ever paid.

Items 1, 3 and 4 are founder decisions. See the final report.
