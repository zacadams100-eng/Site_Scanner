"""
The historical chain, end to end, over the real HTTP boundary.

`test_historical_rules.py` proves `series → metric → rule → radar` by calling
`radar.assess()` directly. That leaves the last two links of the chain in
`HISTORICAL_EVIDENCE_MODEL.md` unproven together:

    Sentinel-2 → metrics → rules → radar → investigations → the UI payload

This file closes that gap. It drives `POST /api/series` on the real app and
asserts the response a browser actually receives — so the composition in
`routes_catalog` (`historical_view.report` joined to `radar.outcome_for`) is
exercised rather than assumed, and the shape `HistoricalEvidence.tsx` reads is
pinned by a test rather than by a screenshot.

**What is substituted, and what is not.** Only the Earth Engine network call.
`REAL_SERIES` is the registry the real backend installs into at startup
(`api/index.py`, `mock_ee_backend.py`), so installing a fixture there is the
same seam the production code uses — everything downstream of the fetch is the
real path, including provenance labelling, `source` derivation, licensing,
caching, the radar and the historical view.

**The fixture is Sentinel-2 shaped, not convenient.** `ndvi` is
`sentinel2_sr`, which begins 2017-03, so the months before it are gaps and the
production baseline is 2017–2019 against a 2023–2025 recent period — not the
2011 window the step-4 unit tests use. A fixture that quietly supplied 2011
NDVI would prove a path production can never take.
"""

import pytest

import routes_catalog


# The archive Sentinel-2 actually has. Months before this are `None`, which is
# the correct answer and not a gap to paper over (HE3).
S2_START_YEAR, S2_START_MONTH = 2017, 3

#: April–September, the vegetation window frozen in the methodology.
WINDOW = (4, 5, 6, 7, 8, 9)

GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[
        [-0.58, 51.235], [-0.56, 51.235], [-0.56, 51.245],
        [-0.58, 51.245], [-0.58, 51.235],
    ]],
}

RULE = "historical_vegetation_decline"


def s2_ndvi(per_year):
    """A Sentinel-2 NDVI implementation, in the shape `REAL_SERIES` holds.

    Returns one point per requested step. A month outside the archive, or a
    year the scenario does not supply, is `None` — a real gap, carried as a
    gap.
    """
    def fn(geometry, steps, area_ha):
        points = []
        for t in steps:
            year, month = int(t[:4]), int(t[5:7])
            before_archive = (year, month) < (S2_START_YEAR, S2_START_MONTH)
            value = None
            if not before_archive and month in WINDOW:
                value = per_year.get(year)
            # `valid_fraction` is how much of the AOI the composite actually
            # saw, and `annual_rollup` weights by it. A gap is 0.0, matching
            # `ee_series._gap`.
            points.append({"t": t, "value": value, "interpolated": False,
                           "valid_fraction": 0.0 if value is None else 0.95})
        return points
    return fn


def flat(value, years):
    return {y: value for y in years}


def declining(baseline, recent):
    """Baseline value across 2017–2019, recent across 2023–2025, interpolated
    between so the middle years are usable but uninteresting."""
    per_year = {}
    for y in range(2017, 2026):
        if y <= 2019:
            per_year[y] = baseline
        elif y >= 2023:
            per_year[y] = recent
        else:
            per_year[y] = (baseline + recent) / 2
    return per_year


@pytest.fixture
def live_ndvi(monkeypatch):
    """Install a fixture NDVI as a *real* Earth Engine factor.

    The endpoint matters: `_series_for` derives `source` from it, and only
    `earth-engine` or `open-data` may produce a finding at all (EM1–EM3, HE2).
    A fixture registered without a plausible endpoint would be labelled
    `open-data` and the test would prove the wrong provenance.

    The series cache is cleared on the way in and out. Its key is
    (factor, geometry, steps) — identical across every scenario here — so
    without this the second scenario would silently assert against the first
    one's data.
    """
    def install(per_year):
        routes_catalog.SERIES_CACHE.clear()
        monkeypatch.setitem(routes_catalog.REAL_SERIES, "ndvi", s2_ndvi(per_year))
        monkeypatch.setitem(routes_catalog.REAL_SOURCES, "ndvi", {
            "source": "Copernicus / ESA",
            "publisher": "European Space Agency",
            "endpoint": "earthengine.googleapis.com",
            "status": "verified",
        })
    yield install
    routes_catalog.SERIES_CACHE.clear()


def fetch(client, per_year, install):
    install(per_year)
    r = client.post("/api/series", json={
        "geometry": GEOMETRY,
        "factor_ids": ["ndvi"],
    })
    assert r.status_code == 200, r.text
    return r.json()


def entry_for(body, metric_id="vegetation"):
    return next(e for e in body["historical"] if e["id"] == metric_id)


