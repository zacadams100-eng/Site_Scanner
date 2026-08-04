#!/usr/bin/env python3
"""
Audit every factor the catalogue calls real.

"Real" is the strongest claim this application makes, and it is made in a
tooltip next to 269 factors. This checks that each of those claims is backed by
something a user could reproduce: a callable that fetches it, a named
publisher, a named endpoint, a licence, and an honest statement of whether
anyone has ever run it against the live service.

    python3 scripts/audit_catalogue.py          # human-readable
    python3 scripts/audit_catalogue.py --json

Exit status is 1 if any factor fails a check. `tests/test_catalogue.py` runs
the same checks, so a mislabel fails CI rather than waiting to be noticed.

## The checks, and why each one exists

1.  **Registered factors exist in the catalogue.** A registry entry for an id
    nobody can select is dead code that reads as coverage.
2.  **Every real factor names a publisher and an endpoint.** These differ more
    often than you would expect — SSSI boundaries are Natural England's data
    served by MHCLG — and a user shown only the publisher cannot find the
    number.
3.  **Every real factor declares its verification status,** `verified` or
    `written`. This is the check that stops "we implemented it" drifting into
    "we ran it" as the code ages and nobody remembers which.
4.  **A publisher/endpoint mismatch is explained.** If the two differ, the
    provenance note has to say so. Silently answering a Natural England factor
    from a different host is the kind of thing that is fine until someone
    tries to reconcile two numbers.
5.  **Every real factor's base carries a licence and attribution.** Showing a
    number whose licence we cannot name is the one failure here with legal
    consequences.
6.  **Unresolved commercial terms are surfaced, not hidden.** A base marked
    `commercial: "verify"` with real factors hanging off it is reported —
    see docs/licensing/DECISION-LOG.md.
"""

import argparse
import json
import pathlib
import sys
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import catalog                                       # noqa: E402


def build_registry():
    """Register every real source the way a backend does at startup.

    Earth Engine is optional here: `ee_series` imports cleanly without
    credentials, but if it ever stops doing so the audit should still be able
    to check the open-data half rather than failing entirely.
    """
    registry, provenance = {}, {}
    try:
        import ee_series
        ee_series.install(registry, provenance)
    except Exception as exc:                          # noqa: BLE001
        print(f"note: Earth Engine factors not audited ({exc})", file=sys.stderr)
    import open_data
    open_data.install(registry, provenance)
    return registry, provenance


def audit(registry, provenance):
    """Returns (findings, summary). A finding is (severity, factor_id, text)
    where severity is 'fail' or 'warn'."""
    findings = []
    known = catalog.FACTOR_BY_ID

    for factor_id in sorted(registry):
        spec = known.get(factor_id)
        if spec is None:
            findings.append(("fail", factor_id,
                             "registered as real but not in the catalogue"))
            continue

        prov = provenance.get(factor_id)
        if not prov:
            findings.append(("fail", factor_id, "real with no provenance recorded"))
            continue

        if not prov.get("source"):
            findings.append(("fail", factor_id, "provenance names no publisher"))
        if not prov.get("endpoint"):
            findings.append(("fail", factor_id, "provenance names no endpoint"))

        status = prov.get("status")
        if status not in ("verified", "written"):
            findings.append(("fail", factor_id,
                             f"status {status!r} is neither 'verified' nor 'written'"))

        base = catalog.BASE_BY_ID.get(spec["base"], {})
        endpoint = (prov.get("endpoint") or "").lower()
        base_host = (urlparse(base.get("url", "")).hostname or "").lower()
        base_host = base_host[4:] if base_host.startswith("www.") else base_host
        if endpoint and base_host and endpoint not in base_host \
                and base_host not in endpoint:
            if "served through" not in (prov.get("note") or "").lower():
                findings.append((
                    "fail", factor_id,
                    f"answered by {endpoint} but the catalogue shows "
                    f"{base_host}, and the note does not say so"))

        if not base.get("licence"):
            findings.append(("fail", factor_id,
                             f"base {spec['base']!r} declares no licence"))
        if not base.get("attribution"):
            findings.append(("fail", factor_id,
                             f"base {spec['base']!r} declares no attribution"))
        if base.get("commercial") == "verify":
            findings.append((
                "warn", factor_id,
                f"licence for {spec['base']!r} is unconfirmed for commercial "
                f"use — docs/licensing/DECISION-LOG.md"))

    total = len(catalog.FACTORS)
    real = [f for f in registry if f in known]
    verified = [f for f in real
                if provenance.get(f, {}).get("status") == "verified"]
    summary = {
        "factors": total,
        "real": len(real),
        "verified": len(verified),
        "written": len(real) - len(verified),
        "generated": total - len(real),
        "real_share": round(len(real) / total, 4) if total else 0.0,
    }
    return findings, summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    registry, provenance = build_registry()
    findings, summary = audit(registry, provenance)
    fails = [f for f in findings if f[0] == "fail"]

    if args.json:
        print(json.dumps({
            "summary": summary,
            "findings": [{"severity": s, "factor": f, "detail": d}
                         for s, f, d in findings],
            "provenance": provenance,
        }, indent=2, sort_keys=True))
        return 1 if fails else 0

    print(f"{summary['factors']} factors: {summary['real']} real "
          f"({summary['real_share'] * 100:.1f}%), "
          f"{summary['generated']} generated")
    print(f"  of the real: {summary['verified']} verified against a live "
          f"service, {summary['written']} written but never run\n")

    by_source = {}
    for factor_id in sorted(registry):
        p = provenance.get(factor_id, {})
        by_source.setdefault((p.get("source", "?"), p.get("endpoint", "?"),
                              p.get("status", "?")), []).append(factor_id)
    for (source, endpoint, status), ids in sorted(by_source.items()):
        via = "" if endpoint in source.lower() else f" via {endpoint}"
        print(f"  {len(ids):3d}  {source}{via}  [{status}]")

    if findings:
        print()
        for severity, factor_id, detail in findings:
            print(f"  {severity.upper():4} {factor_id:<26} {detail}")

    print(f"\n{len(fails)} failure(s), "
          f"{len(findings) - len(fails)} warning(s).")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
