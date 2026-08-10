"""
Shared test setup.

app.py calls init_earth_engine() at import time and would raise without
credentials, so a stand-in `ee` module is installed into sys.modules *before*
app.py is ever imported. The stand-in serves mock_ee_backend's responses, so
the tests assert against the same payload shapes the real backend produces
without needing a service account.
"""

import json
import pathlib
import sys
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mock_ee_backend import DEFAULT_TILE_URL_NDVI, make_stats  # noqa: E402


class EEState:
    """Knobs the tests use to steer the fake, plus call counters so caching
    can be asserted on rather than inferred."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.year = 2024
        self.geometry = None
        self.failure = None          # set to an Exception to make EE blow up
        self.calls = {"stats": 0, "tile": 0}


STATE = EEState()


class EEException(Exception):
    """Stands in for ee.EEException."""


class _Fetcher:
    url_format = DEFAULT_TILE_URL_NDVI


class _Node:
    """Any Earth Engine object.

    Every unknown method returns another _Node, which is enough for the long
    chains in app.py (.filterDate().filter().map().median(), .select().unmask()
    .divide().add().rename(), ...) without modelling the real API. These tests
    cover app.py's HTTP layer; the Earth Engine logic itself is what the real
    credentials will validate.
    """

    def __init__(self, label="ee"):
        self._label = label

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def call(*args, **kwargs):
            # sentinel2_composite builds f"{year}-01-01"; picking the year up
            # here lets the fake return year-appropriate stats.
            if name == "filterDate" and args:
                try:
                    STATE.year = int(str(args[0])[:4])
                except (ValueError, TypeError):
                    pass
            return _Node(f"{self._label}.{name}")

        return call

    def getMapId(self, vis_params=None):
        if STATE.failure:
            raise STATE.failure
        STATE.calls["tile"] += 1
        return {"tile_fetcher": _Fetcher()}


class _Dictionary(_Node):
    def __init__(self, mapping=None):
        super().__init__("Dictionary")
        self._mapping = mapping or {}

    def getInfo(self):
        if STATE.failure:
            raise STATE.failure
        STATE.calls["stats"] += 1
        # The real getInfo resolves the whole dict server-side; the mock
        # produces the same shape for the geometry that was submitted.
        return make_stats(STATE.year, STATE.geometry)


def _make_fake_ee() -> types.ModuleType:
    mod = types.ModuleType("ee")

    def Geometry(geom, *args, **kwargs):
        # The real ee.Geometry rejects malformed GeoJSON, which is what turns
        # a bad request into app.py's 500. Mirror that.
        if not isinstance(geom, dict) or "type" not in geom or "coordinates" not in geom:
            raise EEException(f"Invalid GeoJSON geometry: {geom!r}")
        if geom["type"] not in ("Polygon", "MultiPolygon"):
            raise EEException(f"Unsupported geometry type: {geom['type']}")
        STATE.geometry = geom
        return _Node("Geometry")

    def ServiceAccountCredentials(email, key_data=None, **kwargs):
        if not email:
            raise EEException("client_email missing from the service account key")
        return _Node("Credentials")

    def Initialize(credentials=None, project=None, **kwargs):
        if not project:
            raise EEException("project is required")
        return None

    mod.Image = lambda *a, **k: _Node("Image")
    mod.ImageCollection = lambda *a, **k: _Node("ImageCollection")
    mod.Dictionary = _Dictionary
    mod.Geometry = Geometry
    mod.Reducer = _Node("Reducer")
    mod.Filter = _Node("Filter")
    mod.ServiceAccountCredentials = ServiceAccountCredentials
    mod.Initialize = Initialize
    mod.EEException = EEException
    return mod


# Must happen at import time: pytest imports this module before collecting the
# test modules that import app.py.
sys.modules.setdefault("ee", _make_fake_ee())


@pytest.fixture(autouse=True)
def _reset_ee_state():
    """Every test starts with fresh counters and no injected failure."""
    STATE.reset()
    yield
    STATE.reset()


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    """The limiter is one process-wide instance, so without this the budget is
    shared across the whole session and tests start failing in whatever order
    happens to exhaust it. Resetting per test keeps the middleware exercised —
    raising the budget for tests would leave it untested."""
    import ratelimit

    ratelimit.LIMITER.reset()
    yield
    ratelimit.LIMITER.reset()


@pytest.fixture(autouse=True)
def _no_real_api_key(monkeypatch):
    """Nothing in this suite should reach the Anthropic API.

    Tests that exercise the Claude path stub the client and set their own key.
    Clearing it by default means a developer with ANTHROPIC_API_KEY exported
    can't accidentally make (and pay for) live calls by running the tests.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture(scope="session")
def ee_env():
    """Credentials that satisfy init_earth_engine()'s checks without being real."""
    import os

    os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"] = json.dumps(
        {"client_email": "contour-tests@example.iam.gserviceaccount.com", "type": "service_account"}
    )
    os.environ["EE_PROJECT"] = "contour-test-project"
    return True


@pytest.fixture
def app_client(ee_env):
    """TestClient for the real app.py, with caches emptied between tests."""
    from fastapi.testclient import TestClient

    import app as app_module

    app_module.TILE_CACHE.clear()
    app_module.STATS_CACHE.clear()
    return TestClient(app_module.app)


@pytest.fixture
def mock_client():
    """TestClient for the mock backend."""
    from fastapi.testclient import TestClient

    import mock_ee_backend

    return TestClient(mock_ee_backend.app)


@pytest.fixture
def guildford_polygon():
    """The example area from the README, near Guildford."""
    return {
        "type": "Polygon",
        "coordinates": [[
            [-0.58, 51.235], [-0.56, 51.235], [-0.56, 51.245],
            [-0.58, 51.245], [-0.58, 51.235],
        ]],
    }


# ---------------------------------------------------------------------------
# A live Sentinel-2 factor, without Earth Engine
# ---------------------------------------------------------------------------
#: The archive Sentinel-2 actually has. Months before this are `None`, which is
#: the correct answer and not a gap to paper over (HE3).
S2_START = (2017, 3)

#: April–September, the vegetation window frozen in the methodology.
S2_WINDOW = (4, 5, 6, 7, 8, 9)


def s2_ndvi(per_year):
    """A Sentinel-2 NDVI implementation, in the shape `REAL_SERIES` holds.

    Lives here rather than in one test module because two suites now drive the
    real HTTP path with it. Returns one point per requested step; a month
    outside the archive, or a year the scenario does not supply, is a gap
    carried as a gap.
    """
    def fn(geometry, steps, area_ha):
        points = []
        for t in steps:
            year, month = int(t[:4]), int(t[5:7])
            value = None
            if (year, month) >= S2_START and month in S2_WINDOW:
                value = per_year.get(year)
            # `valid_fraction` is how much of the AOI the composite saw, and
            # `annual_rollup` weights by it. A gap is 0.0, matching
            # `ee_series._gap`.
            points.append({"t": t, "value": value, "interpolated": False,
                           "valid_fraction": 0.0 if value is None else 0.95})
        return points
    return fn


@pytest.fixture
def live_ndvi(monkeypatch):
    """Install a fixture NDVI as a *real* Earth Engine factor.

    The endpoint matters: `_series_for` derives `source` from it, and only
    `earth-engine` or `open-data` may produce a finding at all (EM1–EM3, HE2).
    A fixture registered without a plausible endpoint would be labelled
    `open-data` and the test would prove the wrong provenance.

    The series cache is cleared on the way in and out. Its key is
    (factor, geometry, steps) — identical across scenarios — so without this a
    second scenario would silently assert against the first one's data.
    """
    import routes_catalog

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
