"""
Professional review — the model, tested with nothing filled in.

There are no reviewers and no reviews in this product. What these tests protect
is the *shape* of the transition, and specifically the four ways a review model
can make evidence less trustworthy rather than more:

    an anonymous or unverifiable endorsement
    a review whose scope is wider than the reviewer's discipline
    a partly-reviewed record that reads as reviewed
    a co-sign that replaces the machine provenance instead of adding to it

Every one of those transfers confidence without transferring responsibility,
which is worse than no review at all — a reader trusts the finding more and has
no more reason to.
"""

from __future__ import annotations

import pytest

import review as review_mod
from review import InvalidReview, Review

GOOD = {
    "reviewer_name": "A. Surveyor",
    "registration": "MCIEEM 12345",
    "discipline": "Ecologist",
    "scope": ["habitat_vegetation_decline"],
    "statement": "The decline is consistent with a change in cutting regime "
                 "rather than deterioration. No further survey advised.",
    "reviewed_at": "2026-08-12T09:00:00Z",
}

RECORD = {
    "record_id": "rec_abc123",
    "findings": [
        {"id": "habitat_vegetation_decline", "kind": "flag",
         "statement": "NDVI declined", "rule": {"threshold": 0.1},
         "threshold": "0.1 index points"},
        {"id": "flood_zone3", "kind": "flag", "statement": "Intersects FZ3",
         "rule": {"threshold": "any"}, "threshold": "any intersection"},
    ],
    "review": {"status": "unreviewed", "reviews": []},
}


# ---------------------------------------------------------------------------
# Unreviewed is a state, not a missing value
# ---------------------------------------------------------------------------
def test_a_record_with_no_reviews_says_so_rather_than_going_quiet():
    """The distinction the whole product rests on, applied to the reviewer
    instead of the check. A record that could not represent review would render
    "nobody has seen this" and "a professional agreed" identically."""
    out = review_mod.apply(RECORD, [])
    assert out["review"]["status"] == "unreviewed"
    assert "No professional has reviewed" in out["review"]["statement"]
    assert out["review"]["reviews"] == []


def test_declined_is_kept_apart_from_unreviewed():
    """A professional who looked and would not sign has told you something
    valuable. Collapsing that into "not reviewed" discards the most important
    review a record can receive."""
    declined = review_mod.validate({**GOOD, "outcome": "declined"})
    out = review_mod.apply(RECORD, [declined])
    assert out["review"]["status"] == "declined"
    assert review_mod.REVIEW_STATES["declined"] != \
        review_mod.REVIEW_STATES["unreviewed"]


# ---------------------------------------------------------------------------
# A review must be checkable
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("field", review_mod.REQUIRED_FIELDS)
def test_every_required_field_is_actually_required(field):
    """Each is required because its absence makes the review unusable rather
    than thinner. An endorsement that looks verifiable and is not transfers
    confidence without transferring responsibility."""
    submission = {**GOOD}
    submission[field] = [] if field == "scope" else ""
    with pytest.raises(InvalidReview) as e:
        review_mod.validate(submission)
    assert field in str(e.value)


def test_a_review_is_refused_rather_than_partially_recorded():
    """Filling in a blank registration would produce an endorsement nobody can
    check, wearing the appearance of one they can."""
    with pytest.raises(InvalidReview):
        review_mod.validate({"reviewer_name": "A. Surveyor"})


def test_the_registration_is_carried_so_a_reader_can_verify_it():
    """"MCIEEM" alone is a claim. "MCIEEM 12345" is a claim someone can check,
    and the whole value of a co-sign is that it is checkable."""
    r = review_mod.validate(GOOD)
    assert r.registration == "MCIEEM 12345"
    assert r.as_dict()["registration"] == "MCIEEM 12345"


def test_an_unknown_outcome_is_refused():
    """There is no "partially". It would leave a reader unable to tell which
    findings were accepted."""
    with pytest.raises(InvalidReview):
        review_mod.validate({**GOOD, "outcome": "probably"})


def test_a_review_is_frozen_once_made():
    """A statement made at a moment by a named person. One that can be edited
    afterwards without anybody knowing defeats the point of recording it."""
    r = review_mod.validate(GOOD)
    with pytest.raises(Exception):
        r.statement = "Something else"      # type: ignore[misc]


# ---------------------------------------------------------------------------
# Scope — the field that matters most
# ---------------------------------------------------------------------------
def test_a_review_covers_the_findings_it_names_and_no_others():
    """An ecologist can speak to a habitat finding and not to a flood-zone
    intersection. A review without a scope would put one specialist's name
    under every finding in the document, including ones they never saw."""
    out = review_mod.apply(RECORD, [review_mod.validate(GOOD)])
    by_id = {f["id"]: f for f in out["findings"]}
    assert by_id["habitat_vegetation_decline"]["reviewed_by"]
    assert by_id["flood_zone3"]["reviewed_by"] == []


