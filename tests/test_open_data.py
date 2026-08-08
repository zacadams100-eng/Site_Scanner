"""
Open-data integrations, against recorded response shapes.

These sources cannot be reached from the environment this was written in — the
egress proxy denies everything outside a short allowlist — so every test here
substitutes a recorded payload for the HTTP call. That proves the parsing, the
aggregation and the failure behaviour; it does not prove the endpoint still
answers in that shape, which is what `scripts/check_open_data.py` is for.

The fixtures are shaped from each API's published documentation. Where a field
name is a guess rather than a documented certainty, the test says so, because
the difference matters when the live check finally runs.
"""

import pytest

import open_data


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Nothing in this file may touch the network, even by accident."""
    def boom(*a, **k):
        raise AssertionError("a test tried to make a real HTTP request")
    monkeypatch.setattr(open_data._SESSION, "get", boom)
    open_data._LOOKUP_CACHE.clear()


GUILDFORD = {
    "type": "Polygon",
    "coordinates": [[
        [-0.58, 51.235], [-0.56, 51.235], [-0.56, 51.245], [-0.58, 51.245], [-0.58, 51.235],
    ]],
}
STEPS = ["2024-01", "2024-02", "2024-03", "2024-04", "2024-05", "2024-06"]


def fake_get(monkeypatch, routes):
    """Answer `_get` from a table keyed by a substring of the URL."""
    def _get(url, params=None, auth=None):
        for fragment, payload in routes.items():
            if fragment in url:
                return payload(params) if callable(payload) else payload
        raise AssertionError(f"unexpected request to {url}")
    monkeypatch.setattr(open_data, "_get", _get)


POSTCODE_RESPONSE = {
    "status": 200,
    "result": [{
        "postcode": "GU2 7XH",
        "admin_district": "Guildford",
        "codes": {"admin_district": "E07000209"},
    }],
}


# ---------------------------------------------------------------------------
# postcodes.io — the join everything else depends on
# ---------------------------------------------------------------------------
def test_locate_returns_the_district_and_the_authority_code(monkeypatch):
    fake_get(monkeypatch, {"postcodes.io": POSTCODE_RESPONSE})
    loc = open_data.locate(GUILDFORD)
    assert loc["postcode"] == "GU2 7XH"
    assert loc["district"] == "GU2"
    assert loc["admin_district_code"] == "E07000209"


def test_locate_fails_loudly_when_there_is_no_postcode(monkeypatch):
    """Out at sea there is no nearest postcode, and the caller has to know
    rather than receive a plausible-looking default."""
    fake_get(monkeypatch, {"postcodes.io": {"result": None}})
    with pytest.raises(open_data.OpenDataError):
        open_data.locate(GUILDFORD)


# ---------------------------------------------------------------------------
# planning.data.gov.uk — designations
# ---------------------------------------------------------------------------
def _square(w, s, e, n):
    return {"type": "Feature", "properties": {},
            "geometry": {"type": "Polygon",
                         "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}}


def test_coverage_measures_the_share_of_the_area_inside_a_designation(monkeypatch):
    """Half the AOI covered should read as about half, not as "present"."""
    half = _square(-0.58, 51.235, -0.57, 51.245)      # the western half
    pct = open_data._coverage(GUILDFORD, [half])
    assert 45 <= pct <= 55, pct


def test_coverage_is_zero_when_nothing_intersects(monkeypatch):
    far = _square(-2.0, 52.0, -1.9, 52.1)
    assert open_data._coverage(GUILDFORD, [far]) == 0.0


def test_coverage_is_total_when_the_designation_swallows_the_area(monkeypatch):
    everything = _square(-1.0, 51.0, 0.0, 52.0)
    assert open_data._coverage(GUILDFORD, [everything]) == 100.0


def test_coverage_respects_holes(monkeypatch):
    """A doughnut-shaped designation must not count its own hole. Reported as
    a real case because conservation areas with excluded parcels exist."""
    doughnut = {"type": "Feature", "properties": {}, "geometry": {
        "type": "Polygon", "coordinates": [
            [[-1.0, 51.0], [0.0, 51.0], [0.0, 52.0], [-1.0, 52.0], [-1.0, 51.0]],
            [[-0.58, 51.235], [-0.56, 51.235], [-0.56, 51.245], [-0.58, 51.245], [-0.58, 51.235]],
        ]}}
    assert open_data._coverage(GUILDFORD, [doughnut]) == 0.0


def test_a_designation_series_is_static_and_says_so(monkeypatch):
    fake_get(monkeypatch, {"planning.data.gov.uk": {
        "features": [_square(-0.58, 51.235, -0.57, 51.245)]}})
    pts = open_data.planning_series("conservation-area", "pct", GUILDFORD, STEPS, 200.0)
    assert len(pts) == len(STEPS)
    assert 45 <= pts[0]["value"] <= 55
    assert pts[0]["interpolated"] is False
    assert all(p["interpolated"] for p in pts[1:]), "carried-forward months must say so"
    assert len({p["value"] for p in pts}) == 1


def test_density_counts_features_per_square_kilometre(monkeypatch):
    fake_get(monkeypatch, {"planning.data.gov.uk": {
        "entities": [{"entity": i} for i in range(8)]}})
    pts = open_data.planning_series("listed-building-outline", "density",
                                    GUILDFORD, STEPS, 200.0)      # 200 ha = 2 km²
    assert pts[0]["value"] == 4.0


def test_no_designation_is_zero_not_a_gap(monkeypatch):
    """Nothing intersecting is a measurement — "no conservation area here" —
    unlike a source that failed to answer."""
    fake_get(monkeypatch, {"planning.data.gov.uk": {"features": []}})
    pts = open_data.planning_series("green-belt", "pct", GUILDFORD, STEPS, 200.0)
    assert pts[0]["value"] == 0.0


# ---------------------------------------------------------------------------
# Flood risk zones — one dataset, two factors
#
# The field name `flood-risk-type` and its values are taken from the platform's
# published schema and have NOT been confirmed against a live response. If the
# live check shows a different attribute, this filter is where to fix it — the
# rest of the path is the same code the eleven designations already use.
# ---------------------------------------------------------------------------
def _zone(kind, x0, y0, x1, y1):
    f = _square(x0, y0, x1, y1)
    f["properties"] = {"flood-risk-type": kind}
    return f


FLOOD_MIX = {"features": [
    # Zone 2 over the western half, Zone 3 over a narrow strip of it.
    _zone("Flood Zone 2", -0.58, 51.235, -0.57, 51.245),
    _zone("Flood Zone 3", -0.58, 51.235, -0.578, 51.245),
]}


def test_the_two_flood_zones_do_not_return_the_same_number(monkeypatch):
    """The failure this filter exists to prevent.

    Zone 2 and Zone 3 share one dataset. Without the attribute filter both
    factors measure every returned feature and report an identical figure —
    which is wrong in the direction that looks entirely plausible, because
    Zone 3 genuinely is a subset of Zone 2 and a reader would not blink at
    two similar numbers.
    """
    fake_get(monkeypatch, {"planning.data.gov.uk": FLOOD_MIX})
    z2 = open_data.planning_series("flood-risk-zone", "pct", GUILDFORD, STEPS,
                                   200.0, "flood-risk-type", ("zone 2",))
    z3 = open_data.planning_series("flood-risk-zone", "pct", GUILDFORD, STEPS,
                                   200.0, "flood-risk-type", ("zone 3",))
    assert z2[0]["value"] > z3[0]["value"], \
        "Zone 2 covers Zone 3, so it can never be the smaller number"
    assert z3[0]["value"] > 0


def test_zone_3_subdivisions_count_as_zone_3(monkeypatch):
    """Some authorities publish 3a and 3b rather than a bare 3. Both are
    Zone 3 for planning purposes, and dropping them would report a floodplain
    as dry."""
    fake_get(monkeypatch, {"planning.data.gov.uk": {"features": [
        _zone("Flood Zone 3b", -0.58, 51.235, -0.57, 51.245)]}})
    pts = open_data.planning_series("flood-risk-zone", "pct", GUILDFORD, STEPS,
                                    200.0, "flood-risk-type", ("zone 3",))
    assert pts[0]["value"] > 0


def test_the_filter_is_insensitive_to_case_and_separators(monkeypatch):
    """The same zone appears as `Flood Zone 3`, `flood-risk-zone-3` and
    `zone_3` across the register."""
    for spelling in ("Flood Zone 3", "flood-zone-3", "ZONE_3", "zone 3"):
        fake_get(monkeypatch, {"planning.data.gov.uk": {"features": [
            _zone(spelling, -0.58, 51.235, -0.57, 51.245)]}})
        pts = open_data.planning_series("flood-risk-zone", "pct", GUILDFORD,
                                        STEPS, 200.0, "flood-risk-type",
                                        ("zone 3",))
        assert pts[0]["value"] > 0, f"{spelling!r} was not recognised"


def test_the_attribute_may_arrive_nested(monkeypatch):
    """The platform surfaces dataset-specific fields at the top level for some
    datasets and under a `json` sub-object for others."""
    f = _square(-0.58, 51.235, -0.57, 51.245)
    f["properties"] = {"json": {"flood-risk-type": "Flood Zone 3"}}
    fake_get(monkeypatch, {"planning.data.gov.uk": {"features": [f]}})
    pts = open_data.planning_series("flood-risk-zone", "pct", GUILDFORD, STEPS,
                                    200.0, "flood-risk-type", ("zone 3",))
    assert pts[0]["value"] > 0


def test_zones_present_but_none_matching_is_zero(monkeypatch):
    """A site inside Zone 2 and outside Zone 3 must report 0% Zone 3 — not
    fall through to measuring every feature the dataset returned."""
    fake_get(monkeypatch, {"planning.data.gov.uk": {"features": [
        _zone("Flood Zone 2", -0.58, 51.235, -0.57, 51.245)]}})
    pts = open_data.planning_series("flood-risk-zone", "pct", GUILDFORD, STEPS,
                                    200.0, "flood-risk-type", ("zone 3",))
    assert pts[0]["value"] == 0.0


def test_a_wrong_attribute_name_raises_rather_than_reporting_no_flood_risk(monkeypatch):
    """The most dangerous failure available in this file.

    `flood-risk-type` comes from the published schema and has never been seen
    in a live response. If the real key differs, every feature fails the
    filter — and "nothing matched" would be indistinguishable from "no Zone 3
    here", so the app would report 0% flood risk, confidently, on a
    floodplain. Raising instead falls back to the generator, which labels
    itself demo data.
    """
    f = _square(-0.58, 51.235, -0.57, 51.245)
    f["properties"] = {"flood-zone": "Flood Zone 3"}     # a different key
    fake_get(monkeypatch, {"planning.data.gov.uk": {"features": [f]}})
    with pytest.raises(open_data.OpenDataError) as e:
        open_data.planning_series("flood-risk-zone", "pct", GUILDFORD, STEPS,
                                  200.0, "flood-risk-type", ("zone 3",))
    assert "attribute name is wrong" in str(e.value)


def test_an_empty_response_is_still_zero_not_an_error(monkeypatch):
    """No entities at all is a genuine measurement — this site is nowhere near
    a flood zone — and must not be confused with a broken attribute."""
    fake_get(monkeypatch, {"planning.data.gov.uk": {"features": []}})
    pts = open_data.planning_series("flood-risk-zone", "pct", GUILDFORD, STEPS,
                                    200.0, "flood-risk-type", ("zone 3",))
    assert pts[0]["value"] == 0.0


def test_an_unfiltered_dataset_is_unaffected(monkeypatch):
    """The eleven designations pass no filter and must behave exactly as
    before."""
    fake_get(monkeypatch, {"planning.data.gov.uk": {
        "features": [_square(-0.58, 51.235, -0.57, 51.245)]}})
    pts = open_data.planning_series("conservation-area", "pct", GUILDFORD,
                                    STEPS, 200.0)
    assert 45 <= pts[0]["value"] <= 55


def test_both_flood_factors_are_registered():
    import catalog
    import routes_catalog
    registry, sources = {}, {}
    open_data.install(registry, sources)
    for fid in ("flood_zone2_pct", "flood_zone3_pct"):
        assert fid in registry, f"{fid} should now be real"
        assert sources[fid]["status"] == "written", \
            "never run against the live platform — must not claim verified"


# ---------------------------------------------------------------------------
# Land Registry Price Paid
# ---------------------------------------------------------------------------
def _sale(date, amount, new=False, ptype="terraced"):
    return {
        "date": {"value": date},
        "amount": {"value": str(amount)},
        "newBuild": {"value": "true" if new else "false"},
        "type": {"value": f"http://landregistry.data.gov.uk/def/common/{ptype}"},
    }


PPD_RESPONSE = {"results": {"bindings": [
    _sale("2024-01-15", 300000),
    _sale("2024-01-20", 400000, new=True),
    _sale("2024-02-02", 250000, ptype="flat-maisonette"),
    _sale("2024-03-11", 500000),
]}}


def test_price_paid_aggregates_a_month_into_mean_median_and_count(monkeypatch):
    fake_get(monkeypatch, {"postcodes.io": POSTCODE_RESPONSE,
                           "landregistry": PPD_RESPONSE})
    out = open_data.ppd_group(GUILDFORD, STEPS, 200.0)

    jan = {p["t"]: p["value"] for p in out["avg_sale_price"]}["2024-01"]
    assert jan == 350000
    assert {p["t"]: p["value"] for p in out["transaction_count"]}["2024-01"] == 2
    assert {p["t"]: p["value"] for p in out["new_build_share"]}["2024-01"] == 50.0
    assert {p["t"]: p["value"] for p in out["flat_share"]}["2024-02"] == 100.0


def test_a_month_with_no_sales_is_a_gap_not_a_zero_price(monkeypatch):
    """A district with no transactions in April did not have houses worth
    nothing — the price is unknown and the count is zero, and those are
    different facts."""
    fake_get(monkeypatch, {"postcodes.io": POSTCODE_RESPONSE,
                           "landregistry": PPD_RESPONSE})
    out = open_data.ppd_group(GUILDFORD, STEPS, 200.0)
    april = {p["t"]: p for p in out["avg_sale_price"]}["2024-04"]
    assert april["value"] is None
    assert {p["t"]: p["value"] for p in out["transaction_count"]}["2024-04"] == 0


def test_year_on_year_needs_a_year_of_history(monkeypatch):
    fake_get(monkeypatch, {"postcodes.io": POSTCODE_RESPONSE,
                           "landregistry": PPD_RESPONSE})
    out = open_data.ppd_group(GUILDFORD, STEPS, 200.0)
    assert all(p["value"] is None for p in out["price_change_yoy"]), \
        "six months of data cannot produce a year-on-year change"


# ---------------------------------------------------------------------------
# data.police.uk
# ---------------------------------------------------------------------------
def _crime(category):
    return {"category": category, "location": {"latitude": "51.24", "longitude": "-0.57"}}


def test_crime_is_counted_per_square_kilometre_and_by_category(monkeypatch):
    crimes = [_crime("burglary"), _crime("violent-crime"),
              _crime("violent-crime"), _crime("anti-social-behaviour")]
    fake_get(monkeypatch, {"data.police.uk": crimes})
    out = open_data.police_group(GUILDFORD, STEPS, 200.0)     # 2 km²

    assert {p["t"]: p["value"] for p in out["crime_density"]}["2024-01"] == 2.0
    assert {p["t"]: p["value"] for p in out["burglary_density"]}["2024-01"] == 0.5
    assert {p["t"]: p["value"] for p in out["violent_crime_share"]}["2024-01"] == 50.0
    assert {p["t"]: p["value"] for p in out["antisocial_share"]}["2024-01"] == 25.0


def test_a_month_with_no_crime_is_zero_density_but_no_share(monkeypatch):
    fake_get(monkeypatch, {"data.police.uk": []})
    out = open_data.police_group(GUILDFORD, STEPS, 200.0)
    assert {p["t"]: p["value"] for p in out["crime_density"]}["2024-01"] == 0.0
    assert {p["t"]: p["value"] for p in out["violent_crime_share"]}["2024-01"] is None


def test_future_months_are_gaps_rather_than_empty_results(monkeypatch):
    """The archive stops at last month. Asking for next month returns an empty
    list, which would otherwise render as a crime-free future."""
    fake_get(monkeypatch, {"data.police.uk": []})
    future = ["2099-01", "2099-02"]
    out = open_data.police_group(GUILDFORD, future, 200.0)
    assert all(p["value"] is None for p in out["crime_density"])


def test_the_polygon_sent_to_the_police_api_is_thinned(monkeypatch):
    """A traced field boundary is hundreds of points and the API rejects a very
    long query string."""
    ring = [[-0.58 + i * 0.0001, 51.235 + (i % 3) * 0.0001] for i in range(400)]
    ring.append(ring[0])
    poly = open_data._police_poly({"type": "Polygon", "coordinates": [ring]})
    assert poly.count(":") <= 70


# ---------------------------------------------------------------------------
# EPC
# ---------------------------------------------------------------------------
def test_epc_refuses_to_pretend_it_has_a_key(monkeypatch):
    monkeypatch.delenv("EPC_API_KEY", raising=False)
    monkeypatch.delenv("EPC_API_EMAIL", raising=False)
    with pytest.raises(open_data.OpenDataError) as e:
        open_data.epc_group(GUILDFORD, STEPS, 200.0)
    assert "EPC_API" in str(e.value)


def test_epc_accumulates_certificates_over_time(monkeypatch):
    """A rating is a property of the stock, not of the month it was lodged in,
    so each month sees every certificate up to it."""
    monkeypatch.setenv("EPC_API_EMAIL", "x@example.com")
    monkeypatch.setenv("EPC_API_KEY", "k")
    fake_get(monkeypatch, {"postcodes.io": POSTCODE_RESPONSE,
                           "epc.opendatacommunities": {"rows": [
                               {"lodgement-date": "2024-01-05", "current-energy-efficiency": "60",
                                "potential-energy-efficiency": "80", "current-energy-rating": "D",
                                "total-floor-area": "90", "mainheat-description": "Boiler and radiators, mains gas"},
                               {"lodgement-date": "2024-03-05", "current-energy-efficiency": "80",
                                "potential-energy-efficiency": "90", "current-energy-rating": "C",
                                "total-floor-area": "110", "mainheat-description": "Air source heat pump"},
                           ]}})
    out = open_data.epc_group(GUILDFORD, STEPS, 200.0)
    sap = {p["t"]: p["value"] for p in out["epc_mean_sap"]}
    assert sap["2024-01"] == 60.0
    assert sap["2024-03"] == 70.0, "March averages both certificates"
    assert {p["t"]: p["value"] for p in out["heat_pump_share"]}["2024-03"] == 50.0
    assert {p["t"]: p["value"] for p in out["epc_below_c_share"]}["2024-03"] == 50.0


# ---------------------------------------------------------------------------
# Registration and failure behaviour
# ---------------------------------------------------------------------------
def test_install_registers_only_factors_the_catalogue_knows():
    import catalog
    registry = {}
    open_data.install(registry)
    assert registry, "nothing was registered"
    for factor_id in registry:
        assert factor_id in catalog.FACTOR_BY_ID, factor_id


def test_every_registered_factor_declares_its_source_and_status():
    registry = {}
    open_data.install(registry)
    for factor_id in registry:
        status = open_data.SOURCE_STATUS[factor_id]
        assert status["source"]
        # Nothing may claim to be verified until the live check has been run
        # and someone has recorded that here.
        assert status["status"] in ("written", "verified")


def test_a_failing_source_falls_back_to_generated_data_and_says_so(monkeypatch):
    """The whole degradation contract in one test: a source that cannot answer
    must produce labelled demo data, not an empty report."""
    from fastapi.testclient import TestClient
    import mock_ee_backend
    import routes_catalog

    routes_catalog.REAL_SERIES.clear()
    routes_catalog.SERIES_CACHE.clear()

    def boom(geometry, steps, area_ha):
        raise open_data.OpenDataError("data.police.uk unreachable: ConnectionError")

    routes_catalog.REAL_SERIES["crime_density"] = boom
    try:
        client = TestClient(mock_ee_backend.app)
        body = client.post("/api/series", json={
            "geometry": GUILDFORD, "factor_ids": ["crime_density"],
            "start": "2024-01", "end": "2024-03"}).json()
        series = body["series"]["crime_density"]
        assert series["source"] == "generated"
        assert "unreachable" in series["error"]
        assert series["points"], "a fallback must still return a usable series"
        assert body["real_factors"] == []
    finally:
        routes_catalog.REAL_SERIES.clear()
        routes_catalog.SERIES_CACHE.clear()
