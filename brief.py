"""
The Site Investigation Brief.

The artefact that leaves the product. Everything else Contour builds is read by
someone already inside the tool; this is read by the person who was sent it —
often the professional being asked to quote for the survey.

A differentiation audit found the gap this closes: Contour had built a
sophisticated evidence system, and the thing that actually left the building
was a spreadsheet of series values. The Brief is not a prettier report. It is a
different artefact answering a different question:

    Here is the evidence we established about this site, and the professional
    questions that remain.

## What it is not

Not a site appraisal. It contains no opinion about whether the site is
suitable, developable, valuable or safe, and `EM7`/`EM8` are enforced through
it exactly as everywhere else — it is assembled from payloads that already
satisfy them rather than computing anything new.

## A read, not a second engine

Every section is a projection of `radar`, `evidence` and `historical`. Nothing
here evaluates a rule, crosses a threshold, decides a state or composes a
claim: the third of those would be a second opinion, and the fourth would let
the Brief's wording drift away from the explorer's for the same finding. Same
contract as `evidence.py` and `historical/view.py`.

The one thing this module does own is **order** — which sections appear and in
what sequence. That is a real editorial decision and it is stated in
`SECTIONS`: coverage before findings, always, because a reader who meets "7
flagged" before learning that 18 factors could not be assessed has already
formed a view of the site.
"""

from __future__ import annotations

from typing import Any, Dict, List

#: Section order, and the reason it is this order rather than another.
#:
#: Coverage first is the load-bearing choice. Findings are what a reader wants
#: and gaps are what protects them, so gaps that arrive after the findings
#: arrive after the conclusion has been drawn.
SECTIONS = (
    "site",
    "coverage",
    "findings",
    "historical",
    "gaps",
    "log",
    "methodology",
)

#: Shown at the foot, and the sentence the whole product rests on. Repeated
#: here rather than referenced because the Brief travels away from the app and
#: has to carry its own terms.
PRINCIPLE_HEADING = "The Contour principle"


def _site(payload: Dict[str, Any], name: str) -> Dict[str, Any]:
    centroid = payload.get("centroid") or {}
    return {
        "name": name or "Untitled site",
        "area_ha": payload.get("area_ha"),
        # Coordinates, never an administrative area. A drawn shape carries no
        # county, and deriving one from a point without a boundary dataset
        # would put a guess in the line a reader trusts most.
        "centroid": centroid,
        "assessed_at": (payload.get("radar") or {}).get("assessed_at", ""),
    }


