"""
The ONS spreadsheet ingest.

The releases themselves cannot be downloaded from here — the proxy blocks
ons.gov.uk along with every other open-data host — so these tests build
workbooks that reproduce the *shapes* the real files have, and run the whole
path over them: parse, store, read back, register, serve.

That covers the part most likely to break. A government spreadsheet is laid
out for a person reading it, and the layout changes between releases: notes
above the header, the area column called four different things across four
files, suppressed values written as `:` or `x`, dates as `2024 JUL` or
`Jul-24`. What it cannot cover is whether today's URL still resolves, which is
what `python3 -m ons.job --check` is for.
"""

import json
import pathlib

import pytest

openpyxl = pytest.importorskip("openpyxl")

from ons import job, parse                                    # noqa: E402
from ons.datasets import Column, Dataset                      # noqa: E402


def workbook(tmp_path, rows, sheet_name="Table 3", extra_sheets=()):
    """A workbook with `rows` written verbatim — preamble, headers and all."""
    book = openpyxl.Workbook()
    book.active.title = sheet_name
    for row in rows:
        book.active.append(list(row))
    for name in extra_sheets:
        book.create_sheet(name)
    path = tmp_path / "release.xlsx"
    book.save(path)
    return path


def monthly_spec(**kw):
    base = dict(
        id="private_rents", title="Rents", publisher="ONS", licence="OGL v3",
        url="https://example.invalid/rents.xlsx", page="https://example.invalid",
        cadence="monthly", sheet="Table 3", header_contains="code",
        period_column="date",
        columns=[Column("rental_median", "average rent", lo=200, hi=6000)],
    )
    base.update(kw)
    return Dataset(**base)


RENT_ROWS = [
    ("Price Index of Private Rents, UK",),          # a title
    ("Contact: prices@ons.gov.uk",),                # and a note
    (),                                             # and a spacer
    ("Area code", "Area name", "Date", "Average rent (£)"),
    ("E07000209", "Guildford", "2024 JUN", 1420.0),
    ("E07000209", "Guildford", "2024 JUL", 1435.0),
    ("E09000007", "Camden", "2024 JUL", 2380.0),
    ("E12000008", "South East", "2024 JUL", 1310.0),   # a region, not an LA
    ("W06000015", "Cardiff", "2024 JUL", 1105.0),      # Wales, out of coverage
]


# --------------------------------------------------------------------------
# Finding things in a sheet laid out for a human
# --------------------------------------------------------------------------
def test_the_header_row_is_found_below_the_preamble():
    rows = [list(r) for r in RENT_ROWS]
    found = parse.find_header(rows, "code")
    assert rows[found][0] == "Area code"


def test_the_header_row_is_found_however_many_notes_precede_it():
    """Releases add and remove notes at the top, which moves every cell
    reference. Nothing here may depend on a row number."""
    for preamble in (0, 1, 7):
        rows = [["a note"] for _ in range(preamble)] + [
            ["Area code", "Date", "Average rent (£)"],
            ["E07000209", "2024 JUL", 1435.0],
        ]
        assert parse.find_header(rows, "code") == preamble


def test_a_missing_header_is_an_error_not_a_guess():
    with pytest.raises(parse.ParseError, match="no header row"):
        parse.find_header([["some", "unrelated", "sheet"]], "code")


def test_the_area_column_is_found_by_its_values_not_its_heading():
    """ONS calls it 'Area code', 'LAD24CD', 'ladcode23' and 'Local authority
    code' across the four files we read. Every one of them holds E07000209."""
    for heading in ("Area code", "LAD24CD", "ladcode23", "Local authority code"):
        rows = [[heading, "Name"]] + [[f"E070002{i:02d}", "x"] for i in range(10)]
        assert parse.find_area_column(rows, 0) == 0


def test_the_area_column_is_found_even_when_it_is_not_first():
    rows = [["Name", "Region", "Code"]] + \
           [["x", "South East", f"E070002{i:02d}"] for i in range(10)]
    assert parse.find_area_column(rows, 0) == 2


def test_a_sheet_with_no_area_codes_is_refused():
    rows = [["Year", "Value"]] + [[2020 + i, i] for i in range(10)]
    with pytest.raises(parse.ParseError, match="no column of ONS area codes"):
        parse.find_area_column(rows, 0)


@pytest.mark.parametrize("raw, cadence, expected", [
    ("2024 JUL", "monthly", "2024-07"),
    ("2024-07", "monthly", "2024-07"),
    ("Jul-24", "monthly", "2024-07"),
    ("Jul-2024", "monthly", "2024-07"),
    ("2024", "annual", "2024"),
    ("Year ending March 2021", "annual", "2021"),
    ("", "monthly", None),
    ("not a date", "monthly", None),
])
def test_periods_are_normalised_from_every_shape_ons_uses(raw, cadence, expected):
    assert parse.normalise_period(raw, cadence) == expected


