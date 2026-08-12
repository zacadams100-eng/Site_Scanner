# The Site Scanner Evidence Standard

A statement of what this product guarantees about every number it shows, and
what it refuses to do. It is written as a standard rather than as a description
because the intention is that it outlives any one implementation — and because
a standard is checkable, which a promise is not.

**Status: internal.** Nine of the ten principles are enforced by tests in this
repository today; each names them. It has not been reviewed externally, is not
endorsed by any body, and is not a recognised standard. Saying otherwise would
break the first principle.

---

## The one sentence

> Site Scanner prepares the question. It does not answer it.

The product establishes evidence about a place, states what that evidence does
not settle, and names what a professional should look at next. It does not
score a site, rank one against another, or say whether somewhere is suitable for
anything. Those are professional judgements and they belong to the person whose
name goes on the report.

---

## The ten principles

### 1. A check that could not run reports *not assessed*, never *clear*

Silence is not safety. The difference between "we looked and found nothing" and
"we could not look" is the entire product, and every layer preserves it — the
rule, the topic, the factor, the record, the portfolio row.

*Enforced:* `tests/test_evidence_model.py`, `test_three_scanners.py::test_an_unassessed_topic_is_never_reported_as_clear`, `test_site_evidence_record.py`, `test_portfolio.py::test_an_unassessed_site_is_not_reported_as_clear`.

### 2. Generated data may never produce a finding

Only `earth-engine` and `open-data` sources can raise a flag. The mock backend
stamps every response `X-Contour-Mock: true` and the interface says so. A
generated number is a fabricated fact about a real place whether or not anyone
would act on it.

*Enforced:* `tests/test_mock_header_contract.py`, `test_radar.py`.

### 3. Every threshold says whose it is

Thresholds chosen by this product are labelled **product-defined** and are never
described as regulatory, statutory or scientific consensus. Where nobody
qualified has checked one, it says `unvalidated` and states what validating it
would take.

*Enforced:* `tests/test_threshold_validation_visible.py`, `test_three_scanners.py::test_no_threshold_is_presented_as_regulatory`.

### 4. Every finding states what it does not establish

`not_established` is never empty. A claim boundary that goes missing on some
path is worse than none, because a reader learns to expect it and reads its
absence as "nothing to qualify here".

*Enforced:* `claims.py` is the only module permitted to word a boundary;
`tests/test_evidence_model.py` (EM12), `test_site_evidence_record.py`.

### 5. Provenance is four facts, not one

Publisher, endpoint, licence, and whether *this deployment has actually run it*.
"We wrote it" must never reach a user as "we ran it" — `written` and `verified`
are different states and are shown differently.

*Enforced:* `tests/test_catalogue_audit.py`, `evidence.py::_source_block`.

### 6. Coverage is stated at the domain level, not the scanner level

"Water: partial" is a claim nobody can check. "Water covers flood, surface water
and coastal exposure, and does not cover groundwater, drainage or catchment" is
one a professional can act on. Every unbuilt domain names its specific blocker.

*Enforced:* `scanners._check_registry`, `tests/test_scanner_registry.py::test_every_declared_domain_says_what_is_missing`.

### 7. No score, index, grade or rank — at any level

Not per finding, not per site, not per portfolio. The value is evidence,
transparency and investigation; a single number is the same thing with the
reasoning removed, and it is the one change that would make this product
actively harmful. Ordering is permitted where the row shows the values that
produced it.

*Enforced:* `tests/test_site_evidence_record.py::test_the_record_contains_no_score_grade_or_index`, `test_portfolio.py::test_the_portfolio_document_contains_no_score_or_ranking_value` — both grep the served document.

### 8. Demonstration data is identifiable wherever it appears

Generated content carries its label on the document, on the row and on the
record — not in a legend, because a legend does not survive a row being copied,
exported or screenshotted. It is set at creation and never inferred from a name
or a location.

*Enforced:* `tests/test_portfolio_route.py` (six tests, one per path a fragment
can take out of the product).

### 9. Evidence is versioned and addressable

Every record carries three versions — scanner, methodology, schema — because a
reader of an old record asks three different questions. Identifiers are content
hashes: the same ground is the same site, and a record cannot be edited without
becoming a different record.

*Enforced:* `tests/test_site_evidence_record.py` (identity and versioning
sections).

### 10. Machine assessment and professional review are distinct states

`unreviewed` is a state, not a missing value. A review requires a named person,
a verifiable registration, a stated scope and a timestamp, or it is refused. A
co-signed finding keeps its machine provenance in full.

*Enforced:* `tests/test_review.py`.

---

## What the standard does not cover

Named because an unstated limit reads as a covered one — which is principle 1
applied to this document.

- **Accuracy of a source.** The standard governs how evidence is *handled*, not
  whether the Environment Agency's flood zones are right. A wrong source
  faithfully reported is still wrong.
- **Fitness for a decision.** Whether the evidence assembled is sufficient for a
  particular decision is a professional judgement.
- **Completeness of coverage.** The standard requires the gaps be named, not
  that there be none. Most of this catalogue is not yet real data.
- **Legal compliance.** Nothing here is legal advice. `LEGAL_RISK_REGISTER.md`
  is the honest account of what has and has not been checked.

---

## Why this could matter commercially

Not stated as a plan, because it depends on adoption this product has not
earned. But the shape of the opportunity is worth recording, since it is the
reason to hold the line when a feature would break a principle:

Fragmented land due diligence has no common form. Evidence arrives as PDFs,
emails, screenshots and spreadsheets, and the recipient cannot tell what was
checked from what was skipped. A standard form that is **auditable** — provenance
attached, gaps named, thresholds disclosed, review status explicit — is worth
more to the person receiving it than to the person producing it. That is the
condition under which a format spreads.

Every principle above is a constraint on this product and simultaneously the
asset. A competitor can copy a scanner in a quarter. Copying a discipline
requires them to also give up the site score, which is what their sales team
wants most.