# ---------------------------------------------------------------------------
# The whole chain, on one request
# ---------------------------------------------------------------------------
def test_a_real_decline_travels_the_entire_chain(mock_client, live_ndvi):
    """The deliverable, in one assertion block: what changed, how we know,
    whether the evidence was sufficient, and what it prompts."""
    body = fetch(mock_client, declining(0.61, 0.47), live_ndvi)

    # The series came back real, from the satellite it claims.
    assert body["series"]["ndvi"]["source"] == "earth-engine"
    assert "ndvi" in body["real_factors"]

    entry = entry_for(body)
    metric, finding = entry["metric"], entry["finding"]

    # 1. What changed — a quantified decline against a declared baseline.
    assert metric["change_pct"] == pytest.approx(-22.95, abs=0.1)
    assert metric["baseline"] == pytest.approx(0.61, abs=0.001)
    assert metric["recent"] == pytest.approx(0.47, abs=0.001)
    assert metric["baseline_years"] == [2017, 2018, 2019]
    assert metric["recent_years"] == [2023, 2024, 2025]

    # 2. How we know — reproducible under a named methodology (HE10).
    assert metric["method_version"] == "hist-1"

    # 3. Whether the evidence was sufficient — stated, not implied (HE3), and
    #    as two figures that are not interchangeable. 9 usable years out of 15
    #    calendar years is the honest reading of a Sentinel-2 record that
    #    cannot see 2011–2016 at all: the gap is part of the result, not a
    #    denominator to quietly shrink.
    assert metric["years_usable"] == 9
    assert metric["years_total"] == 15
    assert metric["year_coverage"] == pytest.approx(0.6, abs=0.01)
    assert metric["meets_minimum_evidence"] is True

    # 4. What the engine made of it, and what that prompts.
    assert finding["state"] == "flagged"
    assert RULE in {f["id"] for f in body["radar"]["flags"]}

    raised = [i for i in body["radar"]["investigations"] if RULE in i["why"]]
    assert raised, "a historical flag must raise an investigation, not float free"
    survey = raised[0]
    assert survey["id"] == "ecology_survey"
    # EM8: it names a check to make, never a verdict on the site. And it traces
    # back to the flag that raised it — no free-floating advice.
    assert RULE in survey["why"]
    assert survey["evidence_factors"] == ["ndvi"]


def test_the_flag_carries_its_threshold_as_contours_own(mock_client, live_ndvi):
    """The threshold is a product decision and must travel labelled as one —
    the UI renders this text rather than composing its own (step 5)."""
    body = fetch(mock_client, declining(0.61, 0.47), live_ndvi)
    meta = entry_for(body)["rule_meta"]

    assert "not a regulatory or scientific standard" in " ".join(
        str(v) for v in meta.values()).lower()


def test_the_composed_finding_states_what_changed_and_never_why(mock_client, live_ndvi):
    """HE9, over the wire, on the sentence a user actually reads.

    Scoped to `flag.text` — the prose the server *composes from this site's
    data* — and deliberately not to the whole payload. `rule_meta` carries the
    fixed disclaimer "not evidence of ecological degradation", and a
    forbidden-word scan cannot tell a denial from an assertion: pointed at the
    entire entry it fails on the very sentence that exists to prevent the
    error. That disclaimer is pinned by the test above instead. The same trap
    caught the comparison scan; see `PROGRESS.md`.
    """
    body = fetch(mock_client, declining(0.61, 0.47), live_ndvi)
    text = entry_for(body)["finding"]["flag"]["text"]

    # States the observation, quantified, against the declared periods.
    assert "declined 23%" in text
    assert "0.61 in 2017–2019" in text and "0.47 in 2023–2025" in text

    # Prompts the professional to establish a cause; never names one.
    lowered = text.lower()
    for forbidden in ("degradation", "damage", "caused by", "due to",
                      "because of", "as a result of"):
        assert forbidden not in lowered, f"causal language in the finding: {forbidden}"


# ---------------------------------------------------------------------------
# The two outcomes that are not a flag
# ---------------------------------------------------------------------------
def test_a_stable_site_is_clear_and_still_rendered(mock_client, live_ndvi):
    """The reason `historical/view.py` exists: a `clear` result raises no flag,
    so a UI reading `radar.flags` alone would draw nothing for the most
    reassuring outcome the product can produce."""
    body = fetch(mock_client, flat(0.61, range(2017, 2026)), live_ndvi)
    entry = entry_for(body)

    assert entry["finding"]["state"] == "clear"
    assert RULE not in {f["id"] for f in body["radar"]["flags"]}
    # Present in the payload regardless — a missing row reads as a clean one.
    assert entry["metric"]["change_pct"] == pytest.approx(0.0, abs=0.001)


def test_too_few_usable_years_is_not_assessed_never_clear(mock_client, live_ndvi):
    """HE6 and EM11's three-state rule. The arithmetic works fine on three
    years; the point is that it must not therefore become a finding."""
    # Only 2017–2019 observed: a change statistic is computable and must not be
    # reported as one, because the two periods would overlap.
    body = fetch(mock_client, flat(0.61, (2017, 2018, 2019)), live_ndvi)
    entry = entry_for(body)

    assert entry["finding"]["state"] == "not_assessed"
    assert RULE not in {f["id"] for f in body["radar"]["flags"]}


def test_generated_ndvi_produces_no_historical_finding(mock_client):
    """HE2, over the wire. With no real NDVI installed the generator stands in,
    and a fabricated fifteen-year trend is the most convincing wrong thing this
    product could draw."""
    routes_catalog.SERIES_CACHE.clear()
    r = mock_client.post("/api/series", json={
        "geometry": GEOMETRY, "factor_ids": ["ndvi"],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["series"]["ndvi"]["source"] == "generated"

    entry = entry_for(body)
    assert entry["finding"]["state"] == "not_assessed"
    assert RULE not in {f["id"] for f in body["radar"]["flags"]}
