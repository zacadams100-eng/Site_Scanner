"""
The portfolio, and the ways a many-site view can lie.

Single-site mistakes are visible: a professional reads one report and sees the
gaps. Portfolio mistakes are not, and they scale — a miscount is read once and
applied to a thousand sites. So most of these tests are about the specific ways
an aggregate misleads:

    a site never scanned counted as clear
    one site assessed twice counted as two
    demo data blended into a real total
    a rollup that has quietly become a score
    ordering that ranks rather than prioritises

The radar tests carry the most weight. Every number in it is acted on.
"""

from __future__ import annotations

import json

import pytest

import portfolio as portfolio_mod
from portfolio import Portfolio, SiteEntry


def _summary(**over):
    """A record summary, in the shape `site_record.summarise` produces.

    `tests/test_site_evidence_record.py` asserts that shape against the real
    thing; this file builds it directly so a portfolio test can express a site
    that has been assessed twice, or never, without running twenty
    assessments.
    """
    base = {
        "record_id": "rec_abc", "site_id": "site_abc", "site_name": "A field",
        "area_ha": 12.0, "scanner": "land", "scanner_status": "live",
        "assessed_at": "2026-08-01T00:00:00Z",
        "flagged": 0, "informational": 0, "investigations": 0,
        "factors_assessed": 20, "not_assessed": 0, "domain_gaps": 0,
        "review_status": "unreviewed",
    }
    base.update(over)
    return base


def _entry(site_id, name="A field", *, source="drawn", **records):
    return SiteEntry(site_id=site_id, name=name, source=source,
                     records={k: v for k, v in records.items()})


# ---------------------------------------------------------------------------
# A site never scanned is not a clean site
# ---------------------------------------------------------------------------
def test_an_unassessed_site_is_not_reported_as_clear():
    """The product's founding distinction, at portfolio scale where it is
    easier to lose: an empty findings column looks identical for a site that
    was assessed and cleared and one that was never looked at."""
    never = _entry("site_1")
    clear = _entry("site_2", land=_summary())
    assert never.assessed is False
    assert clear.assessed is True
    assert never.flagged == clear.flagged == 0


def test_the_radar_counts_unassessed_sites_beside_the_findings():
    """"87 investigations" without "310 never scanned" invites a reader to
    treat the remainder as clear. At portfolio scale that reading is made once
    and applied to every site in the list."""
    p = Portfolio("p1", "Test", [
        _entry("site_1", land=_summary(flagged=2, investigations=1)),
        _entry("site_2", land=_summary()),
        _entry("site_3"),
        _entry("site_4"),
    ])
    r = portfolio_mod.radar(p)
    assert r["sites"] == 4
    assert r["sites_assessed"] == 2
    assert r["sites_unassessed"] == 2
    assert r["sites_with_findings"] == 1
    assert r["findings"] == 2
    assert r["investigations"] == 1


def test_unassessed_sites_sort_above_assessed_and_clear_ones():
    """They are the work outstanding. A list that buried them at the bottom
    would hide the portfolio's real state behind its completed part."""
    p = Portfolio("p1", "Test", [
        _entry("site_clear", "Clear field", land=_summary()),
        _entry("site_never", "Never scanned"),
        _entry("site_found", "Found something", land=_summary(flagged=3)),
    ])
    order = [r["name"] for r in portfolio_mod.rows(p)]
    assert order == ["Found something", "Never scanned", "Clear field"]


# ---------------------------------------------------------------------------
# One site is one site
# ---------------------------------------------------------------------------
def test_a_site_assessed_by_two_scanners_is_one_site():
    """Getting this wrong inflates every count by exactly the amount of work
    that has been done — the most misleading direction for an error to run."""
    merged = portfolio_mod.merge([
        _entry("site_1", land=_summary(scanner="land", flagged=1)),
        _entry("site_1", water=_summary(scanner="water", flagged=2)),
    ])
    assert len(merged) == 1
    assert sorted(merged[0].records) == ["land", "water"]
    assert merged[0].flagged == 3


def test_reassessing_a_site_replaces_its_record_rather_than_adding_one():
    """Otherwise a site scanned monthly would report twelve times its
    findings by December."""
    merged = portfolio_mod.merge([
        _entry("site_1", land=_summary(flagged=5,
                                       assessed_at="2026-01-01T00:00:00Z")),
        _entry("site_1", land=_summary(flagged=1,
                                       assessed_at="2026-08-01T00:00:00Z")),
    ])
    assert len(merged) == 1
    assert merged[0].flagged == 1, "the older record won"
    assert merged[0].records["land"]["assessed_at"] == "2026-08-01T00:00:00Z"


