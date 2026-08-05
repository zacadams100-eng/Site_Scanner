"""
The insight engine.

An application that writes confident English sentences about a place is one
bad guard away from being an application that lies about a place. Most of what
is tested here is therefore what the engine *refuses* to say: no claims from
generated data without saying so, no trends through carried-forward values, no
narration of noise.
"""

import math

import pytest

import insights


def series(values, *, factor_id="ndvi", unit="index", source="earth-engine",
           cadence="monthly", start=(2015, 1), name="NDVI",
           interpolated=False):
    """A series in the shape `/api/series` returns."""
    points, year, month = [], start[0], start[1]
    for v in values:
        points.append({"t": f"{year:04d}-{month:02d}", "value": v,
                       "valid_fraction": 0.0 if v is None else 1.0,
                       "interpolated": interpolated and v is not None})
        month += 1
        if month > 12:
            month, year = 1, year + 1
    return {"factor_id": factor_id, "unit": unit, "source": source,
            "cadence": cadence, "points": points, "meta": {"name": name}}


def kinds(found):
    return {f["kind"] for f in found}


def one(found, kind):
    matches = [f for f in found if f["kind"] == kind]
    assert matches, f"no {kind} insight in {[f['kind'] for f in found]}"
    return matches[0]


# --------------------------------------------------------------------------
# The three rules that keep it honest
# --------------------------------------------------------------------------
def test_generated_data_says_so_in_the_sentence_itself():
    """Not in a tooltip, not in a sibling field — in the text. A caveat kept
    somewhere else is a caveat some future layout drops."""
    rising = [0.3 + i * 0.004 for i in range(60)]
    found = insights.for_series(series(rising, source="generated"))
    assert found
    for f in found:
        assert "demo data" in f["text"], f"unlabelled claim: {f['text']}"


def test_real_data_carries_no_caveat():
    rising = [0.3 + i * 0.004 for i in range(60)]
    found = insights.for_series(series(rising, source="earth-engine"))
    assert found and all("demo data" not in f["text"] for f in found)


def test_carried_forward_values_never_produce_a_trend():
    """A census figure held across 144 months is a perfectly flat, perfectly
    significant series. Analysing it would invent a finding from an artefact
    of how it was stored."""
    held = series([41.2] * 144, unit="years", name="Median age",
                  interpolated=True)
    found = insights.for_series(held)
    assert "trend" not in kinds(found)
    assert "step" not in kinds(found)


def test_an_annual_figure_stepping_once_a_year_is_not_a_step_change():
    """Interpolated points between the real ones would otherwise make every
    January look like a change point."""
    values, points = [], []
    for year, level in enumerate([10.0, 11.0, 12.0, 13.0, 14.0]):
        values.extend([level] * 12)
    s = series(values, unit="%", name="Affordability")
    for i, p in enumerate(s["points"]):
        p["interpolated"] = i % 12 != 0        # only January is observed
    found = insights.for_series(s)
    assert "step" not in kinds(found)


def test_a_short_series_produces_nothing():
    """Fewer than a year of observations is not enough for any of this."""
    assert insights.for_series(series([0.4, 0.5, 0.6])) == []


def test_a_series_of_gaps_produces_nothing_but_a_coverage_note():
    mostly_missing = [0.4 if i % 5 == 0 else None for i in range(60)]
    found = insights.for_series(series(mostly_missing))
    assert kinds(found) <= {"coverage"}


# --------------------------------------------------------------------------
# Trend
# --------------------------------------------------------------------------
def test_a_clear_rise_is_reported_with_its_size_and_dates():
    rising = [0.30 + i * 0.004 for i in range(60)]
    found = one(insights.for_series(series(rising)), "trend")
    assert "rose" in found["text"]
    assert "2015-01" in found["text"] and "2019-12" in found["text"]
    assert found["pct_change"] == pytest.approx(78.7, rel=0.02)
    assert "about" in found["text"], "trend endpoints are fitted, not observed"
    assert found["r2"] > 0.99


