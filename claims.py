"""
The canonical claim boundary.

**EM12.** Every finding states what it establishes and what it does not, and
both come from here. One module, one vocabulary, one wording per state.

The reason this is a module rather than a convention is prose duplication. The
explorer, the Brief and — next — the investigation workspace all present the
same findings, and the moment any of them composes its own limitation there are
two sentences describing one boundary. They will drift, and the drift is
invisible: each reads correctly on its own screen, and only someone holding a
brief next to the app would ever notice that the document is more confident
than the product.

## Scope, and why it is not larger

EM12 requires a **state-generic** boundary, always. A rule *may* add its own
negative via `rule_meta.not_evidence_of`, and most will not: at the time this
was written 1 of 25 rules had one, and requiring 25 would have meant inventing
24 — asking rule authors to write limitation prose for domains they have not
thought hard about, which produces confident-sounding text that nobody checked.
That is the failure this project exists to avoid, so the invariant is scoped to
what the architecture can actually satisfy honestly.

The clauses below are therefore keyed by *state*, not by factor or rule. A
flagged flood check and a flagged vegetation check are limited in the same way;
a `clear` result and a `no_data` result are not.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

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



#: Every state the boundary must answer for, including the three causes of
#: `not_assessed`. Exhaustive by construction: `test_em12_*` walks this and
#: fails if a state or reason exists that produces no limitation, so a new
#: finding state cannot ship without one.
STATES = (
    ("flagged", None),
    ("clear", None),
    ("informational", None),
    ("not_assessed", "no_data"),
    ("not_assessed", "not_selected"),
    ("not_assessed", "demo_data"),
)


def compose(state: str, reason: Optional[str], *,
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


