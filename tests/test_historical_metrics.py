"""
Historical metrics, against the frozen methodology.

`HISTORICAL_EVIDENCE_MODEL.md` defines the method; this file tests the method
rather than the arithmetic. "NDVI produces the expected number" would pass
against a subtly wrong baseline, so most of what follows is adversarial: feed
it December, feed it interpolated years, feed it a zero baseline, feed it two
usable years, and assert it does the awkward thing rather than the convenient
one.

The tests most worth keeping are the ones that catch a *future simplification*:

- `test_he4_seasonal_windows_are_per_metric_and_actually_differ` fails the day
  someone shares one window across families because it is tidier.
- `test_he4_baseline_is_the_first_three_usable_years_not_calendar_years` fails
  the day someone reaches for `years[:3]`.
- `test_he6_two_usable_years_produce_no_change_statistic` fails the day
  incomplete evidence quietly becomes a confident number.
"""

import pytest

from historical import metrics


def series(values_by_period, *, source="earth-engine", unit="index",
           interpolated=(), name="NDVI"):
    """A series in the shape `/api/series` returns.

    `values_by_period` maps 'YYYY-MM' to a value; `interpolated` names the
    periods that were carried forward rather than observed.
    """
    return {
        "unit": unit, "cadence": "monthly", "source": source,
        "meta": {"name": name},
        "provenance": {"source": "Copernicus / ESA",
                       "endpoint": "earthengine.googleapis.com",
                       "status": "verified"},
        "points": [{"t": t, "value": v,
                    "interpolated": t in interpolated}
                   for t, v in sorted(values_by_period.items())],
    }


def growing_year(year, value, months=(4, 5, 6, 7, 8, 9)):
    return {f"{year}-{m:02d}": value for m in months}


def summer_year(year, value, months=(6, 7, 8)):
    return {f"{year}-{m:02d}": value for m in months}


def veg_series(per_year, **kw):
    """One NDVI series from {year: value}."""
    points = {}
    for year, value in per_year.items():
        points.update(growing_year(year, value))
    return series(points, **kw)


# ---------------------------------------------------------------------------
# HE4 — the baseline definition
# ---------------------------------------------------------------------------
def test_he4_baseline_is_the_first_three_usable_years_not_calendar_years():
    """The trap: `years[:3]` on the calendar range builds a baseline partly
    from years with no data.

    Usable years 2011, 2012, 2013, 2015, 2018, 2021 — so the baseline is
    2011–2013 and the recent period is 2015–2021, even though the calendar
    range is 2011–2021 and five of those years are absent.
    """
    m = metrics.change_metric(
        veg_series({2011: 0.50, 2012: 0.52, 2013: 0.48,
                    2015: 0.40, 2018: 0.38, 2021: 0.36}),
        name="Vegetation vigour", family="vegetation", factor="ndvi")

    assert m["baseline_years"] == [2011, 2012, 2013]
    assert m["recent_years"] == [2015, 2018, 2021]
    assert m["baseline"] == pytest.approx(0.50)     # median of .50 .52 .48
    assert m["recent"] == pytest.approx(0.38)       # median of .40 .38 .36


def test_he4_annual_and_period_values_are_medians_not_means():
    """One cloud-contaminated composite should not move a year, and one year
    should not move a fifteen-year baseline."""
    points = {}
    # 2011 has an outlier month; its median must ignore it, its mean would not.
    points.update({f"2011-{m:02d}": 0.50 for m in (4, 5, 6, 7, 8)})
    points["2011-09"] = 0.02
    for year in (2012, 2013, 2014, 2015, 2016):
        points.update(growing_year(year, 0.50))
    m = metrics.change_metric(series(points), name="V", family="vegetation")

    assert m["annual_values"]["2011"] == pytest.approx(0.50)
    assert m["baseline"] == pytest.approx(0.50)


