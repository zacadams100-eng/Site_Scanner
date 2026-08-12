"""
The deploy contract that turns eleven client-rendered routes into real files.

Two problems this fixes, and both are invisible from inside the application:

- every unknown URL answered HTTP 200 with the React 404 page, which a crawler
  files as a real page;
- the marketing copy was invisible to anything that does not run JavaScript.

Asserted against `vercel.json` and the build output rather than a running
deployment, because that is what can be checked without deploying — and both
regressions would be silent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "web" / "dist"
VERCEL = json.loads((ROOT / "vercel.json").read_text())

#: Needs `npm run build` first. Skipped rather than failed so the Python suite
#: still runs on a machine that has not built the frontend.
needs_build = pytest.mark.skipif(
    not (DIST / "index.html").exists(),
    reason="web/dist not built — run `npm run build` in web/")


def _sources():
    return [r["source"] for r in VERCEL["rewrites"]]


def test_no_catch_all_rewrite_survives():
    """`/(.*)` → index.html is what made every unknown URL a soft 404.

    If it comes back, everything below still passes and the site silently
    starts answering 200 for pages that do not exist."""
    assert "/(.*)" not in _sources(), \
        "the catch-all rewrite is back — every unknown URL will answer 200"


def test_the_application_still_has_its_rewrite():
    """`/app` is a real SPA with client-side routing beneath it, and without a
    rewrite a deep link into it 404s on refresh."""
    assert "/app" in _sources()
    assert "/app/(.*)" in _sources()


def test_the_application_rewrites_to_its_own_shell_not_the_homepage():
    """index.html now carries the homepage's prerendered markup. Pointing the
    app at it means opening the scanner flashes the marketing headline."""
    for rewrite in VERCEL["rewrites"]:
        if rewrite["source"].startswith("/app"):
            assert rewrite["destination"] == "/app.html", \
                "the app would render the marketing homepage for a frame"


def test_the_api_rewrite_is_untouched():
    assert "/api/(.*)" in _sources()


@needs_build
def test_every_public_route_is_a_real_file():
    """A file means the filesystem answers the URL, which is what makes the
    404 real for everything else."""
    for route in ("index.html", "scanners/index.html", "scanners/land/index.html",
                  "scanners/habitat/index.html", "scanners/coastal/index.html",
                  "about/index.html", "case-studies/index.html",
                  "contact/index.html", "request-a-site-scan/index.html",
                  "thank-you/index.html", "privacy/index.html"):
        assert (DIST / route).exists(), f"{route} was not prerendered"


@needs_build
def test_a_404_page_exists_for_the_platform_to_serve():
    page = DIST / "404.html"
    assert page.exists()
    body = page.read_text()
    # It must not be indexed: a 404 in search results is a page people reach
    # without having done anything.
    assert 'content="noindex' in body


@needs_build
def test_the_prerendered_pages_contain_their_actual_copy():
    """The point of the exercise. A shell with an empty <div id="root"> would
    pass every test above and fix nothing."""
    home = (DIST / "index.html").read_text()
    assert "Know what to investigate" in home
    assert "<h1" in home
    scanners = (DIST / "scanners" / "index.html").read_text()
    # The built scanners, by name. Checked against the marketing copy rather
    # than the registry on purpose: this page is written prose, and asserting a
    # count here would break every time a scanner is added, which is how a test
    # gets edited rather than read.
    assert "Ecology" in scanners and "Water" in scanners
    # And the thing the page must never stop saying. Partial coverage stated
    # rather than implied is the whole reason this page lists what each scanner
    # does not do, and a redesign that dropped it would pass every other check
    # here.
    assert "Registered, not built" in scanners


@needs_build
def test_each_page_carries_its_own_title_and_description():
    """Prerendering with one shared <head> would undo the SEO work that made
    every route's metadata unique."""
    seen = {}
    for route in ("index.html", "scanners/index.html", "about/index.html",
                  "privacy/index.html", "contact/index.html"):
        body = (DIST / route).read_text()
        title = body.split("<title>", 1)[1].split("</title>", 1)[0]
        assert title not in seen, f"{route} shares a title with {seen.get(title)}"
        seen[title] = route


@needs_build
def test_the_app_shell_carries_no_marketing_markup():
    """It is the bare document React mounts into."""
    shell = (DIST / "app.html").read_text()
    assert "Know what to investigate" not in shell
    assert 'id="root"' in shell


@needs_build
def test_prerendering_did_not_bake_in_runtime_canvas_state():
    """The hero draws into a canvas at runtime. A serialised canvas keeps its
    inline size and the `is-ready` class, which would tell a fresh page it had
    already loaded and leave the sheet blank."""
    home = (DIST / "index.html").read_text()
    assert "hf is-ready" not in home