@pytest.mark.parametrize("cell, expected", [
    (1420, 1420.0), (1420.5, 1420.5), ("1,420", 1420.0), ("£1,420", 1420.0),
    ("12.5%", 12.5),
    # Every one of these means "no observation" in some government release.
    (":", None), ("x", None), ("..", None), ("#", None), ("N/A", None),
    ("c", None), ("", None), (None, None), ("text", None),
])
def test_suppressed_values_are_gaps_not_zeros(cell, expected):
    assert parse._number(cell) == expected


# --------------------------------------------------------------------------
# Parsing a whole sheet
# --------------------------------------------------------------------------
def test_a_monthly_release_parses_to_observations(tmp_path):
    path = workbook(tmp_path, RENT_ROWS)
    got = parse.parse_workbook(path, monthly_spec())

    assert ("rental_median", "E07000209", "2024-07", 1435.0) in got
    assert ("rental_median", "E07000209", "2024-06", 1420.0) in got
    assert ("rental_median", "E09000007", "2024-07", 2380.0) in got


def test_regions_and_other_countries_are_left_out(tmp_path):
    """A figure for the whole South East is not what someone drawing a field
    in Guildford should be shown, and the app covers England."""
    got = parse.parse_workbook(workbook(tmp_path, RENT_ROWS), monthly_spec())
    areas = {a for _, a, _, _ in got}
    assert "E12000008" not in areas, "regions must not be reported as districts"
    assert "W06000015" not in areas, "coverage is England"


def test_a_column_matching_the_wrong_header_is_caught_by_its_values(tmp_path):
    """A fragment match can land on the wrong column — 'median' appears in
    'median rent' and in 'median week'. Bounds are how that gets noticed
    instead of stored."""
    rows = [
        ("Area code", "Date", "Average rent (£)"),
    ] + [(f"E070002{i:02d}", "2024 JUL", 3.5) for i in range(10)]   # weeks, not rent
    with pytest.raises(parse.ParseError, match="wrong column"):
        parse.parse_workbook(workbook(tmp_path, rows), monthly_spec())


def test_a_file_that_parses_to_nothing_is_an_error(tmp_path):
    """The most dangerous outcome: it looks like a successful refresh and it
    silently empties a factor."""
    rows = [
        ("Area code", "Date", "Average rent (£)"),
    ] + [(f"E070002{i:02d}", "2024 JUL", ":") for i in range(10)]
    with pytest.raises(parse.ParseError, match="no observations"):
        parse.parse_workbook(workbook(tmp_path, rows), monthly_spec())


def test_a_renamed_sheet_is_still_found(tmp_path):
    """'Table 3' becomes '3a' between releases. Failing the whole refresh over
    a renamed tab is a worse outcome than a fuzzy match."""
    path = workbook(tmp_path, RENT_ROWS, sheet_name="Table3a")
    assert parse.parse_workbook(path, monthly_spec())


def test_a_genuinely_missing_sheet_is_an_error(tmp_path):
    path = workbook(tmp_path, RENT_ROWS, sheet_name="Notes")
    with pytest.raises(parse.ParseError, match="no sheet named"):
        parse.parse_workbook(path, monthly_spec(sheet="Table 9"))


def test_a_wide_annual_release_reads_every_year_column(tmp_path):
    """The affordability release is one column per year rather than one row
    per period."""
    rows = [
        ("Local authority code", "Name", "2019", "2020", "2021"),
        ("E07000209", "Guildford", 12.1, 12.8, 13.4),
        ("E09000007", "Camden", 15.0, 15.9, ":"),
    ]
    spec = Dataset(
        id="affordability", title="Affordability", publisher="ONS",
        licence="OGL v3", url="https://example.invalid/a.xls",
        page="https://example.invalid", cadence="annual", sheet="5c",
        header_contains="code",
        columns=[Column("affordability_ratio", "median", lo=1.5, hi=40.0)],
        extra={"wide_years": "true"},
    )
    got = parse.parse_workbook(workbook(tmp_path, rows, sheet_name="5c"), spec)
    assert ("affordability_ratio", "E07000209", "2020", 12.8) in got
    assert ("affordability_ratio", "E09000007", "2021", 0.0) not in got
    assert len([o for o in got if o[1] == "E09000007"]) == 2, "suppressed year dropped"


def test_a_scale_is_applied_to_the_published_figure(tmp_path):
    """ASHE publishes weekly pay; the catalogue's unit is £/yr."""
    rows = [
        ("Area code", "Date", "Median weekly pay"),
        ("E07000209", "2024", 780.0),
    ]
    spec = monthly_spec(
        cadence="annual", period_column=None, period="2024",
        columns=[Column("earnings_median", "median", scale=52.0,
                        lo=12_000, hi=120_000)])
    got = parse.parse_workbook(workbook(tmp_path, rows), spec)
    assert got == [("earnings_median", "E07000209", "2024", 40560.0)]


