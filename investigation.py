"""
The investigation workspace.

One question, in the order a professional asks it:

    Why am I seeing this?      → the findings that raised it
    What does it establish?    → the canonical claim
    What does it not?          → the canonical limitation
    What prompted it?          → the rule, its threshold, its method
    What should be checked?    → the named investigation
    What do I take along?      → sources, dates, methods, measurements

## This module is a proof of the Contour abstraction

**It must be able to assemble an investigation without knowing whether the
subject is land, habitat, infrastructure, mining or coastline.** Every
domain-specific word enters through injected metadata — `radar.INVESTIGATIONS`,
a rule's `rule_meta`, a factor's catalogue entry — and none is written here.

That is not decoration. `radar.py` already never imports `catalog`, and the
engine's generality turned out to be a side effect of testing discipline rather
than of design (see `docs/VERTICAL_DISCOVERY.md`). This module is where that
generality would be easiest to lose: an investigation workspace is exactly the
place someone writes "the site" or "before development", and the moment it
happens the engine stops being reusable for reasons nobody records.

`tests/test_investigation_workspace.py` therefore does two things: it scans this
file for domain vocabulary, and it assembles a **coastal** investigation from
fabricated metadata to prove the assembly path carries no land assumptions. If
the second test ever needs a change here to pass, the abstraction has been
broken and the change is the evidence.

## Naming

The thing being investigated is a **subject**, never a "site". A subject has a
geometry and evidence; whether that geometry is a parcel, a reserve, a licence
block or a stretch of shoreline is not this module's business.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence


def _readable(identifier: str) -> str:
    """`shoreline_retreat` → `Shoreline retreat`.

    Pure formatting, and deliberately not a lookup table: a table would need an
    entry per domain, which is the coupling this module exists to avoid.
    """
    words = identifier.replace("_", " ").strip()
    return words[:1].upper() + words[1:] if words else identifier


def _evidence_for(factors: Sequence[str],
                  entries: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """What to take to the professional, per factor.

    Deliberately the same fields for every domain: what answered, through which
    endpoint, how far it has been proven, when it was read, and under what
    method. A geologist and an ecologist need the same six things about a
    number before they will rely on it.
    """
    by_factor = {e["factor"]: e for e in entries}
    out: List[Dict[str, Any]] = []
    for fid in factors:
        entry = by_factor.get(fid)
        if not entry:
            continue
        src = entry.get("source") or {}
        methods = sorted({
            str((f.get("rule_meta") or {}).get("method_version") or "")
            for f in entry.get("findings", [])
        } - {""})
        out.append({
            "factor": fid,
            "name": entry.get("name", fid),
            "state": entry.get("state"),
            "publisher": src.get("publisher", ""),
            "endpoint": src.get("endpoint", ""),
            "dataset": src.get("dataset", ""),
            "licence": src.get("licence", ""),
            "attribution": src.get("attribution", ""),
            "runtime": src.get("runtime", ""),
            "assessed_at": entry.get("assessed_at", ""),
            "methods": methods,
            # The measurements themselves, as the rule recorded them.
            "measurements": [
                {"rule": f.get("id", ""),
                 "rule_name": str((f.get("rule_meta") or {}).get("rule") or ""),
                 "threshold": f.get("threshold", ""),
                 "evidence": f.get("evidence") or {}}
                for f in entry.get("findings", [])
            ],
        })
    return out


def report(radar_payload: Dict[str, Any],
           evidence_entries: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One workspace entry per investigation the evidence raised.

    A join, not a second engine. The investigation, its priority and the flags
    behind it were all decided by `radar`; the claim boundary was composed by
    `claims`. Nothing here evaluates, ranks or re-words any of it — which is
    what lets the same function serve a domain this code has never seen.
    """
    investigations = radar_payload.get("investigations") or []
    flags_by_id = {f["id"]: f for f in (radar_payload.get("flags") or [])}
    entries_by_factor = {e["factor"]: e for e in evidence_entries}

    out: List[Dict[str, Any]] = []
    for inv in investigations:
        raised_by = []
        factors: List[str] = []
        for flag_id in inv.get("why") or []:
            flag = flags_by_id.get(flag_id)
            if not flag:
                continue
            meta = flag.get("rule_meta") or {}
            raised_by.append({
                "id": flag_id,
                # The rule's own name where it declares one, otherwise its id
                # made readable. An engine identifier shown to a professional
                # reads as a leak — and most rules declare no name, so a
                # generic fallback is the fix rather than 24 hand-written
                # labels. Formatting only: no word here names a domain.
                "rule": str(meta.get("rule") or "") or _readable(flag_id),
                "text": flag.get("text", ""),
                "severity": flag.get("severity"),
                "threshold": flag.get("threshold", ""),
                "threshold_type": str(meta.get("threshold_type") or ""),
                "threshold_status": str(meta.get("threshold_status") or ""),
                "method": str(meta.get("method_version") or ""),
                "factors": flag.get("factors") or [],
            })
            factors.extend(flag.get("factors") or [])

        # Deduplicated, order preserved: a factor read by two rules appears
        # once in the evidence pack a professional is handed.
        seen: List[str] = []
        for fid in factors:
            if fid not in seen:
                seen.append(fid)

        # The claim boundary, taken from the entries the engine already
        # composed. Union rather than recomposition — EM12 requires one
        # canonical wording, and an investigation is a *view* over findings
        # that already have one.
        established: List[str] = []
        not_established: List[str] = []
        for fid in seen:
            entry = entries_by_factor.get(fid)
            if not entry:
                continue
            for c in entry["claims"]["established"]:
                if c not in established:
                    established.append(c)
            for c in entry["claims"]["not_established"]:
                if c not in not_established:
                    not_established.append(c)

        out.append({
            "id": inv["id"],
            "name": inv["name"],
            "blurb": inv.get("blurb", ""),
            "next_step": inv.get("next_step", ""),
            "priority": inv.get("priority", ""),
            "raised_by": raised_by,
            "established": established,
            "not_established": not_established,
            "evidence": _evidence_for(seen, evidence_entries),
        })
    return out


def find(workspace: Sequence[Dict[str, Any]], investigation_id: str):
    """One entry by id, or `None`. A workspace opens on the investigation the
    reader clicked, not on a list of all of them."""
    for entry in workspace:
        if entry["id"] == investigation_id:
            return entry
    return None
