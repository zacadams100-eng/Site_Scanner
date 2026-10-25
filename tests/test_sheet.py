import json
import sqlite3

import pytest
import requests

from sheet.fetch import NONE_FOUND, NOT_ASSESSED, PRESENT, Fetcher, FixtureFetcher, fetch_all
from sheet.findings import build_findings
from sheet.geometry import site_from_geojson
from sheet.layers import LAYER_BY_ID, LAYERS
from sheet.make import make_sheet

from tests.fixtures_build import SITE, build, site_geojson


# --- the layer list -------------------------------------------------------------
def test_thirty_layers_each_with_a_source():
    assert len(LAYERS) == 30
    for l in LAYERS:
        assert (l.source == "planning" and l.dataset) or (l.source == "arcgis" and l.url), l.id


# --- fetching: failures are never "clear" ---------------------------------------
class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")

    def json(self):
        return self.payload


class FakeSession(requests.Session):
    def __init__(self, responses):
        super().__init__()
        self.responses, self.calls = list(responses), []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_network_failure_is_not_assessed():
    # Retried once, then reported: still down means not assessed.
    f = Fetcher(FakeSession([requests.ConnectionError("down"), requests.ConnectionError("down")]))
    r = f.fetch(LAYER_BY_ID["sssi"], SITE)
    assert r.status == NOT_ASSESSED and "down" in r.error


def test_http_error_is_not_assessed():
    f = Fetcher(FakeSession([FakeResponse({}, 503)]))
    assert f.fetch(LAYER_BY_ID["sssi"], SITE).status == NOT_ASSESSED


def test_arcgis_error_body_is_not_assessed():
    f = Fetcher(FakeSession([FakeResponse({"error": {"message": "Invalid query"}})]))
    r = f.fetch(LAYER_BY_ID["priority_habitat"], SITE)
    assert r.status == NOT_ASSESSED and "Invalid query" in r.error


EMPTY_FC = {"type": "FeatureCollection", "features": []}
# The national probe: one record somewhere in England, so the dataset is real.
SOMEWHERE = {"entities": [{"entity": 1}], "count": 1}


def test_empty_answer_is_none_found():
    f = Fetcher(FakeSession([FakeResponse(EMPTY_FC), FakeResponse(SOMEWHERE)]))
    assert f.fetch(LAYER_BY_ID["sssi"], SITE).status == NONE_FOUND


def test_dataset_empty_nationally_is_not_assessed():
    """planning.data's forest-inventory had 0 records and printed "none found"."""
    s = FakeSession([FakeResponse(EMPTY_FC), FakeResponse({"entities": [], "count": 0})])
    r = Fetcher(s).fetch(LAYER_BY_ID["sssi"], SITE)
    assert r.status == NOT_ASSESSED and "empty nationally" in r.error
    assert s.calls[1][1]["dataset"] == "site-of-special-scientific-interest"
    assert s.calls[1][0].endswith("/entity.json")      # no geometry in the national probe


def test_arcgis_dataset_empty_nationally_is_not_assessed():
    s = FakeSession([FakeResponse(EMPTY_FC), FakeResponse({"count": 0})])
    assert Fetcher(s).fetch(LAYER_BY_ID["main_river"], SITE).status == NOT_ASSESSED


def test_failed_national_probe_is_not_assessed():
    s = FakeSession([FakeResponse(EMPTY_FC), requests.ConnectionError("down"), requests.ConnectionError("down")])
    assert Fetcher(s).fetch(LAYER_BY_ID["sssi"], SITE).status == NOT_ASSESSED


def test_planning_follows_next_links():
    from shapely.geometry import mapping
    from sheet.geometry import to_wgs
    feat = {"type": "Feature", "properties": {"name": "A"}, "geometry": mapping(to_wgs(SITE.centroid.buffer(10)))}
    s = FakeSession([
        FakeResponse({"type": "FeatureCollection", "features": [feat], "links": {"next": "https://x/next"}}),
        FakeResponse({"type": "FeatureCollection", "features": [dict(feat, properties={"name": "B"})], "links": {}}),
    ])
    r = Fetcher(s).fetch(LAYER_BY_ID["sssi"], SITE)
    assert r.status == PRESENT and {f.label for f in r.features} == {"A", "B"}
    assert s.calls[1][0] == "https://x/next"
    assert s.calls[0][1]["dataset"] == "site-of-special-scientific-interest"


