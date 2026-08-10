"""
Evidence comparison — how do these sites' evidence profiles differ.

Not *which site is best*. `COMPARISON_CONTRACT.md` is the specification and was
written before this module; `EVIDENCE_MODEL.md` EM10 and
`tests/test_comparison_contract.py` enforce it.

## The trap this module is shaped around

**Fewer flags can mean less looked at.**

    Site A   4 flagged   18 observed    6 not assessed
    Site C   0 flagged   11 observed   13 not assessed

Site C reads as the better site. Site C is the *less examined* site. A
comparison that reports flag counts without coverage misleads in favour of
whichever parcel nobody investigated, which is the worst possible direction for
a tool people use to decide where to spend money.

So every count in this payload travels with its coverage, and `coverage_warning`
fires unprompted when the sites were not examined to a comparable depth.

## Three layers, and a hard stop after the third

1. `sites` — counts, no interpretation.
2. `topics` — each site's value and assessment state, side by side. A topic
   where the sites have different coverage is `not_comparable`, and says so.
3. `differences` — deterministic statements about values **every** site
   observed. Quantity, never judgement.

There is no fourth layer. No composite, no ordering by quality, no winner.
Sites come back in the order they were supplied.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import radar

#: Two ways sites can be unevenly examined, and both have to be caught.
#:
#: `COVERAGE_GAP` is the difference in *share* of relevant factors observed.
#: On its own it misses the common case: with 24 relevant factors, a site that
#: observed four and a site that observed one differ by only 12 points of
#: share, while one holds four times the evidence of the other. So the ratio is
#: checked too — the smaller must be at least `COVERAGE_RATIO` of the larger,
#: once they differ by more than `COVERAGE_MIN_DIFF` in absolute terms, which
#: keeps 3-vs-2 from warning.
#:
#: Deliberately generous in both directions: the warning costs a sentence, and
#: its absence costs the reader a wrong decision.
COVERAGE_GAP = 0.15
COVERAGE_RATIO = 0.75
COVERAGE_MIN_DIFF = 2

LIMITS = (
    "This compares what was established about each site, not the sites "
    "themselves. Counts are only comparable where coverage is comparable — a "
    "site with fewer flags may simply have been examined less, which is why "
    "every count here carries its coverage. Contour does not rank sites or say "
    "which one to choose; that judgement belongs to the person whose name goes "
    "on the report."
)


def _site_summary(site: Dict[str, Any]) -> Dict[str, Any]:
    """Layer 1 for one site. Counts, and the coverage that makes them readable."""
    payload = site.get("radar") or {}
    counts = payload.get("counts") or {}
    coverage = payload.get("coverage") or {}
    return {
        "id": site.get("id"),
        "name": site.get("name") or site.get("id"),
        "flags": counts.get("flags", 0),
        "high": counts.get("high", 0),
        "informational": counts.get("informational", 0),
        # `observed` rather than `assessed`: the claim is that a real source
        # returned a usable value, not that someone looked at the factor.
        "observed": coverage.get("assessed", 0),
        "relevant": coverage.get("relevant", 0),
        "not_assessed": coverage.get("not_assessed", 0),
        "share": coverage.get("share", 0.0),
        # Never separable from the counts above. See EM10.
        "coverage_note": radar.COVERAGE_NOTE,
    }


def _observed_level(payload: Dict[str, Any], factor: str) -> Optional[float]:
    """The value this site observed for a factor, or None if it did not.

    None means *not observed* and never zero. A comparison that reads a missing
    value as 0 produces "Site B has 0% flood risk" for a site whose flood layer
    was never loaded, which is the false-zero failure the whole evidence model
    is built to refuse.
    """
    row = next((r for r in payload.get("log") or []
                if r.get("factor") == factor), None)
    if not row or row.get("state") != "assessed":
        return None
    series = (payload.get("_series") or {}).get(factor)
    if series is None:
        return None
    values = radar._real_values(series)
    return values[-1][1] if values else None


def _unit_of(factor: str) -> str:
    """The factor's unit, spaced the way this project writes units."""
    try:
        import catalog
        unit = (catalog.FACTOR_BY_ID.get(factor) or {}).get("unit", "")
    except Exception:                                       # noqa: BLE001
        return ""
    if not unit or unit in ("class", "index"):
        return ""
    return unit if unit == "%" else f" {unit}"