def test_a_clear_fall_is_reported_as_a_fall():
    falling = [0.9 - i * 0.005 for i in range(60)]
    found = one(insights.for_series(series(falling)), "trend")
    assert "fell" in found["text"]
    assert found["slope_per_step"] < 0


def test_noise_does_not_get_narrated_as_a_trend():
    """The guard that matters most. Any 60-point random series has a non-zero
    slope; without a significance test every factor in every report would get
    a confident sentence about a trend that is not there."""
    import random

    rng = random.Random(20240816)
    narrated = 0
    for _ in range(60):
        noise = [0.5 + rng.gauss(0, 0.1) for _ in range(60)]
        if "trend" in kinds(insights.for_series(series(noise))):
            narrated += 1
    # A 5% test on 60 pure-noise series should fire about three times.
    assert narrated <= 8, f"narrated {narrated}/60 noise series as trends"


def test_a_scattered_trend_ranks_below_a_clean_one_of_the_same_slope():
    """Significance is not the same as being worth reading."""
    import random

    rng = random.Random(7)
    slope = [0.3 + i * 0.004 for i in range(120)]
    noisy = [v + rng.gauss(0, 0.25) for v in slope]

    clean_t = one(insights.for_series(series(slope)), "trend")
    noisy_t = one(insights.for_series(series(noisy)), "trend")
    assert clean_t["notability"] > noisy_t["notability"]


# --------------------------------------------------------------------------
# Seasonal anomaly
# --------------------------------------------------------------------------
def test_a_hot_july_is_measured_against_other_julys_not_against_june():
    """Comparing a month to the one before it would call every summer an
    anomaly."""
    # Six years of a clean seasonal cycle, with a little year-to-year
    # variation so each calendar month has a spread to be measured against.
    rng = __import__("random").Random(3)
    values = []
    for year in range(6):
        for month in range(1, 13):
            seasonal = 10 * math.sin((month - 3) / 12 * 2 * math.pi)
            values.append(20 + seasonal + rng.gauss(0, 0.4))
    # Then make the last month of all far hotter than that month has ever been.
    values[-1] += 12

    s = series(values, unit="°C", name="Land surface temp")
    found = one(insights.for_series(s), "anomaly")
    assert found["z"] > 2
    assert "highest" in found["text"]


def test_an_ordinary_month_produces_no_anomaly():
    values = [20 + 10 * math.sin((m % 12 - 3) / 12 * 2 * math.pi)
              for m in range(72)]
    assert "anomaly" not in kinds(insights.for_series(series(values, unit="°C")))


def test_an_anomaly_needs_three_prior_years_of_that_month():
    """With two Julys there is no standard deviation worth dividing by."""
    values = [20.0] * 20 + [60.0]
    assert "anomaly" not in kinds(insights.for_series(series(values, unit="°C")))


# --------------------------------------------------------------------------
# Step change
# --------------------------------------------------------------------------
def test_a_level_shift_is_found_and_dated_roughly():
    values = [10.0] * 40 + [18.0] * 40
    found = one(insights.for_series(series(values, unit="%")), "step")
    # "Roughly": the split is found from the data, so the reported levels are
    # the means either side of wherever it landed, not the planted values.
    assert found["before"] == pytest.approx(10.0, rel=0.05)
    assert found["after"] == pytest.approx(18.0, rel=0.05)
    assert found["at"].startswith("2018"), found["at"]
    assert "shifted up" in found["text"]


def test_a_steady_series_has_no_step():
    values = [10.0 + i * 0.01 for i in range(80)]
    assert "step" not in kinds(insights.for_series(series(values, unit="%")))


# --------------------------------------------------------------------------
# Static designations
# --------------------------------------------------------------------------
def test_a_designation_is_stated_rather_than_analysed():
    """A green-belt percentage is a fact about the site, not a time series."""
    s = series([64.6] * 132, factor_id="green_belt_pct", unit="%",
               name="Green Belt", source="open-data", interpolated=True)
    found = insights.for_series(s)
    assert kinds(found) == {"static"}
    assert one(found, "static")["text"] == "Green Belt: 64.6%."