def test_a_review_naming_a_finding_the_record_does_not_have_is_refused():
    """The one thing standing between a co-sign and a signature on a blank
    page."""
    stray = review_mod.validate({**GOOD, "scope": ["not_a_finding"]})
    with pytest.raises(InvalidReview) as e:
        review_mod.apply(RECORD, [stray])
    assert "not_a_finding" in str(e.value)


def test_a_review_cannot_be_attached_to_a_different_record():
    """Evidence changes, and a review is a statement about the evidence as it
    stood. Reattaching one to a later record would silently endorse findings
    the reviewer never saw."""
    other = review_mod.validate({**GOOD, "record_id": "rec_somethingelse"})
    with pytest.raises(InvalidReview) as e:
        review_mod.apply(RECORD, [other])
    assert "rec_somethingelse" in str(e.value)


# ---------------------------------------------------------------------------
# A partly-reviewed record must not read as reviewed
# ---------------------------------------------------------------------------
def test_the_unreviewed_findings_are_named():
    """The same discipline the rest of the product applies to evidence. A
    record where one finding of two was reviewed must not read as reviewed."""
    out = review_mod.apply(RECORD, [review_mod.validate(GOOD)])
    assert out["review"]["unreviewed_findings"] == ["flood_zone3"]
    assert "1 of 2" in out["review"]["statement"]
    assert "remain machine assessments" in out["review"]["statement"]


def test_a_fully_reviewed_record_says_so_without_overclaiming():
    """"Within the scope each states" is doing work: it is still not a
    statement that the site is sound."""
    both = review_mod.validate({
        **GOOD, "scope": ["habitat_vegetation_decline", "flood_zone3"]})
    out = review_mod.apply(RECORD, [both])
    assert out["review"]["unreviewed_findings"] == []
    assert "All 2 findings" in out["review"]["statement"]
    assert "within the scope each states" in out["review"]["statement"]


# ---------------------------------------------------------------------------
# Co-signed means both
# ---------------------------------------------------------------------------
def test_a_reviewed_finding_keeps_its_machine_provenance():
    """Co-signed means *both* — the rule that reached it and the professional
    who accepted it. Dropping the first makes the second unverifiable, because
    there is nothing left to check it against."""
    out = review_mod.apply(RECORD, [review_mod.validate(GOOD)])
    finding = out["findings"][0]
    assert finding["rule"] == {"threshold": 0.1}
    assert finding["threshold"] == "0.1 index points"
    assert finding["statement"] == "NDVI declined"
    assert finding["reviewed_by"][0]["reviewer_name"] == "A. Surveyor"


def test_the_reviewer_travels_on_the_finding_not_only_in_a_header():
    """A finding quoted on its own has to carry who stands behind it."""
    out = review_mod.apply(RECORD, [review_mod.validate(GOOD)])
    reviewed = out["findings"][0]["reviewed_by"][0]
    assert reviewed["registration"] == "MCIEEM 12345"
    assert reviewed["discipline"] == "Ecologist"
    assert reviewed["reviewed_at"] == "2026-08-12T09:00:00Z"


def test_apply_never_mutates_the_record_it_was_given():
    """A review is an addition. A function that edited the record in place
    would make the original unrecoverable, and the original is the evidence."""
    original = dict(RECORD)
    review_mod.apply(RECORD, [review_mod.validate(GOOD)])
    assert RECORD == original
    assert RECORD["review"]["status"] == "unreviewed"
    assert "reviewed_by" not in RECORD["findings"][0]


# ---------------------------------------------------------------------------
# Nothing is invented
# ---------------------------------------------------------------------------
def test_no_reviewer_is_defaulted_synthesised_or_generated():
    """Structurally: nothing in this module produces a reviewer. Every review
    that exists came from a caller supplying one."""
    import pathlib
    text = pathlib.Path(review_mod.__file__).read_text().lower()
    for banned in ("faker", "random", "sample_reviewer", "default_reviewer"):
        assert banned not in text


def test_the_specialist_map_is_advisory_and_never_enforced():
    """Whether a professional is competent to review a finding is their
    judgement and their liability, not a lookup this product may make. A review
    outside the mapped discipline is recorded, not refused."""
    out_of_discipline = review_mod.validate({
        **GOOD, "discipline": "Chartered surveyor"})
    out = review_mod.apply(RECORD, [out_of_discipline])
    assert out["review"]["status"] == "reviewed"


def test_land_has_no_named_specialist():
    """It spans ground conditions, terrain, flood, vegetation, ecology and
    planning. Naming one discipline would be an invented claim about who is
    competent to sign the whole thing."""
    assert review_mod.specialist_for("land") == ""
    assert review_mod.specialist_for("ecology") == "Ecologist"
    assert review_mod.specialist_for("nonsense") == ""
