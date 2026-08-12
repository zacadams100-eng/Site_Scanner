"""
The demonstration portfolio.

The one place in this product that serves generated evidence on purpose, and
therefore the one place where the labelling *is* the safety mechanism rather
than a courtesy.

## Why it exists

An empty portfolio cannot show what a portfolio does. The Portfolio Radar's
value is visible at forty sites and invisible at zero, and there is no real
portfolio to show because there are no real customers and no Earth Engine
credentials to assess their sites with. Refusing to build one would mean the
feature could not be demonstrated, reviewed or designed against.

## The rules it follows, and why each one

**Every record is stamped `is_demo` at three levels** — the record, the
portfolio entry, and every row. Not one flag at the top: a row that is copied,
exported or screenshotted has to carry its own label, because that fragment is
what a third person sees.

**Sites are named as demonstrations.** "Demonstration site 03" cannot be
mistaken for a place. Naming them "Marsh Farm, Kent" would produce a document
that looks exactly like a real assessment of a real farm — and the moment one
of those leaves the building, this product has published a fabricated claim
about somebody's land.

**Geometries are in England and are not real holdings.** They have to be
somewhere for the map to draw them; they are placed on open countryside at
coordinates chosen for spread, and no attempt is made to match a real parcel
boundary.

**Findings use the real rules' own wording and thresholds.** A demo that
invented finding text would misrepresent what the product says as well as what
it found. The rules are read from the registry, so the demo cannot claim a
check the product does not have — and if a threshold changes, this changes with
it.

**Every observation's provenance says `generated`.** The source block is not
faked. A reader following a demo finding to its source is told exactly what
produced it, which is the same answer the mock backend gives everywhere else in
the product.

**The numbers are deterministic.** Seeded from the site id, so the demo is
stable across processes and deploys: a screenshot taken today matches the
screen tomorrow, and `record_id` stays stable, which is what the portfolio's
deduplication relies on.

## What it deliberately does not do

No trend, no history, no month-over-month change. A longitudinal demo would
mean generating a *past*, and a fabricated history is the one thing that could
not be distinguished from the real longitudinal record this product intends to
build. The demo shows a portfolio at one moment.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import portfolio as portfolio_mod
import scanners
import site_record

#: The label attached to every artefact this module produces.
DEMO_NOTICE = (
    "Demonstration data. These sites are not real holdings and these findings "
    "are not observations of any place — they show the shape of a portfolio, "
    "generated from the product's own rules. No measurement here came from a "
    "satellite, a gauge or a register."
)

#: Where the demonstration sites sit. Open countryside across England, chosen
#: for spread on a national map rather than to resemble any holding. Each is a
#: small rectangle; none is drawn from a real parcel boundary.
_ANCHORS = (
    (-0.58, 51.24), (-2.58, 51.45), (-1.47, 53.38), (0.52, 51.28),
    (-2.99, 53.41), (-1.08, 53.96), (-3.53, 50.72), (0.12, 52.20),
    (-1.90, 52.48), (-2.24, 53.48), (-0.34, 53.74), (-4.14, 50.37),
    (-1.31, 51.06), (-2.75, 54.05), (0.90, 51.88), (-1.61, 54.97),
    (-3.18, 51.48), (-0.14, 50.83), (-2.10, 52.19), (-1.13, 52.63),
    (-0.75, 52.05), (-2.44, 50.72), (-1.78, 51.56), (-0.02, 51.53),
)


def _seed(text: str) -> int:
    """A stable integer from a string.

    `hash()` is randomised per process in Python 3, so using it would make the
    demo different on every restart — screenshots would not match the screen
    and `record_id` would change on every deploy, which is precisely the
    instability the record's identity is designed to avoid.
    """
    return int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)


def _geometry(index: int) -> Dict[str, Any]:
    lng, lat = _ANCHORS[index % len(_ANCHORS)]
    # A few hundred metres across — the size of site this product is for.
    d = 0.006 + (index % 4) * 0.002
    return {
        "type": "Polygon",
        "coordinates": [[
            [round(lng, 6), round(lat, 6)],
            [round(lng + d, 6), round(lat, 6)],
            [round(lng + d, 6), round(lat + d, 6)],
            [round(lng, 6), round(lat + d, 6)],
            [round(lng, 6), round(lat, 6)],
        ]],
    }


def _observation(factor_id: str, name: str, state: str,
                 reason: Optional[str] = None) -> Dict[str, Any]:
    """One observation, whose provenance tells the truth about itself.

    The source block is not faked. `runtime: generated` is the same answer the
    mock backend gives for a generated factor anywhere else in the product, so
    a reader who follows a demo finding to its source is told exactly what
    produced it.
    """
    return {
        "factor": factor_id,
        "name": name,
        "state": state,
        "reason": reason,
        "observed_at": "",
        "source": {
            "publisher": "", "endpoint": "", "dataset": "",
            "licence": "", "attribution": "",
            "runtime": "generated",
            "kind": "generated",
        },
        "claims": {
            "establishes": "Nothing. This is demonstration data.",
            "not_established": (
                "This is generated data and establishes nothing about any "
                "place. It is present to show the shape of the interface."),
        },
    }


def _finding(rule: Any, domain: str) -> Dict[str, Any]:
    """A finding that uses the real rule's own wording and threshold.

    Read from the registry rather than written here, so the demo cannot show a
    check the product does not have, and cannot show a threshold the product no
    longer uses.
    """
    meta = dict(getattr(rule, "meta", None) or {})
    return {
        "id": rule.id,
        "factor": rule.needs[0] if rule.needs else "",
        "domain": domain,
        "kind": "flag",
        "severity": "medium",
        "statement": rule.asks,
        "threshold": str(meta.get("threshold_display") or
                         meta.get("threshold") or ""),
        "evidence": {"demo": True},
        "rule": {**meta, "demo": True},
    }


def _record(index: int) -> Dict[str, Any]:
    """One demonstration record, in the real record's shape.

    Built through `site_record.build` rather than assembled by hand, so the
    demo cannot drift into a shape the real record does not have — and so the
    identifiers, versions and gap accounting are computed by the same code that
    computes them for a real assessment.
    """
    geometry = _geometry(index)
    name = f"Demonstration site {index + 1:02d}"
    seed = _seed(name)

    # Which scanner, spread across the built ones so the demo shows a portfolio
    # assessed by more than one instrument.
    built = ("land", "water", "ecology", "planning")
    scanner = scanners.resolve(built[seed % len(built)])

    flags = [r for r in scanner.rules if r.kind == "flag"]
    # Weighted so most sites are quiet: 0, 0, 0, 1, 1, 2. A demo where four
    # sites in five carry a finding would misrepresent both a real portfolio
    # and this product — it would read as a tool that finds something
    # everywhere, which is the behaviour of an alarm rather than an instrument.
    n_findings = (0, 0, 0, 1, 1, 2)[(seed >> 3) % 6]
    chosen = [flags[(seed + i) % len(flags)] for i in range(n_findings)] \
        if flags else []
    # De-duplicate while keeping order: one rule cannot fire twice.
    seen, picked = set(), []
    for r in chosen:
        if r.id not in seen:
            seen.add(r.id)
            picked.append(r)

    observations: List[Dict[str, Any]] = []
    for i, factor_id in enumerate(scanner.factors[:14]):
        # Most demo factors are unassessed, which is the honest picture of this
        # product today and the one worth showing: a portfolio's real texture is
        # its gaps, not its findings.
        state = "not_assessed" if (seed + i) % 3 else "clear"
        observations.append(_observation(
            factor_id, factor_id.replace("_", " ").title(), state,
            "demo_data" if state == "not_assessed" else None))

    payload = {
        "geometry": geometry,
        "area_ha": round(30 + (seed % 400) / 3.0, 1),
        "centroid": {},
        "evidence": [],
        "radar": {},
    }
    # The moment this record was assembled, which is the literal truth about it
    # and the only date available that is not invented. Leaving it empty made
    # every row in the portfolio read "Date not recorded", which looks like a
    # rendering fault; spreading the dates over past months to look realistic
    # would be fabricating a history, and a fabricated past is the one thing
    # indistinguishable from the real longitudinal record this product intends
    # to build. So the whole demonstration portfolio shares one timestamp — a
    # batch assessed in one moment, because that is what happened.
    #
    # Excluded from `record_id` by construction, so this does not affect the
    # determinism the portfolio's deduplication relies on.
    record = site_record.build(
        payload, scanner=scanner, site_name=name,
        assessed_at=datetime.now(timezone.utc).isoformat())
    record["observations"] = observations
    record["findings"] = [
        _finding(r, scanner.rule_domains.get(r.id, "")) for r in picked]
    record["investigations"] = [
        {"id": inv, "name": (scanner.investigations.get(inv) or {}).get(
            "name", inv), "priority": "standard", "raised_by": [r.id]}
        for r in picked for inv in r.investigations[:1]
    ]
    record["gaps"] = {
        "factors": [{"factor": o["factor"], "reason": o["reason"]}
                    for o in observations if o["state"] == "not_assessed"],
        "by_reason": {"demo_data": sum(
            1 for o in observations if o["state"] == "not_assessed")},
        "factor_count": sum(1 for o in observations
                            if o["state"] == "not_assessed"),
        "domains": [{"id": d.id, "name": d.name, "subject": d.subject,
                     "blocked_by": d.blocked_by}
                    for d in scanner.declared_domains],
        "domain_count": len(scanner.declared_domains),
    }
    # Stamped on the record itself, not only on the portfolio row. A record
    # fetched directly has to say what it is.
    record["is_demo"] = True
    record["demo_notice"] = DEMO_NOTICE
    return record


#: How many demonstration sites. Enough that the radar's counts mean something
#: and the table needs scrolling; not so many that the demo implies a customer
#: base. Twenty-four is two screens.
DEMO_SITE_COUNT = 24

#: Of those, how many have been added and never assessed.
#:
#: Not decoration. `sites_unassessed` is the radar's most important number and
#: a demonstration portfolio where every site had been scanned would hide the
#: one figure that stops a reader treating the remainder as clear. It is also
#: the honest picture of any real portfolio: sites arrive faster than they are
#: assessed, and the gap between the two is the thing an owner manages.
DEMO_UNASSESSED_COUNT = 6


def records() -> List[Dict[str, Any]]:
    """Records for the sites that have been assessed.

    The unassessed sites deliberately have none — that is what unassessed
    means, and giving them an empty record would make them indistinguishable
    from sites that were scanned and found clear.
    """
    return [_record(i) for i in range(DEMO_SITE_COUNT - DEMO_UNASSESSED_COUNT)]


def _unassessed_entries() -> List[portfolio_mod.SiteEntry]:
    """Sites on the books that nothing has looked at yet."""
    out = []
    for i in range(DEMO_SITE_COUNT - DEMO_UNASSESSED_COUNT, DEMO_SITE_COUNT):
        geometry = _geometry(i)
        name = f"Demonstration site {i + 1:02d}"
        out.append(portfolio_mod.SiteEntry(
            site_id=site_record.site_id(geometry),
            name=name,
            geometry=geometry,
            area_ha=round(30 + (_seed(name) % 400) / 3.0, 1),
            records={},
            source="demo",
        ))
    return out


def record_for(site_id: str) -> Optional[Dict[str, Any]]:
    for r in records():
        if (r.get("site") or {}).get("id") == site_id:
            return r
    return None


def build() -> portfolio_mod.Portfolio:
    """The demonstration portfolio.

    Every entry carries `source="demo"`, which is what makes `is_demo` true on
    the entry, on every row and on the document. It is set here, at creation,
    and never inferred downstream — inferring it from a name would mean a real
    site called "Demo Farm" was silently treated as fabricated.
    """
    entries = portfolio_mod.merge(
        [portfolio_mod.entry_from_record(r, source="demo") for r in records()]
        + _unassessed_entries())
    return portfolio_mod.Portfolio(
        id="demo", name="Demonstration portfolio", entries=entries)
