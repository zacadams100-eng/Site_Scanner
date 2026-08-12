"""
The Site Evidence Record — the canonical form of one assessment.

Everything else in this product is a view. This is the thing itself: what was
observed about a place, when, by which scanner, at which version, from which
source, and what a professional was told it did and did not establish.

    site → assessment → factor → evidence → finding → investigation
                                                    → review
                                                    → brief

## Why this exists as its own module

The product already assembles all of this. `radar` reaches the findings,
`evidence` joins them to their sources, `investigation` builds the workspace,
`brief` composes the artefact that leaves the building. What none of them
produces is a form that is **stable, addressable and comparable over time** —
they all shape the same assessment for a particular screen.

The difference matters as soon as there are two assessments. "Has this site
changed since March?" cannot be answered by two briefs, because a brief is
prose in a fixed order and its identifiers are internal to one run. It can be
answered by two records, because a record has stable identifiers and states its
own version.

That capability is the reason to build this now rather than when it is needed:
a longitudinal record can only be assembled from assessments that were
*recorded* in a comparable form at the time. Nothing can retrofit it, and the
records this product does not keep today are the ones it can never compare
tomorrow.

## What is derived, and what is never invented

Everything here is read from an assembled `/api/series` payload. This module
evaluates no rule, crosses no threshold, decides no state and composes no
claim — the same contract `evidence.py` and `brief.py` hold, and for the same
reason: a second module that could reach a finding is a second opinion waiting
to drift.

Specifically **not** here, and deliberately:

- No score, index, grade or rollup of findings into a number. `EM7`.
- No comparison against another record. Comparing two records is a real
  feature and it belongs to whatever holds a series of them; a record that
  described its own change would need to carry another record inside it.
- No specialist review content. `SpecialistReview` is defined and every record
  carries an empty list, because no professional has reviewed anything. The
  shape exists so that when one does, the record can hold it; inventing a
  reviewer would be the worst fabrication available in this codebase.

## Identifiers

Two, and they answer different questions.

`site_id` is derived from the geometry. The same polygon assessed in March and
in August produces the same site id, which is what makes a longitudinal record
possible without asking a user to name and re-find a site. It is a content
hash, so it is stable across processes, deployments and database resets — a
counter or a UUID would give the same ground two identities and quietly break
every comparison.

`record_id` is derived from the site, the scanner, the versions and the
evidence. Two identical assessments of one site collapse to one id; anything
that would change what a reader sees changes it. That makes it safe to store
and safe to deduplicate, and it means a record cannot be edited without
becoming a different record — which is the property an auditable evidence trail
actually needs.

Both are prefixed (`site_`, `rec_`) so an identifier in a log or a URL says
what kind of thing it is without a lookup.

## Versioning

Three versions travel with every record, and they are three different
questions a reader of an old record asks:

- `scanner_version` — did the checks change?
- `methodology_version` — did the meaning of "assessed" change?
- `record_schema` — did the shape of this document change?

Collapsing them into one would make every rule addition look like a schema
migration, and a reader trying to work out whether a two-year-old record is
still comparable would have no way to tell.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional, Sequence

import review

#: The shape of this document. Bumped when a field is added, removed or
#: changes meaning — never for a change in the *values* a field carries.
#:
#: A stored record states the schema it was written under, so a reader two
#: years from now can tell "this field was absent" from "this field was empty",
#: which are different facts about a site and are indistinguishable without it.
RECORD_SCHEMA = "1.0.0"

#: What the assessment engine itself is. Distinct from any scanner's version:
#: this changes when the shared machinery changes — how coverage is counted,
#: how a state is decided — which affects every scanner's output at once.
ENGINE_VERSION = "1.0.0"

#: The states a factor can be in, and the whole point of the model. Listed here
#: because a record is read by things that were not built alongside it, and the
#: vocabulary has to travel with the document rather than living in a component.
#:
#: `clear` and `not_assessed` being different is the product. Everything else
#: in this codebase exists to keep them apart.
EVIDENCE_STATES = {
    "flagged": "A check crossed a reporting threshold.",
    "informational": "A measurement was taken; it is neither good nor bad.",
    "clear": "The check ran against real data and nothing crossed.",
    "not_assessed": "The check could not run. Nothing was established.",
}


def _canonical(value: Any) -> str:
    """Stable JSON for hashing.

    Sorted keys and no incidental whitespace, so two structurally identical
    payloads hash identically regardless of the order a dict happened to be
    built in. Without this the identifiers would be stable within one process
    and different across two, which is the worst kind of stable — it looks
    right in tests and fails in production.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      default=str)