def test_he4_seasonal_windows_are_per_metric_and_actually_differ():
    """Fails the day someone shares one window across families.

    The same December-heavy series must be read differently by each family:
    vegetation ignores winter entirely, LST ignores everything but summer, and
    surface reads all of it.
    """
    assert metrics.SEASONS["vegetation"] == (4, 5, 6, 7, 8, 9)
    assert metrics.SEASONS["lst"] == (6, 7, 8)
    assert metrics.SEASONS["surface"] == tuple(range(1, 13))

    winter_only = series({f"{y}-{m:02d}": 1.0
                          for y in range(2011, 2020) for m in (1, 2, 12)})
    assert metrics.usable_years(winter_only, "vegetation") == {}
    assert metrics.usable_years(winter_only, "lst") == {}
    # Surface reads every month, so the same series is perfectly usable to it.
    assert len(metrics.usable_years(winter_only, "surface")) == 9


def test_he4_december_never_reaches_a_vegetation_metric():
    """A December NDVI is a real observation of not much."""
    points = {}
    for year in range(2011, 2018):
        points.update(growing_year(year, 0.60))
        points[f"{year}-12"] = 0.05          # would drag every year down
    m = metrics.change_metric(series(points), name="V", family="vegetation")
    assert all(v == pytest.approx(0.60) for v in m["annual_values"].values())


def test_he4_lst_requires_all_three_summer_months():
    """The window is three months and the threshold is three observations, so
    a missing July disqualifies the year rather than halving it."""
    points = {}
    for year in range(2011, 2020):
        points.update(summer_year(year, 18.0))
    full = metrics.usable_years(series(points, unit="°C"), "lst")
    assert len(full) == 9

    del points["2015-07"]
    partial = metrics.usable_years(series(points, unit="°C"), "lst")
    assert 2015 not in partial


# ---------------------------------------------------------------------------
# Interpolation
# ---------------------------------------------------------------------------
def test_interpolated_values_can_never_form_a_usable_year():
    """A value carried across a gap reads as a measurement and is not one.

    This also guards against a future change bypassing the exclusion that
    `insights.py` already applies for the same reason.
    """
    points = {}
    for year in (2011, 2013, 2014, 2015, 2016, 2017, 2018):
        points.update(growing_year(year, 0.50))
    carried = growing_year(2012, 0.50)
    points.update(carried)

    m = metrics.change_metric(
        series(points, interpolated=set(carried)),
        name="V", family="vegetation")

    assert "2012" not in m["annual_values"]
    assert 2012 not in m["baseline_years"]
    assert m["baseline_years"] == [2011, 2013, 2014]


def test_a_year_of_purely_interpolated_values_does_not_count_toward_coverage():
    points = {}
    for year in (2011, 2012, 2013):
        points.update(growing_year(year, 0.50))
    carried = growing_year(2014, 0.50)
    points.update(carried)
    cov = metrics.coverage(series(points, interpolated=set(carried)),
                           "vegetation")
    assert cov["years_usable"] == 3
    assert cov["years_total"] == 4
    assert cov["observations_usable"] == 18
    assert cov["observations_possible"] == 24


# ---------------------------------------------------------------------------
# The zero baseline
# ---------------------------------------------------------------------------
def test_a_zero_baseline_produces_an_absolute_change_and_no_percentage():
    """A percentage change from zero is an infinity dressed as a statistic."""
    m = metrics.change_metric(
        veg_series({2011: 0.0, 2012: 0.0, 2013: 0.0,
                    2014: 0.15, 2015: 0.15, 2016: 0.15}),
        name="V", family="vegetation")

    assert m["baseline"] == 0
    assert m["change"] == pytest.approx(0.15)
    assert m["change_type"] == "absolute"
    assert m["change_pct"] is None