def test_an_undated_record_does_not_displace_a_dated_one():
    """An undated record is of unknown age. Letting it win would replace a
    known-recent assessment with one that might be a year old."""
    merged = portfolio_mod.merge([
        _entry("site_1", land=_summary(flagged=1,
                                       assessed_at="2026-08-01T00:00:00Z")),
        _entry("site_1", land=_summary(flagged=9, assessed_at="")),
    ])
    assert merged[0].flagged == 1


def test_merge_drops_entries_with_no_site_id():
    """A site with no identity cannot be deduplicated, so it would appear
    once per assessment. Better absent than counted repeatedly."""
    assert portfolio_mod.merge([_entry("")]) == []


# ---------------------------------------------------------------------------
# Demonstration data stays identifiable
# ---------------------------------------------------------------------------
def test_demo_sites_are_counted_and_named_never_blended_in():
    """A radar that mixed demo and real sites would report a number true of
    neither."""
    p = Portfolio("p1", "Test", [
        _entry("site_1", land=_summary(flagged=1)),
        _entry("site_2", source="demo", land=_summary(flagged=4)),
    ])
    r = portfolio_mod.radar(p)
    assert r["demo_sites"] == 1
    assert r["contains_demo_data"] is True


def test_every_row_carries_its_own_demo_label():
    """A row that leaves the table — copied, exported, screenshotted — has to
    take its label with it. A legend at the top of a screen does not survive
    the journey."""
    p = Portfolio("p1", "Test", [_entry("site_2", source="demo",
                                        land=_summary())])
    row = portfolio_mod.rows(p)[0]
    assert row["is_demo"] is True
    assert row["source"] == "demo"


def test_the_document_states_demo_content_at_the_top_level_too():
    """Two places rather than one, because the consequence of missing it is a
    professional reading generated numbers as measurements."""
    p = Portfolio("p1", "Test", [_entry("s", source="demo", land=_summary())])
    doc = portfolio_mod.document(p)
    assert doc["contains_demo_data"] is True
    assert "demonstration" in doc["demo_notice"].lower()

    clean = portfolio_mod.document(Portfolio("p2", "Real", [_entry("s")]))
    assert clean["contains_demo_data"] is False
    assert clean["demo_notice"] == ""


def test_a_demo_site_merged_with_a_real_one_stays_marked_demo():
    """The cautious direction. A mislabelled demo site puts fabricated
    evidence in a professional's view; a real site wrongly marked demo is only
    ignored."""
    merged = portfolio_mod.merge([
        _entry("site_1", source="demo", land=_summary()),
        _entry("site_1", source="drawn", water=_summary(scanner="water")),
    ])
    assert merged[0].is_demo is True


def test_demo_status_is_carried_and_never_inferred():
    """Never guessed from a name or a location, which could be coincidence.
    A site called "Demo Farm" is not demo data, and a demo site called "North
    Field" still is."""
    real = _entry("site_1", "Demo Farm", source="drawn", land=_summary())
    fake = _entry("site_2", "North Field", source="demo", land=_summary())
    assert real.is_demo is False
    assert fake.is_demo is True


# ---------------------------------------------------------------------------
# Gaps
# ---------------------------------------------------------------------------
def test_factor_gaps_and_domain_gaps_are_counted_separately():
    """Different work. A factor gap may close on a re-run; a domain gap needs
    a source that does not exist yet, and telling an owner to re-run will not
    close it."""
    p = Portfolio("p1", "Test", [
        _entry("site_1", land=_summary(not_assessed=18, domain_gaps=0)),
        _entry("site_2", water=_summary(scanner="water", not_assessed=4,
                                        domain_gaps=3)),
    ])
    r = portfolio_mod.radar(p)
    assert r["factor_gaps"] == 22
    assert r["domain_gaps"] == 3
    assert r["evidence_gaps"] == 25


def test_the_radar_reports_coverage_per_scanner():
    """An owner reading "1,204 sites" needs to know Water has seen forty."""
    p = Portfolio("p1", "Test", [
        _entry("site_1", land=_summary()),
        _entry("site_2", land=_summary()),
        _entry("site_3", water=_summary(scanner="water")),
    ])
    assert portfolio_mod.radar(p)["by_scanner"] == {"land": 2, "water": 1}


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------
def test_only_sites_with_findings_await_review():
    """A record with no findings and no review is not waiting for anybody.
    Putting it in the queue would bury the ones that are."""
    with_findings = _entry("site_1", land=_summary(flagged=2,
                                                   review_status="unreviewed"))
    without = _entry("site_2", land=_summary(flagged=0,
                                             review_status="unreviewed"))
    assert with_findings.awaiting_review is True
    assert without.awaiting_review is False

    p = Portfolio("p1", "Test", [with_findings, without])
    assert portfolio_mod.radar(p)["awaiting_review"] == 1