def _topic_rows(sites: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Layer 2. Each topic, each site's state, and whether they can be compared.

    A topic is only `comparable` where every site assessed every one of its
    indicators. Anything less is a *coverage* difference, and calling it a value
    difference — "A has more flood risk than B" when B was never checked — is
    the specific error this layer exists to make impossible.
    """
    rows = []
    for tid, name in radar.TOPICS.items():
        cells = []
        for site in sites:
            payload = site.get("radar") or {}
            topic = next((t for t in payload.get("topics") or []
                          if t.get("id") == tid), None)
            coverage = (topic or {}).get("coverage") or {"assessed": 0, "total": 0}
            cells.append({
                "id": site.get("id"),
                "state": (topic or {}).get("state", "not_assessed"),
                "coverage": coverage,
                "flags": (topic or {}).get("flags", 0),
                "detail": (topic or {}).get("detail", ""),
            })

        totals = {(c["coverage"]["assessed"], c["coverage"]["total"]) for c in cells}
        complete = all(c["coverage"]["total"] and
                       c["coverage"]["assessed"] == c["coverage"]["total"]
                       for c in cells)
        comparable = complete and len(totals) == 1
        rows.append({
            "id": tid,
            "name": name,
            "sites": cells,
            "comparable": comparable,
            "note": ("" if comparable else
                     "These sites were not assessed to the same depth for this "
                     "topic, so their results describe different amounts of "
                     "evidence rather than different ground."),
        })
    return rows


def _differences(sites: Sequence[Dict[str, Any]],
                 summaries: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Layer 3. Deterministic statements, quantity only.

    Every statement here is arithmetic over values that **every** site observed,
    or a count that travels with its coverage. Nothing is weighted, nothing is
    combined across factors, and nothing is ordered by quality.
    """
    out: List[Dict[str, Any]] = []
    names = {s["id"]: s["name"] for s in summaries}

    # --- Values every site observed -----------------------------------------
    wanted = sorted({f for rule in radar.RULES for f in rule.needs})
    for factor in wanted:
        levels = {}
        for site in sites:
            level = _observed_level(site.get("radar") or {}, factor)
            if level is None:
                break
            levels[site.get("id")] = level
        if len(levels) != len(sites) or len(set(levels.values())) < 2:
            continue
        label = radar._catalog_name(factor)
        # With the unit. "Site A 31" beside "Site A 31%" is the difference
        # between a number and a measurement.
        unit = _unit_of(factor)
        parts = ", ".join(f"{names.get(sid, sid)} {v:g}{unit}"
                          for sid, v in levels.items())
        out.append({
            "kind": "value",
            "factor": factor,
            "text": f"{label}: {parts}.",
            "sites": list(levels),
        })

    # --- Counts, each carrying its coverage ----------------------------------
    observed = {s["id"]: s["observed"] for s in summaries}
    if len(set(observed.values())) > 1:
        parts = ", ".join(f"{names[sid]} observed {n}"
                          for sid, n in observed.items())
        out.append({
            "kind": "coverage",
            "text": f"Indicators observed: {parts}.",
            "sites": list(observed),
        })

    no_high = [s for s in summaries if s["high"] == 0]
    if no_high and len(no_high) < len(summaries):
        for s in no_high:
            # Stated with its coverage, always. Without it this sentence reads
            # as praise for whichever site nobody examined.
            out.append({
                "kind": "flags",
                "text": (f"{s['name']} has no high-severity flags, from "
                         f"{s['observed']} of {s['relevant']} indicators "
                         f"observed."),
                "sites": [s["id"]],
            })
    return out


def compare(sites: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Compare 2–4 sites' evidence profiles.

    `sites` is a sequence of `{"id", "name", "radar": <radar payload>}`. Pass
    `_series` alongside `radar` to enable value comparison; without it the
    comparison still works and simply has no Layer 3 value rows, which is the
    correct degradation — silence rather than a guess.

    Returns sites **in the order supplied**. Any ordering by count would be a
    ranking, and a ranking is what this module exists not to produce.
    """
    summaries = [_site_summary(s) for s in sites]

    shares = [s["share"] for s in summaries]
    counts = [s["observed"] for s in summaries]
    gap = (max(shares) - min(shares)) if shares else 0.0
    lo, hi = (min(counts), max(counts)) if counts else (0, 0)
    thin = (hi > 0 and lo < COVERAGE_RATIO * hi
            and (hi - lo) >= COVERAGE_MIN_DIFF)
    warning = ""
    if gap > COVERAGE_GAP or thin:
        least = min(summaries, key=lambda s: s["observed"])
        most = max(summaries, key=lambda s: s["observed"])
        warning = (
            f"These sites were not examined to the same depth: "
            f"{most['name']} observed {most['observed']} of "
            f"{most['relevant']} indicators and {least['name']} observed "
            f"{least['observed']}. Fewer flags on {least['name']} may mean "
            f"less was looked at rather than less was found. Compare the "
            f"coverage before comparing the counts."
        )

    return {
        "sites": summaries,
        "topics": _topic_rows(sites),
        "differences": _differences(sites, summaries),
        # Fires unprompted. A warning the user has to ask for is a warning that
        # arrives after the decision.
        "coverage_warning": warning,
        "principle": radar.PRINCIPLE,
        "limits": LIMITS,
    }
