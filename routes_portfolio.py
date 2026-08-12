"""
The portfolio route.

Separate from `routes_catalog` for the same reason `routes_enquiry` is: it is
about a *collection* of sites rather than the assessment of one, and the two
have no shared machinery beyond the record that passes between them.

## Where the sites come from

The caller sends records. This route does not store anything, and that is a
deliberate deferral rather than an oversight — the storage decision (a table, a
file, an object store, per-user or per-organisation) is bound up with
authentication, which this product does not have. Building a store now would be
guessing at a data model whose main constraint has not been decided.

What can be built now, and is, is everything downstream of it: the aggregation,
the radar, the ordering, the demo-data discipline and the shape of the
document. When a store arrives it fills `entries` and nothing else changes.
`docs/PORTFOLIO_ARCHITECTURE.md` records that decision and what a real store
must guarantee.

## The demonstration portfolio

`GET /api/portfolio/demo` serves a portfolio built from fixture sites, and
every one of them is marked `is_demo` at the entry, at the row and at the
document. It exists because an empty portfolio cannot show what a portfolio
does, and a screenshot of an empty table sells nothing.

Its numbers are counts of its own fixtures — not a simulation of a real
customer, not scaled to look impressive, and not presented anywhere without the
label. `tests/test_portfolio_route.py` asserts the labelling on every path,
because this is the one endpoint in the product that serves generated evidence
by design, and the discipline that keeps it safe is entirely in the labelling.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import demo_portfolio
import portfolio as portfolio_mod

router = APIRouter()


class PortfolioRequest(BaseModel):
    """Records in, portfolio out.

    Capped at 2,000 records per request. Not a statement about how large a
    portfolio may be — it is a statement about how much one HTTP request should
    carry, and a real store would page rather than post.
    """

    name: str = Field("Portfolio", max_length=120)
    records: List[Dict[str, Any]] = Field(..., max_length=2000)


@router.post("/api/portfolio")
def build_portfolio(req: PortfolioRequest) -> Dict[str, Any]:
    """Aggregate records into one portfolio view.

    Records are merged by `site_id`, so a site assessed by two scanners is one
    site with two records rather than two sites — the failure that would
    otherwise inflate every count by exactly the amount of work done.
    """
    entries = portfolio_mod.merge(
        portfolio_mod.entry_from_record(r) for r in req.records)
    return portfolio_mod.document(
        portfolio_mod.Portfolio(id="adhoc", name=req.name, entries=entries))


@router.get("/api/portfolio/demo")
def demo() -> Dict[str, Any]:
    """A portfolio of demonstration sites, labelled everywhere it appears.

    Serves generated evidence on purpose, which no other endpoint in this
    product does. The label is not decoration: it is the entire reason this is
    permissible, and it travels on the document, on the radar and on every
    individual row so that no fragment of it can be read as a real assessment.
    """
    return portfolio_mod.document(demo_portfolio.build())


@router.get("/api/portfolio/demo/site/{site_id}")
def demo_site(site_id: str) -> Dict[str, Any]:
    """One demonstration site's record.

    Kept behind the `demo` path segment rather than served from `/api/record`,
    so a generated record can never be reached by a URL that looks like the
    real endpoint.
    """
    record = demo_portfolio.record_for(site_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No such demonstration site.")
    return record