# --------------------------------------------------------------------------
# The job, end to end, without a network
# --------------------------------------------------------------------------
def test_the_job_writes_a_store_file_with_its_provenance(tmp_path):
    path = workbook(tmp_path, RENT_ROWS)
    store = tmp_path / "store"
    body = job.refresh(monthly_spec(), source=path, store=store)

    written = json.loads((store / "private_rents.json").read_text())
    assert written["values"]["rental_median"]["E07000209"]["2024-07"] == 1435.0
    assert written["latest_period"] == "2024-07"
    assert written["publisher"] == "ONS" and written["licence"] == "OGL v3"
    assert written["retrieved"].endswith("Z")
    assert body["observations"] == written["observations"]


def test_a_failed_refresh_leaves_the_previous_data_alone(tmp_path):
    """One release moving its URL must not take the others with it, and a
    stale figure carrying its date beats an empty catalogue."""
    store = tmp_path / "store"
    job.refresh(monthly_spec(), source=workbook(tmp_path, RENT_ROWS), store=store)
    before = (store / "private_rents.json").read_text()

    broken = tmp_path / "broken.xlsx"
    broken.write_bytes(b"not a spreadsheet at all")
    with pytest.raises(Exception):
        job.refresh(monthly_spec(), source=broken, store=store)

    assert (store / "private_rents.json").read_text() == before


def test_the_job_leaves_no_scratch_files_behind(tmp_path):
    store = tmp_path / "store"
    job.refresh(monthly_spec(), source=workbook(tmp_path, RENT_ROWS), store=store)
    assert [p.name for p in store.iterdir()] == ["private_rents.json"]


def test_html_served_instead_of_a_spreadsheet_is_recognised():
    """ONS answers a moved URL with an HTML page and a 200 more often than it
    should. Parsing that would fail confusingly several steps later."""
    import requests

    class FakeResponse:
        ok = True
        status_code = 200
        content = b"<!DOCTYPE html><html><head><title>Page not found"

    original = requests.get
    requests.get = lambda *a, **k: FakeResponse()
    try:
        with pytest.raises(job.FetchError, match="HTML"):
            job.fetch("https://example.invalid/moved.xlsx")
    finally:
        requests.get = original


# --------------------------------------------------------------------------
# Serving what was stored
# --------------------------------------------------------------------------
@pytest.fixture
def store(tmp_path):
    import ons_store

    path = tmp_path / "store"
    job.refresh(monthly_spec(), source=workbook(tmp_path, RENT_ROWS), store=path)
    ons_store.reset_cache()
    yield path
    ons_store.reset_cache()


def test_a_stored_monthly_series_lands_on_the_right_months(store):
    import ons_store

    got = ons_store.series("rental_median", "E07000209",
                           ["2024-05", "2024-06", "2024-07"], store=store)
    assert [p["value"] for p in got] == [None, 1420.0, 1435.0]
    assert got[0]["valid_fraction"] == 0.0
    assert not any(p["interpolated"] for p in got if p["value"] is not None)


def test_months_before_the_first_publication_are_gaps_not_backfill(store):
    """"We do not know what the rent was in 2011" and "the rent in 2011 was
    the 2024 rent" are different claims."""
    import ons_store

    got = ons_store.series("rental_median", "E07000209",
                           ["2011-01", "2015-06"], store=store)
    assert [p["value"] for p in got] == [None, None]


def test_an_annual_figure_is_carried_forward_and_flagged(tmp_path):
    """A census figure is a real observation of 2021 held across the timeline.
    The flag is what stops a chart implying it was measured monthly."""
    import ons_store

    rows = [("Area code", "Median age"), ("E07000209", 41.2)]
    spec = monthly_spec(id="census_2021", cadence="periodic", period="2021",
                        period_column=None,
                        columns=[Column("age_median", "median age", lo=20, hi=60)])
    path = tmp_path / "store"
    job.refresh(spec, source=workbook(tmp_path, rows), store=path)
    ons_store.reset_cache()

    got = ons_store.series("age_median", "E07000209",
                           ["2020-06", "2021-03", "2024-09"], store=path)
    assert got[0]["value"] is None, "not carried backwards before publication"
    assert got[1]["value"] == 41.2 and got[1]["interpolated"]
    assert got[2]["value"] == 41.2 and got[2]["interpolated"]
    ons_store.reset_cache()


def test_an_area_with_nothing_published_raises_rather_than_inventing(store):
    import ons_store

    with pytest.raises(ons_store.OnsStoreError):
        ons_store.series("rental_median", "E06000999", ["2024-07"], store=store)


