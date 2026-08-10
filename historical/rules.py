"""
Historical rules — the only place a historical *threshold* lives.

`historical/metrics.py` says what happened. This says whether that is large
enough for Contour to ask a professional to look at it. The distinction is the
whole architecture, and it is also the whole liability position: a metric is an
observation, a threshold is a product decision, and the two must never be
confused for one another in a document, a UI or a sales conversation.

Deliberately one rule. `HISTORICAL_EVIDENCE_MODEL.md` step 4 is vegetation
decline and nothing else, so that the complete chain — Sentinel-2 → metric →
rule → radar → investigation → assessment log → permalink — can be proven end
to end before a second metric family is added on top of an unproven path.

## This module has no dependency on `radar`

`build()` takes the rule class as an argument rather than importing it. That
keeps the direction of knowledge one-way — the engine knows about rules, rules
do not know about the engine — and avoids a circular import that would
otherwise have to be worked around with a lazy import inside a function.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Sequence, Tuple

from historical import metrics

# ---------------------------------------------------------------------------
# The threshold
# ---------------------------------------------------------------------------
#: **Contour reporting threshold — a 20% decline in the historical NDVI
#: metric.**
#:
#: Product-defined screening threshold. **Not a regulatory standard and not a
#: scientific one.** No published definition of ecological degradation was
#: consulted to choose it, and none should be inferred from it.
#:
#: What it means, exactly: a decline of this size is large enough that Contour
#: asks a professional to look at the site. It does not mean the vegetation has
#: degraded, that the habitat has been lost, or that anything is wrong. Those
#: are causal conclusions about a real place, and nothing in this codebase is
#: entitled to reach one — see `HISTORICAL_EVIDENCE_MODEL.md` HE9.
#:
#: Why it is written down here rather than inline: six months from now someone
#: will ask where 20 came from, and the honest answer — "we chose it as a
#: screening threshold" — must be attached to the number rather than lost. A
#: bare `20` in a conditional invites the assumption that it is authoritative,
#: and the person who assumes that is the person who changes it.
#:
#: Sign convention: `change_pct` is negative for a decline and positive for an
#: increase, so the test reads `change_pct <= -20` and never `abs(...) >= 20`.
#: An increase and a decline do not warrant the same investigation, and an
#: absolute comparison would silently treat them as if they did.
VEGETATION_CHANGE_INVESTIGATION_THRESHOLD = -20.0

#: Metadata carried onto every flag this rule raises, for the evidence drawer.
#: It makes the difference between *the measurement* and *Contour's decision to
#: surface the measurement* visible on screen rather than implied.
VEGETATION_RULE_META: Dict[str, Any] = {
    "rule": "Historical vegetation decline",
    "threshold": VEGETATION_CHANGE_INVESTIGATION_THRESHOLD,
    "threshold_display": "≥ 20% decline",
    "threshold_type": "Contour reporting threshold",
    "threshold_status": "product-defined; not a regulatory or scientific standard",
    "purpose": ("Identifies changes large enough to warrant professional "
                "investigation. Not evidence of ecological degradation."),
    "method_version": metrics.METHOD_VERSION,
    "measure": "percentage change from the historical baseline",
    "direction": "decline",
}


def _vegetation_decline(series_by_factor: Dict[str, Dict[str, Any]],
                        insufficient: Callable[[str], Any]) -> Any:
    """Flag a vegetation decline at or beyond the reporting threshold.

    Almost no intelligence, on purpose. It reads the metric, trusts
    `meets_minimum_evidence` rather than reconstructing evidence sufficiency
    for itself, and compares one number against one constant.

    Trusting that flag is not a shortcut — it is the point. If this rule
    recomputed sufficiency, there would be two definitions of "enough
    evidence" and they would drift, which is the same failure EM11 prevents
    between the frontend and the backend.
    """
    metric = metrics.change_metric(
        series_by_factor["ndvi"], name="Vegetation vigour",
        family="vegetation", factor="ndvi")

    if not metric["meets_minimum_evidence"]:
        # Not a clear result. `radar.assess` routes this to `not_assessed`
        # with reason `no_data` — a live series with too few usable years must
        # never read as "checked, nothing found".
        return insufficient(
            metric["shortfall"]
            or "There were not enough usable observations to measure change.")

    change = metric["change_pct"]
    if change is None or change > VEGETATION_CHANGE_INVESTIGATION_THRESHOLD:
        return None                          # checked, below the threshold

    baseline_span = _span(metric["baseline_years"])
    recent_span = _span(metric["recent_years"])
    return {
        "severity": "medium" if change > -35 else "high",
        # Observation, then what it prompts. Never "vegetation has degraded" —
        # that asserts a cause nobody measured. See HE9.
        "text": (f"Vegetation vigour has declined {abs(change):.0f}% relative "
                 f"to the historical baseline ({metric['baseline']:.2f} in "
                 f"{baseline_span} to {metric['recent']:.2f} in "
                 f"{recent_span}). A decline of this size is worth "
                 f"establishing the cause of."),
        "evidence": {
            "change_pct": change,
            "threshold": "20% decline (Contour reporting threshold)",
            "baseline": metric["baseline"],
            "baseline_period": baseline_span,
            "recent": metric["recent"],
            "recent_period": recent_span,
            "years_observed": f"{metric['years_usable']} of "
                              f"{metric['years_total']}",
            "year_coverage": metric["year_coverage"],
            "method_version": metric["method_version"],
        },
    }


def _span(years: Sequence[int]) -> str:
    if not years:
        return "—"
    return f"{years[0]}" if len(years) == 1 else f"{years[0]}–{years[-1]}"


def build(rule_class: Callable[..., Any],
          insufficient: Callable[[str], Any]) -> Tuple[Any, ...]:
    """The historical rules, as engine rules.

    Takes the rule class and the insufficient-evidence marker as arguments
    rather than importing them, so this module never depends on the finding
    engine. See the module docstring.
    """
    return (
        rule_class(
            "historical_vegetation_decline", "vegetation", ["ndvi"],
            lambda s: _vegetation_decline(s, insufficient),
            ["ecology_survey"],
            "whether vegetation vigour has declined against its historical "
            "baseline",
            meta=VEGETATION_RULE_META,
        ),
    )
