"""
The one header that decides whether a number may be believed.

`X-Contour-Mock: true` is how the interface knows it is looking at generated
data, and the whole real-data rule hangs off it. Two ways it can break, and
both are silent:

- the mock stops stamping it, and generated numbers lose their badge;
- the real backend starts stamping it, and real observations are permanently
  labelled demo data.

The first is covered by `test_mock_backend.py`. The second is covered here,
without needing credentials, by asserting the real backend contains no code
that could set it.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

import mock_ee_backend

ROOT = Path(__file__).resolve().parent.parent


def test_the_mock_stamps_every_response_including_errors():
    """Including the failures. A 400 from the mock is still generated data,
    and an unstamped error response is one the UI would treat as real."""
    with TestClient(mock_ee_backend.app) as c:
        for response in (
            c.get("/api/catalog"),
            c.get("/api/catalog?scanner=nonsense"),      # 400
            c.get("/api/no-such-route"),                 # 404
            c.post("/api/series", json={}),              # 422
        ):
            assert response.headers.get("X-Contour-Mock") == "true", \
                f"{response.status_code} response was not tagged as generated"


def test_the_real_backend_never_claims_to_be_the_mock():
    """`app.py` must contain nothing that sets the header.

    Asserted against the source rather than a running server because the real
    backend cannot be imported without Earth Engine credentials — it
    initialises at import time by design. A source check is weaker than a live
    one and is the strongest check available without a service account.
    """
    source = (ROOT / "app.py").read_text()
    assert not re.search(r"X-Contour-Mock", source, re.IGNORECASE), \
        "app.py sets the demo-data header — real observations would be " \
        "labelled generated, permanently and invisibly"


def test_the_header_is_exposed_to_the_browser():
    """A header the browser hides is a header the interface cannot read.

    Cross-origin responses expose only a safelist unless the server says
    otherwise, and this one is not on it — without `expose_headers` the badge
    silently never appears in a deployed split-origin setup.
    """
    source = (ROOT / "mock_ee_backend.py").read_text()
    assert "expose_headers" in source
    assert "X-Contour-Mock" in source.split("expose_headers", 1)[1][:200]


def test_absent_means_real_not_unknown():
    """The frontend reads `=== 'true'`, so an absent header is false.

    Stated as a test because the alternative reading — absent means "we do not
    know", shown as a warning — would put a demo badge on every real
    deployment, and someone would eventually 'fix' it by defaulting the other
    way.
    """
    api = (ROOT / "web" / "src" / "api.ts").read_text()
    app_tsx = (ROOT / "web" / "src" / "App.tsx").read_text()
    for source in (api, app_tsx):
        for match in re.finditer(r"X-Contour-Mock'\)\s*(===|!==)\s*'true'", source):
            assert match.group(1) == "===", \
                "an inverted comparison would label real data as generated"