def _coverage(radar_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Assessed against relevant, with the causes of every gap.

    `assessed + not_assessed = relevant` is the arithmetic that holds. The four
    finding states are *not* a partition — `flagged` and `informational` are
    independent factor sets and one factor can be in both — so the Brief
    reports the partition and lets the states sit inside it, rather than
    printing four numbers that a careful reader will try to add.
    """
    cov = radar_payload.get("coverage") or {}
    return {
        "assessed": cov.get("assessed", 0),
        "relevant": cov.get("relevant", 0),
        "not_assessed": cov.get("not_assessed", 0),
        "flagged": cov.get("flagged", 0),
        "clear": cov.get("clear", 0),
        "informational": cov.get("informational", 0),
        "not_loaded": cov.get("not_selected", 0),
        "no_live_source": cov.get("generated", 0),
        # Travels with the numbers rather than living in a design document.
        "note": cov.get("note", ""),
    }


def _findings(evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Flagged entries, each with its claim boundary and what it prompted.

    The claim pair comes straight from `evidence.py`. Recomposing it here would
    produce two wordings of the same limitation — the Brief's and the
    explorer's — and the first time they disagreed, the disagreement would be
    invisible.
    """
    out = []
    for entry in evidence:
        if entry.get("state") != "flagged":
            continue
        out.append({
            "factor": entry["factor"],
            "name": entry["name"],
            "severity": entry.get("severity"),
            "findings": [
                {"text": f.get("text", ""), "threshold": f.get("threshold", ""),
                 "rule": (f.get("rule_meta") or {}).get("rule", ""),
                 "method": (f.get("rule_meta") or {}).get("method_version", "")}
                for f in entry.get("findings", []) if f.get("kind") == "flag"
            ],
            "established": entry["claims"]["established"],
            "not_established": entry["claims"]["not_established"],
            "investigations": [i["name"] for i in entry.get("investigations", [])],
            "source": entry.get("source") or {},
        })
    return out


def _informational(evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Measured, and deliberately not judged.

    A section of its own because the roadmap's answer for LST and built surface
    is that they stay informational until there is a defensible basis for a
    threshold. That decision is only honest if the Brief has somewhere to put
    an unjudged measurement — otherwise the pressure to invent a threshold
    comes straight back, this time to fill a page.
    """
    return [
        {
            "factor": e["factor"],
            "name": e["name"],
            "text": " ".join(f.get("text", "") for f in e.get("findings", [])),
            "not_established": e["claims"]["not_established"],
        }
        for e in evidence if e.get("state") == "informational"
    ]


def _gaps(evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Why each unassessed factor could not be assessed.

    Grouped by cause, because the three have three different fixes and three
    different owners: `not_loaded` is one click, `no_live_source` is a wall,
    and `no_data` means the source was asked and had nothing for this area.
    """
    causes: Dict[str, List[str]] = {}
    for e in evidence:
        if e.get("state") != "not_assessed":
            continue
        causes.setdefault(e.get("reason") or "unknown", []).append(e["name"])

    labels = {
        "not_selected": "Not loaded into this analysis",
        "demo_data": "No live source — demo data cannot support a finding",
        "no_data": "Source queried; no usable observation returned for this area",
        "unknown": "Not assessed",
    }
    return [
        {"reason": reason, "label": labels.get(reason, labels["unknown"]),
         "count": len(names), "factors": sorted(names)}
        for reason, names in sorted(causes.items())
    ]


def _historical(historical: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for entry in historical:
        metric = entry.get("metric") or {}
        finding = entry.get("finding") or {}
        out.append({
            "name": entry.get("name", ""),
            "state": finding.get("state", "not_assessed"),
            "change_pct": metric.get("change_pct"),
            "baseline": metric.get("baseline"),
            "recent": metric.get("recent"),
            "baseline_years": metric.get("baseline_years") or [],
            "recent_years": metric.get("recent_years") or [],
            "years_usable": metric.get("years_usable"),
            "years_total": metric.get("years_total"),
            "method": metric.get("method_version", ""),
        })
    return out


def _log(radar_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One row per factor any rule wanted. The audit trail.

    Present in full rather than filtered to the interesting rows: a reader
    three months later needs to see what was asked for and did not arrive, not
    only what did.
    """
    return [
        {
            "factor": r.get("factor", ""),
            "name": r.get("name", ""),
            "source": r.get("publisher") or "—",
            "endpoint": r.get("endpoint") or "—",
            "status": r.get("state", ""),
            "verified": r.get("status") == "verified",
            "at": r.get("at", ""),
        }
        for r in (radar_payload.get("log") or [])
    ]


def _methodology(payload: Dict[str, Any], evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Attribution for every source that answered, plus the historical method.

    Attribution is a licence *condition*, not a courtesy, so it travels with
    the artefact that leaves the building rather than living on a screen the
    recipient never sees.
    """
    seen: Dict[str, str] = {}
    for e in evidence:
        src = e.get("source") or {}
        text = src.get("attribution")
        if text and src.get("runtime") in ("verified", "written"):
            seen[text] = src.get("publisher", "")
    return {
        "historical": payload.get("methodology") or {},
        "attributions": sorted(seen),
        "limits": (payload.get("radar") or {}).get("limits", ""),
    }


def build(payload: Dict[str, Any], *, site_name: str = "") -> Dict[str, Any]:
    """The Brief, assembled from an already-assessed payload.

    Takes the whole `/api/series` response rather than its parts, because every
    section is a projection of it and passing four arguments would invite a
    caller to assemble them from different requests — a Brief whose coverage
    and findings came from separate assessments would be internally consistent
    and wrong.
    """
    radar_payload = payload.get("radar") or {}
    evidence = payload.get("evidence") or []

    return {
        "sections": list(SECTIONS),
        "site": _site(payload, site_name),
        "coverage": _coverage(radar_payload),
        "findings": _findings(evidence),
        "informational": _informational(evidence),
        "historical": _historical(payload.get("historical") or []),
        "gaps": _gaps(evidence),
        "log": _log(radar_payload),
        "methodology": _methodology(payload, evidence),
        "principle": radar_payload.get("principle", ""),
    }