def test_features_outside_radius_are_dropped():
    from shapely.geometry import Point, mapping
    from sheet.geometry import to_wgs
    far = Point(SITE.centroid.x + 5000, SITE.centroid.y).buffer(50)   # SSSI radius is 2 km
    s = FakeSession([FakeResponse({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": "Far"}, "geometry": mapping(to_wgs(far))}]}),
        FakeResponse(SOMEWHERE)])
    assert Fetcher(s).fetch(LAYER_BY_ID["sssi"], SITE).status == NONE_FOUND


# --- findings -------------------------------------------------------------------
@pytest.fixture(scope="module")
def fixture_dir(tmp_path_factory):
    return build(tmp_path_factory.mktemp("fx"))


@pytest.fixture(scope="module")
def results(fixture_dir):
    return fetch_all(SITE, FixtureFetcher(fixture_dir))


def test_missing_fixture_is_not_assessed(results):
    r = {x.layer.id: x for x in results}
    assert r["ramsar"].status == NOT_ASSESSED


def test_findings_distances_and_on_site(results):
    f = {x.layer_id: x for x in build_findings(results, SITE)}
    assert f["priority_habitat"].on_site
    assert f["priority_habitat"].items[0].where() == "within the red line"
    sssi = f["sssi"].items[0]
    assert sssi.label == "Fixture Down SSSI" and 400 < sssi.distance_m < 700 and sssi.direction == "NE"
    assert f["spa"].status == NONE_FOUND
    assert "Not assessed" in f["ramsar"].summary()
    # council-published layers warn that a nil return is not conclusive
    assert "confirm locally" in f["tpo_area"].summary()
    assert "confirm locally" not in f["spa"].summary()


def test_no_score_anywhere(results):
    text = " ".join(f.summary() for f in build_findings(results, SITE)).lower()
    for word in ("score", "suitab", "rating", "grade a", "pass", "fail"):
        assert word not in text


# --- end to end ------------------------------------------------------------------
def test_make_sheet_end_to_end(tmp_path, fixture_dir):
    site = site_from_geojson(site_geojson())
    rec = make_sheet(site, tmp_path, "Fixture Field, Test Lane", "TEST-001", FixtureFetcher(fixture_dir))
    assert rec["test_data"] is True
    pdf = tmp_path / rec["files"]["pdf"]
    assert pdf.read_bytes()[:4] == b"%PDF" and pdf.stat().st_size > 20_000
    assert rec["scale"] in (10000, 12500, 25000)
    gpkg = tmp_path / rec["files"]["gpkg"]
    con = sqlite3.connect(gpkg)
    tables = {r[0] for r in con.execute("SELECT table_name FROM gpkg_contents WHERE data_type='features'")}
    assert {"red_line", "search_rings", "sssi", "priority_habitat", "main_river"} <= tables
    styled = {r[0] for r in con.execute("SELECT f_table_name FROM layer_styles")}
    assert tables <= styled
    srs = {r[0] for r in con.execute("SELECT srs_id FROM gpkg_geometry_columns")}
    assert srs == {27700}
    con.close()


# --- the draw page's API --------------------------------------------------------
def test_api_returns_map_features(tmp_path, fixture_dir, monkeypatch):
    from fastapi.testclient import TestClient
    import sheet.api as api
    monkeypatch.setattr(api, "FIXTURES", str(fixture_dir))
    monkeypatch.setattr(api, "JOBS", tmp_path.resolve())
    c = TestClient(api.app)
    assert c.get("/api/info").json()["test_data"] is True
    assert len(c.get("/api/layers").json()) == 30
    assert c.post("/api/sheet", json={"red_line": site_geojson(), "title": "Fixture Field"}).status_code == 400
    r = c.post("/api/sheet", json={"red_line": site_geojson(), "title": "Fixture Field", "client_ref": "T-1"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["test_data"] is True and d["counts"]["not_assessed"] == 1
    assert d["map"]["sssi"]["features"][0]["properties"]["label"] == "Fixture Down SSSI"
    assert "sssi_irz" not in d["map"]          # findings-only layers stay off the map
    assert c.get(d["urls"]["pdf"]).content[:4] == b"%PDF"
    assert c.get(f"/files/{d['job']}/nope.pdf").status_code == 404


def test_api_rejects_a_point():
    from fastapi.testclient import TestClient
    from sheet.api import app
    r = TestClient(app).post("/api/sheet", json={
        "red_line": {"type": "Point", "coordinates": [-0.3, 51.2]}, "title": "x", "client_ref": "T-1"})
    assert r.status_code == 400 and "must be an area" in r.json()["detail"]


def test_record_keeps_fields_of_unlabelled_features(tmp_path, fixture_dir):
    rec = make_sheet(site_from_geojson(site_geojson()), tmp_path, "x", "", FixtureFetcher(fixture_dir))
    f = {x["layer"]: x for x in rec["findings"]}
    assert f["sssi"]["unlabelled_fields"] == {}
    # surface water has no label fields by design, so nothing to report
    assert f["surface_water"]["unlabelled_fields"] == {}


def test_label_codes_and_defaults_from_live_field_names():
    """Field names as the publishers actually sent them on the first live run."""
    from shapely.geometry import mapping
    from sheet.fetch import _features_from_geojson
    from sheet.geometry import search_area, to_wgs
    g = mapping(to_wgs(SITE.centroid.buffer(10)))
    def label(layer_id, props):
        fc = {"features": [{"type": "Feature", "properties": props, "geometry": g}]}
        l = LAYER_BY_ID[layer_id]
        return _features_from_geojson(fc, l, search_area(SITE, l.search_m))[0].label
    assert label("ancient_woodland", {"name": "", "ancient-woodland-status": "ASNW"}) == \
        "Ancient semi-natural woodland"
    assert label("priority_habitat", {"MainHabs": "Deciduous woodland"}) == "Deciduous woodland"
    assert label("sssi_irz", {"IRZURL": "https://irz.geodata.org.uk/x"}) == "https://irz.geodata.org.uk/x"
    assert label("listed_building", {"name": "CHURCH OF ST JOHN THE EVANGELIST",
                                     "listed-building-grade": "II*"}) == \
        "Church of St John the Evangelist (Grade II*)"
    assert label("ancient_woodland", {"name": "(Epoch3:Watley's Copse)(Tithe:Watleys Copse)"}) == \
        "Watley's Copse"
    assert label("sssi", {"name": "RSPB"}) == "RSPB"


def test_parcel_layers_report_area_not_counts(results):
    f = {x.layer_id: x for x in build_findings(results, SITE)}
    sw = f["surface_water"].summary()          # two small ponds, one on the red line
    assert sw.startswith("Covers ") and "of the red line" in sw and "parcels" not in sw
    ph = f["priority_habitat"].summary()
    assert ph.startswith("Within the red line: Lowland meadows ")
    assert "Within 2 km: " in ph and "Deciduous woodland" in ph and " ha" in ph


# --- findings that read like a professional's sheet ------------------------------
from sheet.findings import Item, LayerFinding, same_name_key  # noqa: E402


def test_many_listed_buildings_are_counted_by_grade():
    items = ([Item("Church of St Peter (Grade I)", 120, "N", grade="I"),
              Item("The Manor (Grade II*)", 300, "E", grade="II*"),
              Item("Old Cottage (Grade II)", 0, "", grade="II")]
             + [Item(f"House {n} (Grade II)", 200 + n, "S", grade="II") for n in range(175)])
    f = LayerFinding("listed_building", "Listed building", "", PRESENT, 500, items=items, mode="grades")
    s = f.summary(max_items=8)
    assert s.startswith("178 within 500 m: 1 Grade I, 1 Grade II*, 176 Grade II.")
    assert "Church of St Peter" in s and "The Manor" in s
    assert "Old Cottage" in s          # on the red line: always named, whatever its grade
    assert "House 3" not in s


def test_a_few_listed_buildings_are_still_listed():
    items = [Item("Barn (Grade II)", 40, "W", grade="II")]
    f = LayerFinding("listed_building", "Listed building", "", PRESENT, 500, items=items, mode="grades")
    assert f.summary() == "Barn (Grade II), 40 m W."


def test_one_place_published_by_two_councils_is_one_finding():
    assert same_name_key("RIVER WEY AND GODALMING NAVIGATIONS") == same_name_key("Wey and Godalming Navigations")
    assert same_name_key("Godalming") != same_name_key("Farncombe")


def test_risk_zones_say_the_red_line_is_in_them_with_criteria():
    url = "https://irz.geodata.org.uk/IRZ/step2.html?irzcode={}&notes=11401&location=1,2 %20(IRZ%20polygon%20centre)"
    items = [Item(url.format("0111242322201"), 0, "", count=2), Item(url.format("3111241211101"), 0, "")]
    f = LayerFinding("sssi_irz", "SSSI Impact Risk Zone", "", PRESENT, 0, items=items, mode="zones")
    assert f.summary() == ("The red line falls in 2 impact risk zones (IRZ codes 0111242322201, 3111241211101). "
                           "Check the consultation criteria for the proposal type at irz.geodata.org.uk.")


def test_de_designated_sites_are_not_findings():
    """planning.data keeps sites with an end-date; one LNR ended in 2025."""
    from shapely.geometry import mapping
    from sheet.geometry import to_wgs
    g = mapping(to_wgs(SITE.centroid.buffer(10)))
    s = FakeSession([FakeResponse({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": g, "properties": {"name": "Gone", "end-date": "2025-01-27"}},
        {"type": "Feature", "geometry": g, "properties": {"name": "Here", "end-date": ""}}]})])
    r = Fetcher(s).fetch(LAYER_BY_ID["lnr"], SITE)
    assert [f.label for f in r.features] == ["Here"]


def test_layers_without_names_say_what_they_are():
    f = {x.layer_id: x for x in build_findings(fetch_all(SITE, FixtureFetcher(build(
        __import__("pathlib").Path(__import__("tempfile").mkdtemp())))), SITE)}
    assert f["main_river"].summary().startswith("Main river, ")


def test_names_that_are_file_names_or_numbered_are_cleaned():
    from sheet.fetch import clean_name
    assert clean_name("Conservation_Area.TAB") == ""
    assert clean_name("46=Long Moor Coppice") == "Long Moor Coppice"
    assert clean_name("(Epoch3:46=Long Moor Coppice)(Tithe:)") == "Long Moor Coppice"


def test_unnamed_copy_of_a_named_place_is_dropped():
    from shapely.geometry import box
    from sheet.fetch import Feature, LayerResult
    from sheet.findings import _items
    g = box(SITE.bounds[2] + 600, SITE.bounds[1], SITE.bounds[2] + 900, SITE.bounds[3])
    r = LayerResult(LAYER_BY_ID["conservation_area"], PRESENT,
                    [Feature(g, "Little Bookham", {}), Feature(g, "", {})])
    assert [i.label for i in _items(r, SITE)] == ["Little Bookham"]


def test_woodland_asks_only_for_woodland():
    s = FakeSession([FakeResponse(EMPTY_FC), FakeResponse({"count": 5})])
    Fetcher(s).fetch(LAYER_BY_ID["woodland"], SITE)
    assert s.calls[0][1]["where"] == "CATEGORY='Woodland'"


def test_a_timeout_is_retried_once():
    s = FakeSession([requests.Timeout("slow"), FakeResponse(EMPTY_FC), FakeResponse(SOMEWHERE)])
    assert Fetcher(s).fetch(LAYER_BY_ID["sssi"], SITE).status == NONE_FOUND


def test_an_unrecognised_probe_reply_is_not_called_empty():
    s = FakeSession([FakeResponse(EMPTY_FC), FakeResponse({"detail": "oops"})])
    r = Fetcher(s).fetch(LAYER_BY_ID["sssi"], SITE)
    assert r.status == NOT_ASSESSED and "unexpected reply" in r.error


def test_tiled_layers_do_not_count_tiles_as_parcels():
    items = [Item("Flood Zone 2", 503, "S", count=92)]
    f = LayerFinding("flood_zone", "Flood Zone 2 / 3", "", PRESENT, 1000, items=items, count_parcels=False)
    assert f.summary() == "Flood Zone 2, 503 m S."


def test_small_and_medium_sites_print_at_1_to_10000():
    from shapely.geometry import box
    from sheet.render import choose_scale
    for side in (140, 420, 700):          # about 2, 18 and 50 ha
        assert choose_scale(box(0, 0, side, side), 500) == 10000


def test_headline_is_never_clear_when_layers_were_not_assessed(tmp_path):
    """Every layer failing must not print "No mapped constraint falls within the red line"."""
    from sheet.findings import counts
    from sheet.render import headline_lines
    results = fetch_all(SITE, FixtureFetcher(tmp_path / "no-fixtures-here"))
    findings = build_findings(results, SITE)
    text = " ".join(headline_lines(findings, counts(findings)))
    assert "No mapped constraint" not in text and "30 not assessed" in text


def test_main_rivers_take_their_names_from_os_open_rivers(tmp_path, monkeypatch):
    import geopandas as gpd
    from shapely.geometry import LineString
    from sheet.fetch import Feature, LayerResult
    from sheet.geometry import BNG, search_area
    from sheet.rivers import name_main_rivers
    cx, cy = SITE.centroid.x, SITE.centroid.y
    ea = LineString([(cx - 800, cy - 500), (cx + 800, cy - 500)])          # EA line, no name
    os_wey = LineString([(cx - 900, cy - 505), (cx + 900, cy - 495)])      # runs alongside
    os_ditch = LineString([(cx, cy - 900), (cx, cy - 100)])                # crosses only
    gpkg = tmp_path / "oprvrs.gpkg"
    gpd.GeoDataFrame({"name1": ["River Wey", "Mill Ditch"]}, geometry=[os_wey, os_ditch],
                     crs=BNG).to_file(gpkg, layer="watercourse_link", driver="GPKG")
    r = LayerResult(LAYER_BY_ID["main_river"], PRESENT, [Feature(ea, "Main river", {})])
    assert name_main_rivers([r], search_area(SITE, 1000), gpkg) == 1
    assert r.features[0].label == "River Wey"
    # Without the file nothing changes.
    r2 = LayerResult(LAYER_BY_ID["main_river"], PRESENT, [Feature(ea, "Main river", {})])
    monkeypatch.delenv("CONTOUR_OPEN_RIVERS", raising=False)
    assert name_main_rivers([r2], search_area(SITE, 1000)) == 0 and r2.features[0].label == "Main river"
