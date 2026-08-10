"""
The evidence explorer — what Contour established about one factor, and what it
did not.

A read over an assembled payload. Nothing here evaluates a rule, crosses a
threshold or decides a state: the engine has already done all of that, and this
module joins its output into one per-factor view. Same contract as
`historical/view.py`, and for the same reason — a second module that could
reach a finding is a second opinion waiting to drift.

## Why the claim boundary lives here and not in the browser

The valuable half of this feature is the pair of statements at the end of every
entry: **what this establishes** and **what this does not establish**. They are
the difference between

    measurement → diagnosis          (what a reader does by default)
    measurement → investigation      (what Contour actually supports)

and getting that wrong is the specific way this product would mislead a
professional who trusts it. So the sentences are composed next to the engine
that reached the state, travel in the payload, and are asserted by tests —
rather than being written into a component where they would be one refactor
away from drifting out of step with the rule they describe.

`not_established` is never empty. A claim boundary that goes missing on some
path is worse than none, because the reader learns to expect it and reads its
absence as "nothing to qualify here".
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import catalog
import licensing


# ---------------------------------------------------------------------------
# The clauses
# ---------------------------------------------------------------------------
#: Applied to every flagged result. HE9: a metric is an observation and does not
#: become an environmental conclusion. EM8: naming a survey is not advice, and a
#: reporting threshold is not a regulatory test.
CAUSAL_LIMIT = (
    "It does not establish why the change occurred. A measurement identifies "
    "what changed, not what caused it."
)

REGULATORY_LIMIT = (
    "Contour's reporting thresholds are product-defined. Crossing one is not a "
    "breach of any regulatory or scientific standard, and this result is not a "
    "regulatory determination."
)

#: Applied wherever nothing could be measured. The single most over-read
#: distinction in the product: a factor that could not be measured is *unknown*,
#: and unknown is not clear.
ABSENCE_LIMIT = (
    "This is not a finding of absence. A factor that could not be measured is "
    "unknown, not clear, and nothing here supports a conclusion either way."
)

#: Applied to `clear`. The reason `clear` needs a limit at all is that it is the
#: state most likely to be quoted as a clean bill of health, and it is a
#: statement about one check rather than about the site.
CLEAR_LIMIT = (
    "It does not establish that the site is free of risk in this topic. One "
    "check did not cross one threshold; other checks in the same topic may not "
    "have run at all."
)

#: Applied to informational readings, which feel harmless precisely because
#: they are not actionable.
INFORMATIONAL_LIMIT = (
    "No threshold was applied and no assessment was made. This is a "
    "measurement, not a judgement about whether the value is good or bad."
)


def _source_block(factor_id: str, series: Dict[str, Any],
                  row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Publisher, endpoint, licence and runtime verification, kept apart.

    Four different questions that a single "Source: Environment Agency" line
    collapses into one:

    - **Publisher** — whose data it is.
    - **Endpoint** — which service actually answered. Sentinel-2 reaches this
      product *through Earth Engine*, which does the cloud masking and
      compositing; a user told only "Copernicus" would look for the number in
      the Copernicus Data Space and find a different one (HE1).
    - **Licence and attribution** — what the terms require, which is a fact
      about the data, separately from `clearance`, which is this project's own
      unverified reading of those terms.
    - **Runtime verification** — whether this deployment has actually run it
      live, which `EM5` insists is not the same as an entry existing in a
      registry.
    """
    meta = catalog.resolve(factor_id) or {}
    base = meta.get("base_meta") or {}
    prov = row or {}
    clearance = licensing.clearance(factor_id)

    # `log[].state` is the authority on availability, not the presence of a
    # series: a factor that was never loaded has no series entry at all, and
    # defaulting that to "generated" would tell a user "demo data" about
    # something that was simply never fetched. Those are the two causes the
    # whole product works to keep apart.
    availability = prov.get("state") or ""
    if availability == "generated":
        # Not "unknown". The runtime state of a generated factor is known
        # exactly: there is no live implementation answering for it here.
        runtime, kind = "generated", "generated"
    elif availability == "not_selected":
        runtime, kind = "not_loaded", "not_loaded"
    else:
        status = prov.get("status")
        runtime = status if status else "unknown"
        kind = (series or {}).get("source") or "unknown"

    return {
        # The log row's `source` is the *kind* (earth-engine / open-data), not
        # the publisher — reading it here labelled Sentinel-2 as
        # "earth-engine", which is the endpoint's name for itself.
        "publisher": prov.get("publisher") or base.get("source") or "",
        "endpoint": prov.get("endpoint") or "",
        "dataset": base.get("name") or "",
        "licence": clearance.get("licence") or base.get("licence") or "",
        "attribution": clearance.get("attribution") or base.get("attribution") or "",
        # This project's reading of the licence, explicitly not a legal
        # opinion — it says so in its own payload. Kept apart from `licence`
        # because "OGL v3" is a fact and "cleared" is an interpretation.
        "clearance": clearance.get("status") or "unknown",
        "runtime": runtime,
        "kind": kind,
    }