def test_a_designation_covering_none_of_the_site_is_not_worth_a_sentence():
    """"0% of this site is a national park" is true of almost everywhere."""
    s = series([0.0] * 60, factor_id="national_park_pct", unit="%",
               name="National Park", source="open-data", interpolated=True)
    assert insights.for_series(s) == []


# --------------------------------------------------------------------------
# Ranking a whole report
# --------------------------------------------------------------------------
def test_real_findings_outrank_generated_ones():
    """Demo data should not lead a report that also contains something real.
    Still listed, still labelled, just not first."""
    report = {"series": {
        "fake": series([1 + i * 0.1 for i in range(80)], unit="%",
                       source="generated", name="Fake"),
        "real": series([5 + i * 0.01 for i in range(80)], unit="%",
                       source="open-data", name="Real"),
    }}
    out = insights.summarise(report)
    assert out["insights"][0]["source"] == "open-data"
    assert out["counts"]["from_real_data"] >= 1
    assert out["counts"]["from_generated_data"] >= 1


def test_the_summary_reports_how_many_it_held_back():
    report = {"series": {
        f"f{i}": series([1 + j * 0.1 for j in range(80)], unit="%",
                        source="open-data", name=f"F{i}")
        for i in range(6)
    }}
    out = insights.summarise(report, limit=3)
    assert out["counts"]["shown"] == 3
    assert out["counts"]["total"] > 3
    assert len(out["insights"]) == 3


def test_one_bad_series_does_not_take_down_the_report():
    """An insight is a nicety. The report is what the user paid for."""
    report = {"series": {
        "broken": {"points": "not a list at all", "unit": "%"},
        "fine": series([1 + i * 0.1 for i in range(80)], unit="%",
                       source="open-data", name="Fine"),
    }}
    out = insights.summarise(report)
    assert out["insights"], "a malformed series suppressed the whole summary"


def test_the_api_returns_insights_alongside_the_series():
    from fastapi.testclient import TestClient

    import mock_ee_backend

    client = TestClient(mock_ee_backend.app)
    body = client.post("/api/series", json={
        "geometry": {"type": "Polygon", "coordinates": [[
            [-0.58, 51.23], [-0.56, 51.23], [-0.56, 51.245],
            [-0.58, 51.245], [-0.58, 51.23]]]},
        "factor_ids": ["ndvi", "avg_sale_price"],
        "start": "2015-01", "end": "2025-12"}).json()

    assert "insights" in body and "counts" in body
    for insight in body["insights"]:
        assert insight["text"] and insight["factor"]
        assert 0.0 <= insight["notability"] <= 1.0
        if insight["source"] == "generated":
            assert "demo data" in insight["text"]


def test_a_trend_is_quoted_from_its_fitted_line_not_its_end_points():
    """On a seasonal series the first and last observations are a March and a
    November. Quoting them produced "rose 122%" for a temperature series with
    no trend in it at all."""
    values = [20 + 10 * math.sin((m % 12 - 3) / 12 * 2 * math.pi)
              for m in range(120)]
    found = insights.trend(series(values, unit="°C", name="Temp"))
    if found:                          # a flat seasonal series may have none
        assert abs(found["pct_change"] or 0) < 10, found["text"]


def test_a_weak_trend_says_the_noise_is_bigger_than_it_is():
    """A significant slope is not a dominant one. With 120 points a trend
    explaining 4% of the variance still clears the t-test."""
    import random

    rng = random.Random(11)
    weak = [10 + i * 0.01 + rng.gauss(0, 1.5) for i in range(160)]
    found = insights.trend(series(weak, unit="%"))
    if found:
        assert found["r2"] < 0.25
        assert "variation is larger than the trend" in found["text"]