def test_a_negative_baseline_uses_its_magnitude_for_the_percentage():
    """NDVI can legitimately be negative over water. Dividing by a signed
    baseline flips the sign of the change and reports a fall as a rise."""
    m = metrics.change_metric(
        veg_series({2011: -0.20, 2012: -0.20, 2013: -0.20,
                    2014: -0.30, 2015: -0.30, 2016: -0.30}),
        name="V", family="vegetation")
    assert m["change"] == pytest.approx(-0.10)
    assert m["change_pct"] == pytest.approx(-50.0)


# ---------------------------------------------------------------------------
# HE5 / HE6 — insufficient evidence
# ---------------------------------------------------------------------------
def test_he6_two_usable_years_produce_no_change_statistic():
    """Incomplete evidence must not quietly become a confident number."""
    m = metrics.change_metric(veg_series({2011: 0.50, 2012: 0.40}),
                              name="V", family="vegetation")
    assert m["baseline"] is None
    assert m["recent"] is None
    assert m["change"] is None
    assert m["meets_minimum_evidence"] is False
    assert "2 usable years" in m["shortfall"]


def test_he5_baseline_and_recent_periods_never_overlap():
    """Six usable years are needed before a change statement exists at all.

    With five, the two three-year periods would share a year and the metric
    would be comparing a period with itself.
    """
    five = metrics.change_metric(
        veg_series({y: 0.5 for y in range(2011, 2016)}),
        name="V", family="vegetation")
    assert five["change"] is None

    six = metrics.change_metric(
        veg_series({y: 0.5 for y in range(2011, 2017)}),
        name="V", family="vegetation")
    assert six["change"] is not None
    assert not set(six["baseline_years"]) & set(six["recent_years"])


def test_he5_sparse_year_coverage_computes_the_change_but_withholds_sufficiency():
    """The figures still exist — the rule simply may not use them.

    Reporting the coverage shortfall alongside the numbers is what lets a user
    see how close it came, rather than meeting a blank panel.
    """
    points = {}
    for year in (2011, 2012, 2013, 2024, 2025, 2026):
        points.update(growing_year(year, 0.50 if year < 2020 else 0.30))
    # Sixteen calendar years, six of them usable: 38% year coverage.
    m = metrics.change_metric(series(points), name="V", family="vegetation")

    assert m["change"] is not None
    assert m["meets_minimum_evidence"] is False
    assert "adequately observed" in m["shortfall"]
    assert m["year_coverage"] < metrics.MIN_YEAR_COVERAGE


def test_he5_dense_coverage_meets_the_minimum():
    m = metrics.change_metric(
        veg_series({y: 0.5 for y in range(2011, 2021)}),
        name="V", family="vegetation")
    assert m["meets_minimum_evidence"] is True
    assert m["shortfall"] == ""
    assert m["year_coverage"] == 1.0


# ---------------------------------------------------------------------------
# HE2 — generated data
# ---------------------------------------------------------------------------
def test_he2_generated_data_produces_no_derived_values_at_all():
    """A fabricated fifteen-year trend is the most convincing wrong thing this
    product could draw, and a label on a chart is not a defence against it."""
    m = metrics.change_metric(
        veg_series({y: 0.5 - 0.02 * i for i, y in enumerate(range(2011, 2021))},
                   source="generated"),
        name="V", family="vegetation")

    assert m["real"] is False
    assert m["baseline"] is None and m["recent"] is None and m["change"] is None
    assert m["annual_values"] == {}
    assert m["meets_minimum_evidence"] is False
    assert "generated demo data" in m["shortfall"]


# ---------------------------------------------------------------------------
# HE3 — coverage
# ---------------------------------------------------------------------------
def test_he3_coverage_reports_observations_and_years_separately():
    """A series excellent at the ends and poor in the middle has high
    observation coverage and mediocre year coverage, and it is the second that
    decides whether a fifteen-year statement is defensible."""
    points = {}
    for year in (2011, 2012, 2013, 2014):
        points.update(growing_year(year, 0.5))
    for year in (2015, 2016, 2017, 2018):
        points.update({f"{year}-06": 0.5})          # one month — not usable
    for year in (2019, 2020, 2021):
        points.update(growing_year(year, 0.5))

    cov = metrics.coverage(series(points), "vegetation")
    assert cov["years_usable"] == 7
    assert cov["years_total"] == 11
    assert cov["year_coverage"] == pytest.approx(0.636, abs=0.001)
    assert cov["observation_coverage"] == 1.0       # every point present
    assert cov["first_year"] == 2011 and cov["last_year"] == 2021