def _claims(state: str, reason: Optional[str], *,
            findings: Sequence[Dict[str, Any]],
            measurement_text: str) -> Dict[str, List[str]]:
    """What this establishes, and what it does not.

    Composed per state rather than per factor, because the boundary is a
    property of *how much the engine did*, not of which dataset answered. A
    flagged flood check and a flagged vegetation check are limited in the same
    way; a `clear` result and a `no_data` result are not.
    """
    # Lists rather than one joined paragraph. Three findings concatenated into
    # a single block is a wall of prose in the one place a reader is trying to
    # read carefully, and it hides where one claim ends and the next begins.
    texts = [str(f.get("text") or "") for f in findings if f.get("text")]

    if state == "flagged":
        # A rule may declare its own negative, and it is used *instead of*
        # `purpose`: `purpose` states what the rule does ("Identifies changes
        # large enough to warrant professional investigation"), which under a
        # heading reading "what this does not establish" says the opposite of
        # what it means. Deduplicated, because two rules on one series can
        # declare the same limit and the reader should see it once.
        negatives: List[str] = []
        for f in findings:
            neg = str((f.get("rule_meta") or {}).get("not_evidence_of") or "")
            if neg and neg not in negatives:
                negatives.append(neg)
        return {
            "established": texts or [measurement_text],
            "not_established": [*negatives, CAUSAL_LIMIT, REGULATORY_LIMIT],
        }

    if state == "clear":
        return {
            "established": [
                measurement_text
                or "This check ran against real data and did not cross its "
                   "reporting threshold."
            ],
            "not_established": [CLEAR_LIMIT, REGULATORY_LIMIT],
        }

    if state == "informational":
        return {
            "established": texts or [measurement_text],
            "not_established": [INFORMATIONAL_LIMIT, CAUSAL_LIMIT],
        }

    # Everything below is `not_assessed`, and the three causes have three
    # different fixes — which is the whole reason the reason is carried.
    if reason == "no_data":
        return {
            "established": [
                "Nothing. The source was queried and returned no usable "
                "observation for this area."
            ],
            "not_established": [ABSENCE_LIMIT],
        }
    if reason == "not_selected":
        return {
            "established": [
                "Nothing. This evidence source has not been loaded into this "
                "analysis."
            ],
            "not_established": [ABSENCE_LIMIT],
        }
    if reason == "demo_data":
        return {
            "established": [
                "Nothing. The values shown for this factor are generated demo "
                "data, and demo data is never used to produce a finding."
            ],
            "not_established": [ABSENCE_LIMIT],
        }
    return {
        "established": ["Nothing was established for this factor."],
        "not_established": [ABSENCE_LIMIT],
    }


def _measurement_text(state: str, series: Dict[str, Any],
                      flag: Optional[Dict[str, Any]],
                      info: Optional[Dict[str, Any]]) -> str:
    if flag:
        return str(flag.get("text") or "")
    if info:
        return str(info.get("text") or "")
    meta = series.get("meta") or {} if series else {}
    name = meta.get("name") or ""
    return f"{name} was assessed." if name else ""