def _digest(value: Any, *, prefix: str, length: int = 16) -> str:
    return f"{prefix}{hashlib.sha256(_canonical(value).encode()).hexdigest()[:length]}"


def site_id(geometry: Dict[str, Any]) -> str:
    """A stable identifier for a piece of ground.

    Derived from the geometry so that the same shape is the same site whenever
    and wherever it is assessed. This is what makes a longitudinal record
    possible without a user account, a saved-sites table or a naming
    convention — and it is why a UUID would be wrong here: two assessments of
    one field would become two sites, and the change between them would be
    unobservable.

    Rounded to six decimal places (~0.1 m) before hashing. A drawn polygon
    carries float noise from the map's projection, and without rounding the
    "same" shape redrawn or round-tripped through a permalink would hash
    differently — which would break exactly the case this identifier exists to
    serve. Six places is well below the accuracy of any source here, so the
    rounding cannot merge two genuinely different sites.
    """
    return _digest(_rounded(geometry), prefix="site_")


def _rounded(value: Any, places: int = 6) -> Any:
    if isinstance(value, float):
        return round(value, places)
    if isinstance(value, list):
        return [_rounded(v, places) for v in value]
    if isinstance(value, dict):
        return {k: _rounded(v, places) for k, v in value.items()}
    return value


