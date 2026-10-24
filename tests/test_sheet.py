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
    f = Fetcher(FakeSession([requests.ConnectionError("down")]))
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
SOMEWHERE = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {},
                                                         "geometry": None}]}


def test_empty_answer_is_none_found():
    f = Fetcher(FakeSession([FakeResponse(EMPTY_FC), FakeResponse(SOMEWHERE)]))
    assert f.fetch(LAYER_BY_ID["sssi"], SITE).status == NONE_FOUND


def test_dataset_empty_nationally_is_not_assessed():
    """planning.data's forest-inventory had 0 records and printed "none found"."""
    s = FakeSession([FakeResponse(EMPTY_FC), FakeResponse(EMPTY_FC)])
    r = Fetcher(s).fetch(LAYER_BY_ID["sssi"], SITE)
    assert r.status == NOT_ASSESSED and "empty nationally" in r.error
    assert s.calls[1][1] == {"dataset": "site-of-special-scientific-interest", "limit": 1}


def test_arcgis_dataset_empty_nationally_is_not_assessed():
    s = FakeSession([FakeResponse(EMPTY_FC), FakeResponse({"count": 0})])
    assert Fetcher(s).fetch(LAYER_BY_ID["main_river"], SITE).status == NOT_ASSESSED


def test_failed_national_probe_is_not_assessed():
    s = FakeSession([FakeResponse(EMPTY_FC), requests.ConnectionError("down")])
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
    items = [Item("https://irz.geodata.org.uk/a", 0, "", count=2), Item("https://irz.geodata.org.uk/b", 0, "")]
    f = LayerFinding("sssi_irz", "SSSI Impact Risk Zone", "", PRESENT, 0, items=items, mode="zones")
    assert f.summary() == ("The red line falls in 3 impact risk zones. "
                           "Criteria: https://irz.geodata.org.uk/a; https://irz.geodata.org.uk/b.")