def report(radar_payload: Dict[str, Any],
           series: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One entry per factor any rule wanted, in the log's order.

    **Contextual, not a catalogue.** The denominator is what this site's
    analysis actually touched, not the 273 factors in `catalog.py`. The
    question the explorer answers is "why is Contour saying this", and a
    database dump answers a different one.
    """
    log: Sequence[Dict[str, Any]] = radar_payload.get("log") or []
    flags: Sequence[Dict[str, Any]] = radar_payload.get("flags") or []
    info: Sequence[Dict[str, Any]] = radar_payload.get("informational") or []
    unassessed: Sequence[Dict[str, Any]] = radar_payload.get("not_assessed") or []
    investigations: Sequence[Dict[str, Any]] = radar_payload.get("investigations") or []

    # Every finding on a factor, not the first one. One NDVI series can carry a
    # trend flag *and* a historical-baseline flag, and showing only the
    # strongest hides half the answer to "why is Contour saying this" — which
    # is the only question this screen exists to answer.
    flags_by_factor: Dict[str, List[Dict[str, Any]]] = {}
    for f in flags:
        for fid in f.get("factors", []):
            flags_by_factor.setdefault(fid, []).append(f)
    info_by_factor: Dict[str, List[Dict[str, Any]]] = {}
    for i in info:
        for fid in i.get("factors", []):
            info_by_factor.setdefault(fid, []).append(i)
    # Every reason any rule gave for not assessing this factor. A *set*,
    # because a rule needing two factors reports one reason for both, and
    # taking the first would describe factor B by what was wrong with factor A.
    reasons_by_factor: Dict[str, set] = {}
    for u in unassessed:
        for fid in u.get("factors", []):
            reasons_by_factor.setdefault(fid, set()).add(u.get("reason") or "")

    out: List[Dict[str, Any]] = []
    for row in log:
        fid = row["factor"]
        one = series.get(fid) or {}
        factor_flags = flags_by_factor.get(fid) or []
        factor_info = info_by_factor.get(fid) or []
        flag = factor_flags[0] if factor_flags else None
        inf = factor_info[0] if factor_info else None

        # The state is *read*, never recomputed: a factor is flagged because a
        # flag names it, informational because an informational finding names
        # it. The cause of a `not_assessed` comes from `log[].state`, which is
        # per factor, rather than from a rule's reason, which is per rule.
        #
        # `no_data` is the exception and has to come from the rule: the log can
        # say a source answered, but only the rule knows that what came back
        # held no usable observation. Without this branch a real source that
        # returned nothing but gaps would fall through to `clear` — the exact
        # EM6 failure ("we checked and found nothing" for a question never
        # actually answered) that this project already fixed once.
        reasons = reasons_by_factor.get(fid) or set()
        if flag:
            state, reason = "flagged", None
        elif inf:
            state, reason = "informational", None
        elif "no_data" in reasons:
            state, reason = "not_assessed", "no_data"
        elif row.get("state") == "assessed":
            state, reason = "clear", None
        elif row.get("state") == "generated":
            state, reason = "not_assessed", "demo_data"
        else:
            state, reason = "not_assessed", "not_selected"

        flag_ids = {f["id"] for f in factor_flags}
        # Rule *names*, not rule ids. "Raised by: historical_vegetation_decline"
        # exposes an internal identifier in the one place the reader is trying
        # to follow the reasoning; the rule declares a human name and it should
        # be used. Falls back to the id so a rule without one is still traceable
        # rather than blank.
        name_by_flag = {
            f["id"]: str((f.get("rule_meta") or {}).get("rule") or "")
                     or f.get("topic_name") or f["id"]
            for f in factor_flags
        }
        raised = [
            {"id": inv["id"], "name": inv["name"], "priority": inv["priority"],
             # Which of this factor's flags raised it — "raised by" is the
             # link that makes the journey traceable in both directions.
             "why": [name_by_flag[w] for w in (inv.get("why") or [])
                     if w in flag_ids]}
            for inv in investigations
            if flag_ids & set(inv.get("why") or [])
        ]

        # One entry per finding on this factor, each with the rule that reached
        # it. `findings` is the evidence; `state` is the engine's summary of it.
        findings = [
            {
                "id": f["id"], "kind": "flag", "text": f.get("text") or "",
                "severity": f.get("severity"),
                "threshold": f.get("threshold") or "",
                "evidence": f.get("evidence") or {},
                "rule_meta": f.get("rule_meta") or {},
            }
            for f in factor_flags
        ] + [
            {
                "id": i["id"], "kind": "info", "text": i.get("text") or "",
                "severity": None, "threshold": "",
                "evidence": i.get("evidence") or {}, "rule_meta": {},
            }
            for i in factor_info
        ]

        out.append({
            "factor": fid,
            "name": row.get("name") or fid,
            "state": state,
            "reason": reason,
            "severity": (flag or {}).get("severity"),
            "findings": findings,
            "source": _source_block(fid, one, row),
            "investigations": raised,
            "assessed_at": row.get("at") or "",
            "claims": _claims(state, reason, findings=findings,
                              measurement_text=_measurement_text(
                                  state, one, flag, inf)),
        })
    return out
