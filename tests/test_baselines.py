"""Comparison against England.

The feature is "is this site high or low", and the way it goes wrong is not a
crash. It is a percentile with a real denominator and an invented numerator —
a demo value ranked against a sampled national distribution — which would be
the most convincing wrong number this codebase could produce, because every
part of it looks sourced.

So most of what is tested here is refusal.
"""

import json

import pytest

import baselines


@pytest.fixture(autouse=True)
def _fresh():
    baselines.clear_cache()
    yield
    baselines.clear_cache()


def store(values, factor="crime_density"):
    ordered = sorted(float(v) for v in values)
    return {
        "built": "2026-08-09",
        "method": "test",
        "factors": {factor: {
            "samples": ordered,
            "p10": ordered[int(0.1 * (len(ordered) - 1))],
            "p50": ordered[int(0.5 * (len(ordered) - 1))],
            "p90": ordered[int(0.9 * (len(ordered) - 1))],
            "basis": "sampled",
        }},
    }


# ---------------------------------------------------------------------------
# Placing a value
# ---------------------------------------------------------------------------
def test_a_high_value_reads_as_high():
    s = store(range(100))
    out = baselines.compare("crime_density", 95, s)
    assert out["percentile"] >= 90
    assert "9 in 10" in out["phrase"]


def test_a_typical_value_reads_as_typical():
    out = baselines.compare("crime_density", 50, store(range(100)))
    assert 40 < out["percentile"] <= 60
    assert "about average" in out["phrase"]


def test_a_low_value_reads_as_low():
    out = baselines.compare("crime_density", 3, store(range(100)))
    assert out["percentile"] <= 10
    assert "lower than 9 in 10" in out["phrase"]


def test_a_country_of_zeros_does_not_report_a_zero_as_extreme():
    """Crime density is zero across most of England. Ranking a zero against
    eighty other zeros must not come out as 0th or 100th percentile — both
    would be a confident statement about a tie."""
    s = store([0] * 80 + list(range(1, 21)))
    out = baselines.compare("crime_density", 0, s)
    assert 20 <= out["percentile"] <= 60, out["percentile"]


# ---------------------------------------------------------------------------
# Refusals — the part that matters
# ---------------------------------------------------------------------------
def test_a_factor_with_no_baseline_gets_no_comparison():
    assert baselines.compare("ndvi", 0.4, store(range(100))) is None


def test_a_thin_sample_is_not_quoted():
    """Twelve points is not England. A percentile from it is noise wearing a
    number, and the UI would render it identically to a good one."""
    assert baselines.compare("crime_density", 5, store(range(12))) is None


def test_a_gap_gets_no_comparison():
    assert baselines.compare("crime_density", None, store(range(100))) is None


def test_a_categorical_value_gets_no_comparison():
    """"Grassland" has no percentile, and coercing it would invent an
    ordering that the class codes do not have."""
    assert baselines.compare("crime_density", "Grassland", store(range(100))) is None


def test_a_missing_store_is_not_an_error(tmp_path):
    """The normal state on a fresh clone. The app works without comparisons,
    it just says less."""
    data = baselines.load(tmp_path / "nothing.json")
    assert data["factors"] == {}
    assert baselines.compare("crime_density", 5, data) is None


def test_a_corrupt_store_is_not_an_error(tmp_path):
    bad = tmp_path / "baselines.json"
    bad.write_text("{not json")
    assert baselines.load(bad)["factors"] == {}


# ---------------------------------------------------------------------------
# What travels with the number
# ---------------------------------------------------------------------------
def test_the_sample_size_and_date_travel_with_the_percentile():
    """A percentile from 60 points and one from 6,000 are different claims,
    and the difference has to be visible to whoever reads it."""
    out = baselines.compare("crime_density", 50, store(range(100)))
    assert out["n"] == 100
    assert out["built"] == "2026-08-09"
    assert out["basis"] == "sampled"


def test_the_summary_lists_only_usable_factors(tmp_path, monkeypatch):
    s = store(range(100))
    s["factors"]["thin_one"] = {"samples": [1.0, 2.0], "basis": "sampled"}
    path = tmp_path / "b.json"
    path.write_text(json.dumps(s))
    monkeypatch.setattr(baselines, "BASELINE_FILE", path)
    baselines.clear_cache()

    summary = baselines.summary()
    assert summary["factors"] == ["crime_density"]
    assert "thin_one" not in summary["factors"]


# ---------------------------------------------------------------------------
# The route-level guard: a demo value is never ranked
# ---------------------------------------------------------------------------
def test_a_generated_series_is_never_compared():
    """The failure this whole design is arranged around. A generated value
    ranked against a real national distribution produces a percentile whose
    denominator is sourced and whose numerator is invented."""
    import routes_catalog

    generated = {"source": "generated",
                 "points": [{"t": "2026-05", "value": 230.0}]}
    assert routes_catalog._baseline_for("crime_density", generated) is None


def test_a_real_series_is_compared_when_a_baseline_exists(monkeypatch, tmp_path):
    import routes_catalog

    path = tmp_path / "b.json"
    path.write_text(json.dumps(store(range(100))))
    monkeypatch.setattr(baselines, "BASELINE_FILE", path)
    baselines.clear_cache()

    real = {"source": "open-data",
            "points": [{"t": "2026-05", "value": 95.0}]}
    out = routes_catalog._baseline_for("crime_density", real)
    assert out and out["percentile"] >= 90


def test_the_latest_real_point_is_the_one_compared(monkeypatch, tmp_path):
    """Trailing gaps are normal — police.uk publishes in arrears — and
    comparing a gap would silently drop the whole comparison."""
    import routes_catalog

    path = tmp_path / "b.json"
    path.write_text(json.dumps(store(range(100))))
    monkeypatch.setattr(baselines, "BASELINE_FILE", path)
    baselines.clear_cache()

    real = {"source": "open-data", "points": [
        {"t": "2026-03", "value": 95.0},
        {"t": "2026-04", "value": None},
        {"t": "2026-05", "value": None},
    ]}
    out = routes_catalog._baseline_for("crime_density", real)
    assert out and out["percentile"] >= 90