def _observations(evidence: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One entry per factor the assessment touched, with its provenance.

    A flat list rather than a nested tree. A record is read by machines as
    often as by people — a portfolio counting evidence gaps across a thousand
    sites should not have to walk a tree to find them — and the relationships
    are carried by identifier rather than by nesting.
    """
    out: List[Dict[str, Any]] = []
    for e in evidence:
        source = e.get("source") or {}
        out.append({
            "factor": e.get("factor"),
            "name": e.get("name") or e.get("factor"),
            "state": e.get("state"),
            # Why, when the state is `not_assessed`. The difference between
            # "no source answered" and "the source answered with nothing
            # usable" is the difference between a gap someone can close and one
            # they cannot.
            "reason": e.get("reason"),
            "observed_at": e.get("assessed_at") or "",
            "source": {
                "publisher": source.get("publisher", ""),
                "endpoint": source.get("endpoint", ""),
                "dataset": source.get("dataset", ""),
                "licence": source.get("licence", ""),
                "attribution": source.get("attribution", ""),
                # Whether this deployment has actually run it live. `EM5`
                # insists this is not the same as an entry existing in a
                # registry, and a stored record is precisely where that
                # distinction would otherwise be lost.
                "runtime": source.get("runtime", "unknown"),
                "kind": source.get("kind", "unknown"),
            },
            # The claim boundary, carried rather than recomposed. A record that
            # restated it in its own words would be a second wording of one
            # boundary, and the drift would be invisible.
            "claims": e.get("claims") or {},
        })
    return out


def _findings(evidence: Sequence[Dict[str, Any]],
              rule_domains: Dict[str, str]) -> List[Dict[str, Any]]:
    """Every finding, addressed to the factor and the domain that raised it.

    `domain` is the field that makes a record useful to a portfolio: "eleven
    sites have a finding in Water's coastal domain" is a question an owner
    actually asks, and it cannot be answered from a rule id without knowing the
    taxonomy at read time.
    """
    out: List[Dict[str, Any]] = []
    for e in evidence:
        for f in e.get("findings") or []:
            out.append({
                "id": f.get("id"),
                "factor": e.get("factor"),
                "domain": rule_domains.get(str(f.get("id")), ""),
                "kind": f.get("kind"),
                "severity": f.get("severity"),
                "statement": f.get("text") or "",
                "threshold": f.get("threshold") or "",
                "evidence": f.get("evidence") or {},
                # The rule's own description of itself — what kind of threshold
                # it is and what it is not evidence of. Carried whole because a
                # record read in two years has no access to the rule that
                # raised it.
                "rule": f.get("rule_meta") or {},
            })
    return out


def _investigations(radar_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The professional follow-up each finding prompts.

    `raised_by` keeps the chain traceable in both directions, which is what
    makes the record auditable rather than merely complete: a reader can go
    from an investigation back to the measurement that caused it.
    """
    return [
        {
            "id": inv.get("id"),
            "name": inv.get("name"),
            "priority": inv.get("priority"),
            "raised_by": list(inv.get("why") or []),
        }
        for inv in (radar_payload.get("investigations") or [])
    ]


def _gaps(observations: Sequence[Dict[str, Any]],
          scanner: Optional[Any]) -> Dict[str, Any]:
    """What this assessment could not establish, at both levels it can fail.

    **Factor gaps** — a check that could not run. Counted from the record's own
    observations.

    **Domain gaps** — a part of the scanner's subject that has no checks at
    all. This is the more dangerous of the two and the one a report cannot
    show, because there is nothing in the payload to point at: Water returning
    no groundwater finding looks identical whether groundwater was clear or was
    never asked. Named from the registry so the record carries the shape of its
    own ignorance.
    """
    by_reason: Dict[str, int] = {}
    factors: List[Dict[str, str]] = []
    for o in observations:
        if o["state"] != "not_assessed":
            continue
        reason = o.get("reason") or "unknown"
        by_reason[reason] = by_reason.get(reason, 0) + 1
        factors.append({"factor": o["factor"], "reason": reason})

    domains = [
        {"id": d.id, "name": d.name, "subject": d.subject,
         "blocked_by": d.blocked_by}
        for d in (scanner.declared_domains if scanner is not None else ())
    ]
    return {
        "factors": factors,
        "by_reason": by_reason,
        "factor_count": len(factors),
        "domains": domains,
        "domain_count": len(domains),
    }


def _review_block() -> Dict[str, Any]:
    """The specialist review slot, defined and empty.

    Every record carries this and every record carries it empty. No
    professional has reviewed any finding this product has produced, and the
    field says so in a form a reader cannot mistake for a review that happened.

    The shape is here rather than deferred because it changes what the record
    *is*: an evidence record whose review status is unrepresentable can only
    ever be a machine output, and the product's stated direction is
    machine assessment → professional review → co-signed evidence. The slot is
    the architecture; filling it is a workflow that does not exist yet.

    Composed by `review.py` rather than written out here, so that there is one
    definition of the unreviewed state and one wording of it. `review.apply`
    replaces this block when a review actually arrives, and a second wording
    living here would drift out of step with it invisibly — both would look
    like a sentence somebody wrote on purpose.

    See `docs/SPECIALIST_REVIEW.md` for the model and what a real one requires.
    """
    return review.empty_block()


def build(payload: Dict[str, Any], *, scanner: Optional[Any] = None,
          site_name: str = "", assessed_at: str = "") -> Dict[str, Any]:
    """The record, assembled from an already-assessed payload.

    Takes the whole `/api/series` response for the same reason `brief.build`
    does: every part is a projection of one assessment, and assembling it from
    several would produce a record that was internally consistent and wrong.

    `scanner` is the resolved `Scanner`. Optional so a record can still be
    built from a stored payload whose scanner is no longer registered — a
    record that could not be read after a scanner was retired would defeat the
    purpose of keeping records at all. Where it is absent, the scanner block
    reports what the payload knows and the domain gaps are empty rather than
    invented.
    """
    radar_payload = payload.get("radar") or {}
    evidence = payload.get("evidence") or []
    geometry = payload.get("geometry") or {}
    rule_domains = dict(getattr(scanner, "rule_domains", {}) or {})

    observations = _observations(evidence)
    findings = _findings(evidence, rule_domains)

    site = {
        "id": site_id(geometry) if geometry else "",
        "name": site_name or "Untitled site",
        "geometry": geometry,
        "area_ha": payload.get("area_ha"),
        "centroid": payload.get("centroid") or {},
    }

    scanner_block = {
        "id": getattr(scanner, "id", "") or (
            radar_payload.get("scanner") or ""),
        "name": getattr(scanner, "name", ""),
        "family": getattr(scanner, "family", ""),
        "version": getattr(scanner, "version", ""),
        "methodology_version": getattr(scanner, "methodology_version", ""),
        # `partial` here is load-bearing: it tells a reader of the record that
        # the scanner did not cover its whole subject, which no count of
        # findings can convey.
        "status": getattr(scanner, "status", ""),
        "domains": [
            {"id": d.id, "name": d.name, "implemented": d.implemented}
            for d in getattr(scanner, "domains", ())
        ],
    }

    body = {
        "site": site,
        "scanner": scanner_block,
        "assessed_at": assessed_at,
        "observations": observations,
        "findings": findings,
        "investigations": _investigations(radar_payload),
        "gaps": _gaps(observations, scanner),
        "coverage": radar_payload.get("coverage") or {},
        "review": _review_block(),
        "limits": radar_payload.get("limits", ""),
        "principle": radar_payload.get("principle", ""),
    }

    return {
        # Identity first, so a truncated or streamed record is still
        # addressable.
        "record_id": _digest(
            # Deliberately excludes `assessed_at`: two identical assessments
            # of one site are one record, and including the clock would make
            # every re-run a new document with nothing different in it.
            {k: v for k, v in body.items() if k != "assessed_at"},
            prefix="rec_"),
        "record_schema": RECORD_SCHEMA,
        "engine_version": ENGINE_VERSION,
        **body,
    }


def summarise(record: Dict[str, Any]) -> Dict[str, Any]:
    """The one-line form, for a list of many records.

    A portfolio of a thousand sites cannot hold a thousand full records in a
    table, and the summary is what a row shows. It is derived from the record
    rather than computed alongside it, so a row and the document it opens
    cannot disagree.

    **Counts, never a score.** `flagged` is a count of findings, not a rating,
    and `not_assessed` sits beside it at the same weight on purpose — a row
    showing "3 findings" without "18 unassessed" invites exactly the reading
    this product exists to prevent.
    """
    observations = record.get("observations") or []
    findings = record.get("findings") or []
    states: Dict[str, int] = {}
    for o in observations:
        states[o["state"]] = states.get(o["state"], 0) + 1

    return {
        "record_id": record.get("record_id", ""),
        "site_id": (record.get("site") or {}).get("id", ""),
        "site_name": (record.get("site") or {}).get("name", ""),
        "area_ha": (record.get("site") or {}).get("area_ha"),
        "scanner": (record.get("scanner") or {}).get("id", ""),
        "scanner_status": (record.get("scanner") or {}).get("status", ""),
        "assessed_at": record.get("assessed_at", ""),
        "flagged": sum(1 for f in findings if f.get("kind") == "flag"),
        "informational": sum(1 for f in findings if f.get("kind") == "info"),
        "investigations": len(record.get("investigations") or []),
        "factors_assessed": states.get("clear", 0) + states.get("flagged", 0)
                            + states.get("informational", 0),
        "not_assessed": states.get("not_assessed", 0),
        "domain_gaps": (record.get("gaps") or {}).get("domain_count", 0),
        "review_status": (record.get("review") or {}).get("status", ""),
    }