def test_an_empty_store_registers_nothing(tmp_path):
    """Before the job has ever run there is no data, and those factors must
    keep saying "generated" rather than promising a number."""
    import ons_store

    ons_store.reset_cache()
    assert ons_store.available_factors(store=tmp_path / "nothing") == []
    ons_store.reset_cache()


def test_a_corrupt_store_file_costs_its_factors_not_the_process(tmp_path):
    import ons_store

    path = tmp_path / "store"
    path.mkdir()
    (path / "private_rents.json").write_text("{ truncated")
    ons_store.reset_cache()
    assert ons_store.available_factors(store=path) == []
    ons_store.reset_cache()


def test_the_stored_factors_all_exist_in_the_catalogue():
    """A dataset spec naming a factor the catalogue does not have would ingest
    happily and serve nothing."""
    import catalog
    from ons.datasets import ALL_FACTORS

    missing = [f for f in ALL_FACTORS if f not in catalog.FACTOR_BY_ID]
    assert not missing, f"ons/datasets.py names unknown factors: {missing}"


def test_every_dataset_declares_a_publisher_licence_and_landing_page():
    """The provenance the UI shows comes from these fields, and a landing page
    is what someone needs when the file URL stops resolving."""
    from ons.datasets import DATASETS

    for dataset in DATASETS:
        assert dataset.publisher and dataset.licence
        assert dataset.page.startswith("https://")
        assert dataset.url.startswith("https://")
        assert dataset.columns, f"{dataset.id} feeds no factors"


# --------------------------------------------------------------------------
# Registration: what the catalogue says once the job has run
# --------------------------------------------------------------------------
def test_stored_factors_register_as_real_with_their_provenance(tmp_path, monkeypatch):
    """The end of the whole chain: job -> store -> registry -> /api/catalog.
    A factor only becomes real once there is something behind it."""
    import catalog
    import ons_store
    import open_data

    path = tmp_path / "store"
    job.refresh(monthly_spec(), source=workbook(tmp_path, RENT_ROWS), store=path)
    monkeypatch.setattr(ons_store, "STORE", path)
    ons_store.reset_cache()

    registry, provenance = {}, {}
    open_data.install(registry, provenance)
    try:
        assert "rental_median" in registry
        prov = provenance["rental_median"]
        assert prov["status"] == "written"
        assert "local authority" in prov["note"]
        assert "stored release" in prov["endpoint"]
        assert catalog.FACTOR_BY_ID["rental_median"]["unit"] == "£/month"

        # And the two derived factors that come with it.
        assert "rental_growth_yoy" in registry
        assert "gross_yield" in registry
    finally:
        ons_store.reset_cache()


def test_year_on_year_growth_needs_a_year_of_history(tmp_path, monkeypatch):
    """Without an anniversary to compare against, the honest answer is a gap.
    An unanchored percentage is worse than no percentage."""
    import ons_store
    import open_data

    rows = [("Area code", "Date", "Average rent (£)")] + [
        ("E07000209", f"2023-{m:02d}", 1400.0) for m in range(1, 13)
    ] + [("E07000209", "2024-01", 1470.0)]
    path = tmp_path / "store"
    job.refresh(monthly_spec(), source=workbook(tmp_path, rows), store=path)
    monkeypatch.setattr(ons_store, "STORE", path)
    ons_store.reset_cache()

    monkeypatch.setattr(open_data, "locate",
                        lambda g: {"admin_district_code": "E07000209"})
    try:
        got = open_data.rental_growth_series({}, ["2023-06", "2024-01"], 10.0)
        assert got[0]["value"] is None, "no anniversary to compare against"
        assert got[1]["value"] == pytest.approx(5.0)     # 1400 -> 1470
    finally:
        ons_store.reset_cache()


def test_gross_yield_combines_two_sources_and_gaps_when_either_is_missing(
        tmp_path, monkeypatch):
    """Nobody publishes yield. It exists because rents and sale prices are
    both already in the process."""
    import ons_store
    import open_data

    path = tmp_path / "store"
    job.refresh(monthly_spec(), source=workbook(tmp_path, RENT_ROWS), store=path)
    monkeypatch.setattr(ons_store, "STORE", path)
    ons_store.reset_cache()

    monkeypatch.setattr(open_data, "locate",
                        lambda g: {"admin_district_code": "E07000209"})
    monkeypatch.setattr(open_data, "ppd_group", lambda g, steps, a: {
        "median_sale_price": [
            {"t": "2024-06", "value": 480_000.0},
            {"t": "2024-07", "value": None},           # a month with no sales
        ]})
    try:
        got = open_data.gross_yield_series({}, ["2024-06", "2024-07"], 10.0)
        # 1420 x 12 / 480,000 = 3.55%
        assert got[0]["value"] == pytest.approx(3.55, abs=0.01)
        assert got[1]["value"] is None, "no price means no yield, not a zero"
    finally:
        ons_store.reset_cache()