# ---------------------------------------------------------------------------
# No score, at portfolio scale either
# ---------------------------------------------------------------------------
def test_the_portfolio_document_contains_no_score_or_ranking_value():
    """`EM7` does not stop being true because there are more sites. A
    portfolio is where the pressure to add one is highest — a column that sorts
    is worth money to a buyer — and where it would do the most damage."""
    p = Portfolio("p1", "Test", [
        _entry("site_1", land=_summary(flagged=3)),
        _entry("site_2", land=_summary()),
    ])
    text = json.dumps(portfolio_mod.document(p)).lower()
    for banned in ('"score"', '"grade"', '"rating"', '"rank"', '"index"',
                   '"suitability"', '"risk_score"', '"priority_score"'):
        assert banned not in text, f"the portfolio carries a {banned} field"


def test_the_order_is_explained_by_the_columns_the_row_shows():
    """Ordering is not ranking. A reader must be able to see why a site is
    where it is, from the row itself — which is exactly what a computed score
    removes."""
    p = Portfolio("p1", "Test", [
        _entry("site_1", "Quiet", land=_summary()),
        _entry("site_2", "Busy", land=_summary(flagged=4, investigations=2)),
    ])
    rows = portfolio_mod.rows(p)
    assert rows[0]["name"] == "Busy"
    # The values that produced the order are all present in the row.
    assert rows[0]["findings"] == 4 and rows[0]["investigations"] == 2
    assert rows[1]["findings"] == 0


# ---------------------------------------------------------------------------
# Shape and scale
# ---------------------------------------------------------------------------
def test_an_empty_portfolio_reports_zeroes_rather_than_failing():
    """The state every portfolio starts in, and the one an empty state has to
    render honestly rather than crash on."""
    r = portfolio_mod.radar(Portfolio("p1", "Empty", []))
    assert r["sites"] == 0 and r["sites_unassessed"] == 0
    assert r["findings"] == 0
    assert portfolio_mod.rows(Portfolio("p1", "Empty", [])) == []


def test_a_portfolio_holds_summaries_rather_than_records():
    """A thousand full records would be a document that has to be rebuilt
    whenever one site is reassessed, in order to show twelve fields per row.

    Asserted against a real record rather than this file's fixture: the point
    is that the heavy parts of an actual record do not reach the portfolio.
    """
    import scanners
    import site_record
    from fastapi.testclient import TestClient
    import mock_ee_backend

    geometry = {"type": "Polygon", "coordinates": [[
        [-0.62, 51.22], [-0.62, 51.28], [-0.54, 51.28],
        [-0.54, 51.22], [-0.62, 51.22]]]}
    with TestClient(mock_ee_backend.app) as c:
        record = c.post("/api/record", json={
            "geometry": geometry, "factor_ids": ["ndvi"],
            "scanner": "land"}).json()

    entry = portfolio_mod.entry_from_record(record)
    stored = entry.records["land"]
    # The expensive parts of a record, none of which a row displays.
    for heavy in ("observations", "findings", "investigations_detail",
                  "gaps", "review", "coverage", "limits", "principle"):
        assert heavy not in stored, (
            f"the portfolio is storing {heavy!r} per site, which makes the "
            f"document grow with the evidence rather than with the sites")
    # And it is genuinely smaller than what it summarises.
    assert len(json.dumps(stored)) < len(json.dumps(record)) / 2


def test_the_radar_is_one_pass_and_holds_at_scale():
    """Not a performance claim — nothing here is expensive. It asserts the
    shape stays linear in sites rather than in findings, which is what makes
    one interface work at one site and at ten thousand."""
    many = [_entry(f"site_{i}", f"Site {i}",
                   land=_summary(flagged=i % 3, not_assessed=i % 5))
            for i in range(5000)]
    r = portfolio_mod.radar(Portfolio("big", "Big", many))
    assert r["sites"] == 5000
    assert r["sites_assessed"] == 5000
    assert r["findings"] == sum(i % 3 for i in range(5000))


def test_an_entry_can_be_built_from_a_real_record():
    """The ordinary path into a portfolio, against the real record shape
    rather than this file's fixture."""
    import scanners
    import site_record
    from fastapi.testclient import TestClient
    import mock_ee_backend

    geometry = {"type": "Polygon", "coordinates": [[
        [-0.62, 51.22], [-0.62, 51.28], [-0.54, 51.28],
        [-0.54, 51.22], [-0.62, 51.22]]]}
    with TestClient(mock_ee_backend.app) as c:
        r = c.post("/api/record", json={
            "geometry": geometry, "factor_ids": ["ndvi"], "scanner": "land",
            "site_name": "North field"})
    assert r.status_code == 200, r.text
    record = r.json()

    entry = portfolio_mod.entry_from_record(record)
    assert entry.site_id == site_record.site_id(geometry)
    assert entry.name == "North field"
    assert entry.assessed is True
    assert "land" in entry.records
    assert entry.is_demo is False
