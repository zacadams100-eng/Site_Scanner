"""
Which ONS spreadsheets we ingest, and how to read each one.

`open_data.py` explains why this exists: ONS publishes private rents, earnings,
affordability and the census as **spreadsheets on a release page**, not as Beta
API datasets with stable per-area endpoints. A live API client cannot reach
them. The only honest route is to download each release on a schedule, parse
it, and serve from what we stored — which is the ingest tier again, exactly as
`docs/OPEN-DATA.md` predicted.

## Reading a government spreadsheet

Every one of these has a different shape, and their shapes change between
releases. Nothing here assumes a fixed cell address. A spec says what to look
for, not where it is:

* **The header row is found, not numbered.** `header_contains` names a label
  that must appear in it. A release that adds two rows of notes at the top
  moves every cell reference and breaks nothing here.
* **The area column is found by its values**, not its heading — ONS calls it
  "Area code", "LAD24CD", "Local authority code" and "ladcode23" across these
  four files, but every one of them contains strings like `E07000209`. That is
  a far more stable signal than a caption.
* **Value columns are matched on a label fragment**, case-insensitively, with
  the fragment chosen to survive the year moving through the title.

When a spec stops matching, the job fails loudly for that dataset and leaves
the previous data in place. A stale number that is labelled with its date is
much better than a wrong one, and far better than an empty catalogue.

## Honesty about the URLs

**None of these URLs has been fetched.** The environment this was written in
blocks all outbound HTTPS except a short allowlist, so every one is written
from ONS's published URL conventions and is unverified. ONS also rotates
`/current/` links on each release. `python3 -m ons.job --check` resolves every
URL and reports what it finds without parsing anything; run it first, on a
machine with open egress, and expect to fix some of them. See BLOCKERS.md.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Local authority districts in England: E06 unitary, E07 non-metropolitan
# district, E08 metropolitan borough, E09 London borough. E10 is a county and
# E12 a region — kept out, because a factor reported for a whole county is
# not what someone drawing a field expects.
LAD_PREFIXES = ("E06", "E07", "E08", "E09")


@dataclass
class Column:
    """One column of a sheet, and the factor it feeds."""
    factor: str
    #: Case-insensitive fragment that must appear in the column's header.
    header_contains: str
    #: Multiply the published figure by this. ONS publishes weekly rents and
    #: percentages-as-fractions in places; the catalogue wants monthly pounds
    #: and whole percent.
    scale: float = 1.0
    #: Sanity bounds. A value outside these is dropped rather than stored —
    #: it means the column matched the wrong header, which is the failure mode
    #: a fragment match has.
    lo: Optional[float] = None
    hi: Optional[float] = None


@dataclass
class Dataset:
    id: str
    title: str
    publisher: str
    licence: str
    url: str
    #: Landing page, for a human to check when the file URL stops resolving.
    page: str
    #: 'monthly' | 'annual' | 'periodic'
    cadence: str
    columns: List[Column]
    #: Sheet to read. A name if it is stable, otherwise the index.
    sheet: Optional[str] = None
    sheet_index: int = 0
    #: A label that must appear in the header row, used to find it.
    header_contains: str = "code"
    #: For a wide file, the header fragment of the column holding the period
    #: ("2024-07"). None means the file is one period per release and the
    #: period comes from `period`.
    period_column: Optional[str] = None
    #: Fixed period for a one-shot release like the census.
    period: Optional[str] = None
    notes: str = ""
    extra: Dict[str, str] = field(default_factory=dict)

    @property
    def factors(self) -> List[str]:
        return [c.factor for c in self.columns]


DATASETS: List[Dataset] = [
    # ------------------------------------------------------------------
    # Private rents — monthly, by local authority.
    # ------------------------------------------------------------------
    Dataset(
        id="private_rents",
        title="Price Index of Private Rents, UK: monthly price statistics",
        publisher="Office for National Statistics",
        licence="OGL v3",
        url="https://www.ons.gov.uk/file?uri=/economy/inflationandpriceindices/"
            "datasets/priceindexofprivaterentsukmonthlypricestatistics/current/"
            "pipruk.xlsx",
        page="https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/"
             "priceindexofprivaterentsukmonthlypricestatistics",
        cadence="monthly",
        sheet="Table 3",
        header_contains="code",
        period_column="date",
        columns=[
            Column("rental_median", "average rent", lo=200, hi=6000),
        ],
        notes="Replaced the Index of Private Housing Rental Prices in 2024; the "
              "series before that date comes from the older release and is not "
              "ingested here.",
    ),

    # ------------------------------------------------------------------
    # Affordability — annual, by local authority.
    # ------------------------------------------------------------------
    Dataset(
        id="affordability",
        title="Ratio of house price to workplace-based earnings",
        publisher="Office for National Statistics",
        licence="OGL v3",
        url="https://www.ons.gov.uk/file?uri=/peoplepopulationandcommunity/"
            "housing/datasets/ratioofhousepricetoworkplacebasedearningslower"
            "quartileandmedian/current/ratioofhousepricetoworkplacebasedearnings.xls",
        page="https://www.ons.gov.uk/peoplepopulationandcommunity/housing/"
             "datasets/ratioofhousepricetoworkplacebasedearningslowerquartile"
             "andmedian",
        cadence="annual",
        sheet="5c",
        header_contains="code",
        period_column=None,
        columns=[
            Column("affordability_ratio", "median", lo=1.5, hi=40.0),
        ],
        notes="Wide format: one column per year. The parser reads every "
              "four-digit year column it finds rather than a named one.",
        extra={"wide_years": "true"},
    ),

    # ------------------------------------------------------------------
    # Earnings — annual, by local authority of workplace.
    # ------------------------------------------------------------------
    Dataset(
        id="earnings",
        title="Annual Survey of Hours and Earnings, place of work by local authority",
        publisher="Office for National Statistics",
        licence="OGL v3",
        url="https://www.ons.gov.uk/file?uri=/employmentandlabourmarket/"
            "peopleinwork/earningsandworkinghours/datasets/"
            "placeofworkbylocalauthorityashetable7/current/table72024.zip",
        page="https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/"
             "earningsandworkinghours/datasets/placeofworkbylocalauthorityashetable7",
        cadence="annual",
        sheet=None,
        sheet_index=0,
        header_contains="code",
        columns=[
            # Published as gross weekly pay for full-time employees.
            Column("earnings_median", "median", scale=52.0, lo=12_000, hi=120_000),
        ],
        notes="ASHE ships a zip of workbooks. The job takes the first .xlsx "
              "inside it whose name mentions annual pay.",
    ),

    # ------------------------------------------------------------------
    # Census 2021 — one release, nine factors, by local authority.
    # ------------------------------------------------------------------
    Dataset(
        id="census_2021",
        title="Census 2021, local authority summary",
        publisher="Office for National Statistics",
        licence="OGL v3",
        url="https://www.ons.gov.uk/file?uri=/peoplepopulationandcommunity/"
            "populationandmigration/populationestimates/datasets/"
            "census2021firstresultsenglandwales/census2021firstresults"
            "englandwalesentiredataset/census2021firstresultsenglandwales.xlsx",
        page="https://www.ons.gov.uk/peoplepopulationandcommunity/"
             "populationandmigration/populationestimates/datasets/"
             "census2021firstresultsenglandwales",
        cadence="periodic",
        sheet=None,
        sheet_index=0,
        header_contains="code",
        period="2021",
        columns=[
            Column("households", "household", lo=1, hi=20000),
            Column("age_median", "median age", lo=20, hi=60),
            Column("age_under16_pct", "aged 15 years and under", lo=0, hi=40),
            Column("age_over65_pct", "aged 65 years and over", lo=0, hi=50),
        ],
        notes="The first-results release carries population, households and age "
              "structure. Tenure and qualifications are separate topic "
              "summaries — see BLOCKERS.md; their URLs were not confirmable "
              "from here and they are deliberately not guessed at.",
    ),

    # ------------------------------------------------------------------
    # Deprivation — MHCLG, not ONS, but the same shape of job.
    # ------------------------------------------------------------------
    Dataset(
        id="imd_2019",
        title="English Indices of Deprivation 2019, local authority summaries",
        publisher="Ministry of Housing, Communities and Local Government",
        licence="OGL v3",
        url="https://assets.publishing.service.gov.uk/media/"
            "5d8e26f6ed915d5570c6cc55/File_10_-_IoD2019_Local_Authority_District_"
            "Summaries__lower-tier__.xlsx",
        page="https://www.gov.uk/government/statistics/"
             "english-indices-of-deprivation-2019",
        cadence="periodic",
        sheet="IMD",
        header_contains="code",
        period="2019",
        columns=[
            Column("imd_score", "average score", lo=0, hi=60),
        ],
        notes="Published by MHCLG rather than ONS. It is here because it is the "
              "same job — a spreadsheet on a release page, keyed by local "
              "authority — and splitting the mechanism by publisher would mean "
              "writing it twice.",
    ),
]

DATASET_BY_ID: Dict[str, Dataset] = {d.id: d for d in DATASETS}

#: Every factor any dataset here can fill.
ALL_FACTORS = sorted({c.factor for d in DATASETS for c in d.columns})
