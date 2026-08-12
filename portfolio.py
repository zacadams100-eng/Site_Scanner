"""
The portfolio — many sites, one view.

The product's second question. The first is "tell me about this site", which is
what everything else here answers. This one is "tell me about all of these
sites", and it is a different question rather than the same question repeated:
the answer a portfolio owner needs is not a thousand reports but the handful of
places in them that need a person.

    portfolio → sites → records → radar
                                → gaps
                                → reviews

## What a portfolio is, structurally

A list of `SiteEntry`, each holding a site's identity and the summary of its
most recent record per scanner. Nothing more. It deliberately does **not** hold
the records themselves: a portfolio of a thousand sites would then be a
hundred-megabyte document that has to be rebuilt whenever one site is
reassessed, and the row a user reads needs twelve fields of it.

Records live wherever records live — a file, a table, an object store. This
module takes them as input and never fetches, which is what keeps it testable
and what keeps the storage decision open. See `docs/PORTFOLIO_ARCHITECTURE.md`
for the shape a real store has to have and why that decision is deferred rather
than forgotten.

## The Portfolio Radar

The counts a portfolio owner acts on, and the reason this module exists at all.

    1,204 sites · 87 investigations open · 214 evidence gaps
    42 awaiting review · 16 with new findings

Every one of those is a count of something in the records supplied. There is no
model, no estimate and no extrapolation anywhere in this file. A portfolio
statistic that was partly derived would be the most damaging fabrication in the
product, because it is the number an owner would act on across a thousand
sites at once rather than one.

**`sites_unassessed` sits in the radar beside the findings**, at the same
weight, for the reason the whole product exists: a portfolio view showing "87
investigations" without "310 sites never scanned" invites its reader to treat
the remainder as clear.

## Scale

The interface has to work at one site and at ten thousand. That is a shape
constraint on this module rather than a performance one — nothing here is
expensive — and it is met by summarising per site rather than per finding, and
by every radar count being a single pass over the entries.

The real limit is upstream: assessing ten thousand sites is ten thousand
assessments, which is a job queue this product does not have. That is recorded
in the architecture document rather than pretended away, and `PortfolioRadar`
counts what has actually been assessed rather than what has been added.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import site_record

#: The shape of a portfolio document, versioned for the same reason a record is.
PORTFOLIO_SCHEMA = "1.0.0"

#: How a site entered the portfolio. Carried because it changes what a gap
#: means: a site added and never scanned is work outstanding, while a site
#: whose scan failed is a fault to investigate, and a single "no record" state
#: would collapse the two.
SOURCES = ("drawn", "imported", "demo")


@dataclass(frozen=True)
class SiteEntry:
    """One site in a portfolio, and the state of what is known about it.

    Holds record *summaries*, not records — one per scanner, the most recent.
    A portfolio row shows twelve fields and a thousand full records would make
    the document unreadable and unbuildable at once.
    """

    site_id: str
    name: str
    #: The geometry, kept so the portfolio can draw and re-assess without a
    #: second lookup. This is the one large field, and it is the one that
    #: cannot be derived from anything else.
    geometry: Mapping[str, Any] = field(default_factory=dict)
    area_ha: Optional[float] = None
    #: Scanner id → the summary of that scanner's most recent record.
    records: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    #: Where this site came from. `demo` is load-bearing — see `is_demo`.
    source: str = "drawn"
    added_at: str = ""

    @property
    def assessed(self) -> bool:
        """Whether any scanner has produced a record for this site.

        Not "whether it has findings". A site assessed and clear and a site
        never assessed are the two things this product exists to keep apart,
        and at portfolio scale the distinction is easier to lose, not harder —
        an empty findings column looks identical for both.
        """
        return bool(self.records)

    @property
    def is_demo(self) -> bool:
        """Whether this entry is demonstration data.

        Never inferred from the name, the geometry or anything else that could
        be coincidence: it is set at creation and carried. A demo site that
        stopped being identifiable as one would put fabricated evidence in a
        view a professional reads, which is the failure this whole codebase is
        arranged to prevent.
        """
        return self.source == "demo"

    def summary_for(self, scanner_id: str) -> Optional[Mapping[str, Any]]:
        return self.records.get(scanner_id)

    @property
    def flagged(self) -> int:
        return sum(int(r.get("flagged") or 0) for r in self.records.values())

    @property
    def investigations(self) -> int:
        return sum(int(r.get("investigations") or 0)
                   for r in self.records.values())

    @property
    def evidence_gaps(self) -> int:
        """Factors that could not be assessed, plus domains never covered.

        Both, because they are both gaps and an owner deciding where to spend
        attention does not care which kind a given hole is. They are reported
        separately in the radar, where the distinction does matter: a factor
        gap may close on a re-run, and a domain gap needs a source that does
        not exist yet.
        """
        return sum(int(r.get("not_assessed") or 0) + int(r.get("domain_gaps") or 0)
                   for r in self.records.values())

    @property
    def awaiting_review(self) -> bool:
        """Whether any record here has findings that nobody has reviewed.

        Findings, specifically. A record with no findings and no review is not
        waiting for anybody — putting it in the queue would bury the ones that
        are.
        """
        return any(r.get("review_status") == "unreviewed"
                   and int(r.get("flagged") or 0) > 0
                   for r in self.records.values())


def entry_from_record(record: Mapping[str, Any], *,
                      source: str = "drawn") -> SiteEntry:
    """One site entry from one record.

    The ordinary way a site joins a portfolio: it was assessed, and the
    assessment is what is known about it.
    """
    site = record.get("site") or {}
    summary = site_record.summarise(record)
    return SiteEntry(
        site_id=site.get("id", ""),
        name=site.get("name") or "Untitled site",
        geometry=site.get("geometry") or {},
        area_ha=site.get("area_ha"),
        records={summary["scanner"]: summary},
        source=source,
        added_at=record.get("assessed_at", ""),
    )


def merge(entries: Iterable[SiteEntry]) -> List[SiteEntry]:
    """Collapse entries for one site into one, keeping the latest per scanner.

    A site assessed by Land in March and by Water in August is one site with
    two records, not two sites. Getting this wrong would inflate every count in
    the radar by exactly the amount of work that had been done, which is the
    most misleading direction for an error to run.

    Latest wins per scanner, by `assessed_at`. Records without a timestamp lose
    to records with one rather than sorting arbitrarily — an undated record is
    of unknown age and should not displace one whose age is known.
    """
    by_site: Dict[str, SiteEntry] = {}
    for e in entries:
        if not e.site_id:
            continue
        existing = by_site.get(e.site_id)
        if existing is None:
            by_site[e.site_id] = e
            continue

        records = dict(existing.records)
        for scanner_id, summary in e.records.items():
            current = records.get(scanner_id)
            if current is None or _newer(summary, current):
                records[scanner_id] = summary
        by_site[e.site_id] = SiteEntry(
            site_id=existing.site_id,
            # A demo entry merged with a real one stays marked demo. The
            # cautious direction: a mislabelled demo site is fabricated
            # evidence in a professional's view, where a real site wrongly
            # marked demo is only ignored.
            name=existing.name or e.name,
            geometry=existing.geometry or e.geometry,
            area_ha=existing.area_ha if existing.area_ha is not None else e.area_ha,
            records=records,
            source="demo" if (existing.is_demo or e.is_demo) else existing.source,
            added_at=min(x for x in (existing.added_at, e.added_at) if x)
                     if (existing.added_at or e.added_at) else "",
        )
    return list(by_site.values())


def _newer(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    at_a, at_b = a.get("assessed_at") or "", b.get("assessed_at") or ""
    if at_a and not at_b:
        return True
    if not at_a:
        return False
    return at_a > at_b


@dataclass(frozen=True)
class Portfolio:
    """A named collection of sites.

    Frozen, and rebuilt rather than mutated, for the same reason a `Scanner`
    is: it is read concurrently and a mutable one is a cross-request leak
    waiting to happen.
    """

    id: str
    name: str
    entries: Sequence[SiteEntry] = ()

    @property
    def demo_entries(self) -> List[SiteEntry]:
        return [e for e in self.entries if e.is_demo]

    @property
    def contains_demo_data(self) -> bool:
        return any(e.is_demo for e in self.entries)


def radar(portfolio: Portfolio) -> Dict[str, Any]:
    """The Portfolio Radar — what needs a person, counted.

    Every number here is a count of something present in the entries supplied.
    Nothing is modelled, estimated or extrapolated. A portfolio statistic that
    was partly derived would be the most damaging fabrication available in this
    product, because it is acted on across every site at once.

    The three that matter most, and why each is in the list:

    - `sites_unassessed` — the denominator of everything else. Without it,
      "87 investigations" reads as the whole picture.
    - `domain_gaps` — separated from factor gaps because they are different
      work. A factor gap may close on a re-run; a domain gap needs a source
      that does not exist.
    - `awaiting_review` — findings nobody qualified has looked at, which is
      every finding this product has ever produced.
    """
    entries = list(portfolio.entries)
    assessed = [e for e in entries if e.assessed]

    scanners_seen: Dict[str, int] = {}
    factor_gaps = 0
    domain_gaps = 0
    for e in assessed:
        for scanner_id, summary in e.records.items():
            scanners_seen[scanner_id] = scanners_seen.get(scanner_id, 0) + 1
            factor_gaps += int(summary.get("not_assessed") or 0)
            domain_gaps += int(summary.get("domain_gaps") or 0)

    return {
        "sites": len(entries),
        "sites_assessed": len(assessed),
        # Beside the findings and at the same weight. A portfolio view showing
        # investigations without this number invites its reader to treat the
        # remainder as clear, which is the one reading this product exists to
        # prevent — and at portfolio scale the mistake is made once and applied
        # to a thousand sites.
        "sites_unassessed": len(entries) - len(assessed),
        "sites_with_findings": sum(1 for e in assessed if e.flagged > 0),
        "findings": sum(e.flagged for e in assessed),
        "investigations": sum(e.investigations for e in assessed),
        "factor_gaps": factor_gaps,
        "domain_gaps": domain_gaps,
        "evidence_gaps": factor_gaps + domain_gaps,
        "awaiting_review": sum(1 for e in assessed if e.awaiting_review),
        # Coverage per scanner: how many sites each has actually looked at.
        # An owner reading "1,204 sites" needs to know that Water has seen 40.
        "by_scanner": dict(sorted(scanners_seen.items())),
        # Demonstration data is counted and named, never blended in. A radar
        # that mixed demo and real sites would report a number that is true of
        # neither.
        "demo_sites": sum(1 for e in entries if e.is_demo),
        "contains_demo_data": portfolio.contains_demo_data,
    }


def rows(portfolio: Portfolio) -> List[Dict[str, Any]]:
    """The table. One row per site, ordered by what needs attention first.

    **Ordering is not ranking.** The order is: sites with findings, then sites
    never assessed, then the rest — and the row shows the counts that produced
    that order, so a reader can see why a site is where it is. What it must
    never become is a sort by a computed score, which is the same thing with
    the reasoning removed.

    Unassessed sites sort *above* assessed-and-clear ones deliberately. They
    are the work outstanding, and a list that buried them at the bottom would
    hide the portfolio's real state behind its completed part.
    """
    def key(e: SiteEntry):
        return (
            0 if e.flagged else (1 if not e.assessed else 2),
            -e.flagged,
            -e.investigations,
            e.name.lower(),
        )

    out = []
    for e in sorted(portfolio.entries, key=key):
        out.append({
            "site_id": e.site_id,
            "name": e.name,
            "area_ha": e.area_ha,
            "assessed": e.assessed,
            "scanners": sorted(e.records),
            "findings": e.flagged,
            "investigations": e.investigations,
            "evidence_gaps": e.evidence_gaps,
            "awaiting_review": e.awaiting_review,
            "last_assessed": max(
                (r.get("assessed_at") or "" for r in e.records.values()),
                default=""),
            # Carried on every row, not only in a legend. A row that leaves the
            # table — copied, exported, screenshotted — has to take its own
            # label with it.
            "is_demo": e.is_demo,
            "source": e.source,
        })
    return out


def document(portfolio: Portfolio) -> Dict[str, Any]:
    """The whole portfolio, as the API serves it."""
    return {
        "portfolio_schema": PORTFOLIO_SCHEMA,
        "id": portfolio.id,
        "name": portfolio.name,
        "radar": radar(portfolio),
        "sites": rows(portfolio),
        # Stated at the top level as well as per row. Two places rather than
        # one because the consequence of missing it is a professional reading
        # generated numbers as measurements.
        "contains_demo_data": portfolio.contains_demo_data,
        "demo_notice": (
            "This portfolio contains demonstration sites. Rows marked "
            "`is_demo` were generated to show the interface and are not "
            "observations of those places."
        ) if portfolio.contains_demo_data else "",
    }