# ---------------------------------------------------------------------------
# HE10 — reproducibility
# ---------------------------------------------------------------------------
def test_he10_every_result_records_the_methodology_and_the_periods_used():
    m = metrics.change_metric(
        veg_series({y: 0.5 for y in range(2011, 2021)}),
        name="Vegetation vigour", family="vegetation", factor="ndvi")

    assert m["method_version"] == metrics.METHOD_VERSION == "hist-1"
    assert m["baseline_years"] and m["recent_years"]
    assert m["observations_usable"] and m["observations_possible"]
    assert m["season"] == [4, 5, 6, 7, 8, 9]
    assert m["factor"] == "ndvi"


def test_he1_provenance_travels_with_the_metric():
    m = metrics.change_metric(
        veg_series({y: 0.5 for y in range(2011, 2021)}),
        name="V", family="vegetation")
    assert m["provenance"]["endpoint"] == "earthengine.googleapis.com"
    assert m["provenance"]["source"] == "Copernicus / ESA"
    assert m["source"] == "earth-engine"


# ---------------------------------------------------------------------------
# HE7 — the metric layer knows nothing about findings
# ---------------------------------------------------------------------------
FINDING_WORDS = ("flag", "clear", "severity", "severe", "risk", "suitab",
                 "investigation", "recommend", "score", "grade", "informational",
                 "not_assessed", "concern", "good", "poor", "safe")


def test_he7_a_metric_never_contains_a_finding():
    """A metric says what happened. A rule says whether it crosses a threshold.

    Scanned across every branch, because the tempting place to add "and this
    one is bad" is the branch someone is debugging at the time.
    """
    cases = [
        veg_series({y: 0.5 for y in range(2011, 2021)}),           # sufficient
        veg_series({2011: 0.5, 2012: 0.4}),                        # too few
        veg_series({y: 0.5 for y in range(2011, 2017)},
                   source="generated"),                            # generated
        veg_series({2011: 0.0, 2012: 0.0, 2013: 0.0,
                    2014: 0.2, 2015: 0.2, 2016: 0.2}),             # zero base
    ]
    for s in cases:
        m = metrics.change_metric(s, name="V", family="vegetation")
        for key, value in m.items():
            for word in FINDING_WORDS:
                assert word not in key.lower(), key
                if isinstance(value, str):
                    assert word not in value.lower(), f"{key}={value}"


def test_he7_the_metric_module_imports_nothing_from_the_finding_engine():
    """Structural, not stylistic. The moment `metrics.py` imports `radar`, the
    two layers can start agreeing with each other by accident rather than by
    construction."""
    import pathlib
    source = (pathlib.Path(metrics.__file__)).read_text()
    for banned in ("import radar", "from radar", "import comparison",
                   "import insights"):
        assert banned not in source, banned


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------
def test_malformed_input_produces_an_empty_metric_rather_than_an_exception():
    for bad in ({}, {"points": None}, {"points": "nonsense"},
                {"points": [{"t": "bad", "value": 1}]},
                {"points": [{"value": 1}]},
                {"points": [None, 3, "x"]}):
        m = metrics.change_metric({**bad, "source": "earth-engine"},
                                  name="V", family="vegetation")
        assert m["change"] is None
        assert m["meets_minimum_evidence"] is False


def test_an_unknown_family_is_a_programming_error_not_a_silent_default():
    """Defaulting to the vegetation window would silently change what an
    unrecognised metric measures."""
    with pytest.raises(KeyError):
        metrics.usable_years(veg_series({2011: 0.5}), "not_a_family")
