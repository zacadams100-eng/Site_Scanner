"""
Professional review — the model, and nothing filled in.

The product's stated direction is:

    machine assessment  →  professional review  →  co-signed evidence

The first exists. The third is what makes the evidence worth more than the
machine that produced it, because a finding a named professional has put their
name to is a different artefact from one a rule produced. This module is the
second: the shape of the transition, with no reviewer in it.

## Why build a model with nothing in it

Because the alternative is worse in a specific way. A record whose review
status is *unrepresentable* can only ever be machine output — there is no field
to put a review in, so the product cannot distinguish "no professional has seen
this" from "a professional saw this and agreed", and both render identically as
silence. That silence is the failure this codebase spends its effort
preventing, applied to the reviewer instead of the check.

So `unreviewed` is a **state**, not a missing value, and every record carries
it explicitly. See `site_record._review_block`.

## What is deliberately absent

No reviewer accounts, no authentication, no signing keys, no workflow. Those
are not deferred out of laziness: each depends on decisions this product has
not made and cannot make alone — who verifies a professional's credentials,
what a co-sign means contractually, which body's registration is authoritative
for each discipline. Building a reviewer table now would encode guesses about
all three.

What can be decided now, and is: **what a review must contain in order to mean
anything.** That is `REQUIRED_FIELDS`, and it is the useful half. A review
without a named person, a verifiable registration, a stated scope and a
timestamp is not a review — it is an endorsement, and an endorsement attached
to evidence is worse than no review at all because it transfers confidence
without transferring responsibility.

## Scope is the field that matters most

A professional reviews *some* of a record, not all of it. An ecologist can
speak to a habitat finding and not to a flood-zone intersection, and a review
recorded without a scope would let one specialist's name sit under every
finding in the document — including the ones outside their discipline and
including the ones they never saw.

So `scope` is required, it is a list of finding ids, and `apply` refuses a
review naming a finding the record does not contain. `SCANNER_SPECIALISTS` maps
a scanner to the discipline that would ordinarily own its findings; it is
advisory and never enforced, because who is competent to review what is a
professional judgement and not a lookup table.

## Never
    - No review is ever synthesised, inferred, defaulted or generated.
    - A review is never partially recorded: `validate` refuses, and the record
      keeps its `unreviewed` state rather than gaining a half-review.
    - A reviewed finding never loses its machine provenance. Co-signed means
      *both* — the rule that reached it and the professional who accepted it —
      and dropping the first would make the second unverifiable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

#: The shape of a review document, versioned like everything else that is
#: stored. A review read in five years has to be interpretable by whatever is
#: reading it then.
REVIEW_SCHEMA = "1.0.0"

#: The states a record's review can be in.
#:
#: `unreviewed` and `declined` are deliberately distinct. A professional who
#: looked and would not sign has told you something valuable, and collapsing
#: that into "not reviewed" would discard the most important review a record
#: can receive.
REVIEW_STATES = {
    "unreviewed": "No professional has reviewed these findings.",
    "reviewed": "A professional has reviewed part or all of this record.",
    "declined": "A professional reviewed this and declined to endorse it. "
                "Their reason is recorded.",
}

#: What a review must contain to mean anything.
#:
#: Each of these exists because its absence makes the review unusable rather
#: than merely thinner:
#:
#: - `reviewer_name` — an anonymous endorsement is not one.
#: - `registration` — the body and number a reader can check. "MCIEEM" alone
#:   is a claim; "MCIEEM 12345" is a claim someone can verify, and the whole
#:   value of a co-sign is that it is checkable.
#: - `discipline` — what they are qualified to speak to, so a reader can tell
#:   whether the scope was within it.
#: - `scope` — which findings. See the module note.
#: - `statement` — what they are actually saying. "Reviewed" is not a finding.
#: - `reviewed_at` — a review is a statement about evidence at a moment, and
#:   evidence changes.
REQUIRED_FIELDS: Tuple[str, ...] = (
    "reviewer_name", "registration", "discipline", "scope", "statement",
    "reviewed_at",
)

#: Which discipline would ordinarily own a scanner's findings.
#:
#: Advisory. Never enforced, and deliberately not used to reject a review:
#: whether a particular professional is competent to review a particular
#: finding is their judgement and their liability, not a lookup this product is
#: entitled to make. It exists so the interface can say "this would normally be
#: reviewed by an ecologist" rather than leaving a user to guess who to ask.
SCANNER_SPECIALISTS: Mapping[str, str] = {
    "ecology": "Ecologist",
    "water": "Flood risk consultant / hydrologist",
    "planning": "Planning consultant",
    "heritage": "Heritage consultant / archaeologist",
    "market": "Chartered surveyor / valuer",
    # Land is absent on purpose. It spans ground conditions, terrain, flood,
    # vegetation, ecology and planning, and naming one discipline for it would
    # be an invented claim about who is competent to sign the whole thing.
}


class InvalidReview(ValueError):
    """A review that cannot be recorded, and why.

    Its own type so a caller can tell a malformed submission from a storage
    failure. The message names the missing field, because the fix is always to
    supply it.
    """


@dataclass(frozen=True)
class Review:
    """One professional's statement about part of one record.

    Frozen. A review is a statement made at a moment by a named person; a
    mutable one is a statement that can be changed after the fact without
    anybody knowing, which defeats the entire purpose of recording it.
    """

    reviewer_name: str
    #: The professional body and registration number, as one verifiable string.
    registration: str
    discipline: str
    #: Finding ids this review covers. Never "all" — see the module note.
    scope: Tuple[str, ...]
    statement: str
    reviewed_at: str
    #: `endorsed` or `declined`. A decline is a review and is recorded as one.
    outcome: str = "endorsed"
    #: The record this review is about, so a review that has been separated
    #: from its record can be reattached — and cannot be attached to a
    #: different one, because the id would not match.
    record_id: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "reviewer_name": self.reviewer_name,
            "registration": self.registration,
            "discipline": self.discipline,
            "scope": list(self.scope),
            "statement": self.statement,
            "reviewed_at": self.reviewed_at,
            "outcome": self.outcome,
            "record_id": self.record_id,
            "review_schema": REVIEW_SCHEMA,
        }


def validate(submission: Mapping[str, Any]) -> Review:
    """Turn a submission into a `Review`, or refuse it with the reason.

    Refuses rather than filling in. A review missing its registration number
    recorded with an empty one would be an endorsement that looks verifiable
    and is not, which is worse than no review — it transfers confidence without
    transferring responsibility.
    """
    missing = [f for f in REQUIRED_FIELDS
               if not (submission.get(f) or "") and f != "scope"]
    if not submission.get("scope"):
        missing.append("scope")
    if missing:
        raise InvalidReview(
            "A review is missing " + ", ".join(sorted(missing)) +
            ". Every one of these is required: an anonymous or unscoped "
            "endorsement transfers confidence without transferring "
            "responsibility, which is worse than no review at all."
        )

    outcome = str(submission.get("outcome") or "endorsed").strip().lower()
    if outcome not in ("endorsed", "declined"):
        raise InvalidReview(
            f"Unknown outcome {outcome!r}. A review either endorses the "
            f"findings in its scope or declines to — there is no third "
            f"answer, and 'partially' would leave a reader unable to tell "
            f"which findings were accepted.")

    return Review(
        reviewer_name=str(submission["reviewer_name"]).strip(),
        registration=str(submission["registration"]).strip(),
        discipline=str(submission["discipline"]).strip(),
        scope=tuple(str(s) for s in submission["scope"]),
        statement=str(submission["statement"]).strip(),
        reviewed_at=str(submission["reviewed_at"]).strip(),
        outcome=outcome,
        record_id=str(submission.get("record_id") or "").strip(),
    )


def apply(record: Mapping[str, Any],
          reviews: Sequence[Review]) -> Dict[str, Any]:
    """A record with reviews attached. Returns a new record; never mutates.

    Refuses a review whose scope names a finding this record does not contain.
    That check is the one thing standing between a co-sign and a signature on a
    blank page: a review recorded against an id that is not here would appear
    in the document as a professional endorsing something invisible.

    A reviewed finding keeps everything it had. Co-signed means *both* — the
    rule that reached it and the professional who accepted it — and dropping
    the machine provenance would make the endorsement unverifiable, because
    there would be nothing left to check it against.
    """
    findings = record.get("findings") or []
    known = {str(f.get("id")) for f in findings}

    for r in reviews:
        unknown = [s for s in r.scope if s not in known]
        if unknown:
            raise InvalidReview(
                f"Review by {r.reviewer_name} names findings this record does "
                f"not contain: {', '.join(sorted(unknown))}. A review recorded "
                f"against a finding that is not here would read as a "
                f"professional endorsing something invisible.")
        if r.record_id and r.record_id != record.get("record_id"):
            raise InvalidReview(
                f"Review by {r.reviewer_name} was made against record "
                f"{r.record_id}, not {record.get('record_id')}. Evidence "
                f"changes, and a review is a statement about the evidence as "
                f"it stood.")

    reviewed = {s for r in reviews for s in r.scope}
    out = dict(record)
    out["findings"] = [
        {**f,
         # Which reviews cover this finding, by name and registration. On the
         # finding rather than only in a header, because a finding quoted on
         # its own has to carry who stands behind it.
         "reviewed_by": [
             {"reviewer_name": r.reviewer_name,
              "registration": r.registration,
              "discipline": r.discipline,
              "outcome": r.outcome,
              "reviewed_at": r.reviewed_at}
             for r in reviews if str(f.get("id")) in r.scope
         ]}
        for f in findings
    ]

    unreviewed_findings = sorted(known - reviewed)
    out["review"] = {
        "status": _status(reviews),
        "statement": _statement(reviews, unreviewed_findings, len(known)),
        "reviews": [r.as_dict() for r in reviews],
        # The gap, named — the same discipline the rest of the product applies
        # to evidence. A record where two findings of nine were reviewed must
        # not read as a reviewed record.
        "unreviewed_findings": unreviewed_findings,
        "review_schema": REVIEW_SCHEMA,
    }
    return out


def empty_block() -> Dict[str, Any]:
    """The review block every unreviewed record carries.

    Lives here rather than in `site_record` so there is **one** definition of
    what "nobody has reviewed this" says. Two wordings of a review boundary
    drift exactly as two wordings of a claim boundary do, and the drift is
    invisible: both look like a sentence somebody wrote on purpose.
    """
    return {
        "status": "unreviewed",
        "statement": _statement([], [], 0),
        "reviews": [],
        "unreviewed_findings": [],
        "review_schema": REVIEW_SCHEMA,
    }


def _status(reviews: Sequence[Review]) -> str:
    if not reviews:
        return "unreviewed"
    if all(r.outcome == "declined" for r in reviews):
        return "declined"
    return "reviewed"


def _statement(reviews: Sequence[Review], unreviewed: Sequence[str],
               total: int) -> str:
    """The sentence a reader sees at the top of the record.

    Composed here so there is one wording of it. Two wordings of a review
    boundary drift, exactly as two wordings of a claim boundary do.
    """
    if not reviews:
        return ("No professional has reviewed these findings. Every finding "
                "here is a machine assessment against a stated threshold.")

    covered = total - len(unreviewed)
    who = ", ".join(f"{r.reviewer_name} ({r.registration})" for r in reviews)
    if unreviewed:
        return (f"{covered} of {total} findings have been reviewed, by {who}. "
                f"The remaining {len(unreviewed)} carry no professional "
                f"review and remain machine assessments.")
    return (f"All {total} findings have been reviewed by {who}, within the "
            f"scope each states.")


def specialist_for(scanner_id: str) -> str:
    """Who would ordinarily review this scanner's findings, or "".

    Empty is a real answer and means no single discipline owns it. Returning a
    plausible-sounding guess would be an invented claim about who is competent
    to sign.
    """
    return SCANNER_SPECIALISTS.get((scanner_id or "").lower(), "")
