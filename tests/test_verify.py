"""The one-command verifier.

Its value is entirely in not lying to somebody who has made time to run it.
Two ways it could:

- calling a network outage a broken integration, which turns a train journey
  into a to-do list of imaginary bugs
- reporting the catalogue's headline number wrong, which is the number the
  whole exercise exists to move

Both are tested. The checks themselves are not — those are subprocess calls to
scripts with their own tests, and re-testing them here would only assert that
`subprocess.run` works.
"""

import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location(
    "verify_script", ROOT / "scripts" / "verify.py")
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


# ---------------------------------------------------------------------------
# Offline is not the same as broken
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("output", [
    "FAIL locate — OpenDataError: https://api.postcodes.io unreachable: ProxyError",
    "requests.exceptions.ConnectionError: Max retries exceeded with url:",
    "ProxyError: Tunnel connection failed: 403 Forbidden",
    "socket.gaierror: [Errno -2] Name or service not known",
    "urllib3.exceptions.NewConnectionError: Failed to establish a new connection",
    "ssl.SSLCertVerificationError: certificate verify failed",
])
def test_network_failures_are_recognised(output):
    assert verify._looks_offline(output), \
        "this would be reported as a broken integration"


@pytest.mark.parametrize("output", [
    "FAIL  crime_density — 4 of 180 months returned None",
    "FAIL  median_sale_price — value 4.2 outside declared range 50000..2000000",
    "✓ All 22 factors returned plausible values.",
    "FAIL  flood_zone3_pct — none of the 8 entities carry 'flood-risk-type'",
])
def test_real_failures_are_not_excused_as_network_trouble(output):
    """The opposite mistake, and the worse one: a genuine data bug dismissed as
    a connection problem is a bug that never gets fixed."""
    assert not verify._looks_offline(output)


# ---------------------------------------------------------------------------
# The headline number
# ---------------------------------------------------------------------------
def test_the_catalogue_state_counts_earth_engine_too():
    """`ee_series` imports `ee` lazily but `install` does not, so counting by
    installing reported 24 real factors instead of 51 — wrong in the one place
    the script is supposed to be right."""
    import catalog

    state = verify.catalogue_state()
    # Not a hardcoded total. The catalogue grows — it went 269 to 273 the day
    # a branch merge landed four Environment Agency rainfall factors — and a
    # test that pins the number fails on good news.
    assert f"of {len(catalog.FACTORS)} factors real" in state

    import re
    real = int(re.match(r"(\d+) of ", state).group(1))
    assert real > 40, f"undercounted: {state!r}"


def test_the_catalogue_state_reports_verification_separately():
    """Real and verified are different numbers, and collapsing them is the
    exact overclaim this project spends most of its effort avoiding."""
    assert "verified against a live service" in verify.catalogue_state()


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------
def test_the_report_names_the_next_action_for_a_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(verify, "REPORT", tmp_path / "r.md")
    verify.write_report([
        verify.Outcome("ons", "ONS release URLs", "fail", 3.0,
                       "FAIL private_rents 404", "Open the dataset page and "
                       "copy the current file URL."),
    ], "51 of 269 factors real")
    text = (tmp_path / "r.md").read_text()
    assert "FAIL private_rents 404" in text, "the detail must survive"
    assert "copy the current file URL" in text, "so must the fix"


def test_the_report_is_written_even_when_everything_is_offline(tmp_path, monkeypatch):
    """The run still has to leave something behind — otherwise a trip that
    found nothing is indistinguishable from a trip that never happened."""
    monkeypatch.setattr(verify, "REPORT", tmp_path / "r.md")
    verify.write_report([
        verify.Outcome("ons", "ONS release URLs", "offline", 1.0, "ProxyError", "x"),
    ], "51 of 269 factors real")
    assert (tmp_path / "r.md").exists()


def test_a_passing_check_is_listed_as_something_to_promote(tmp_path, monkeypatch):
    """A pass is not the end of the job — it is permission to move factors from
    `written` to `verified`, which is the number that has been stuck at 1 since
    NDVI. A report that just says "passed" lets the run end there."""
    monkeypatch.setattr(verify, "REPORT", tmp_path / "r.md")
    verify.write_report([
        verify.Outcome("open-data", "Open data (22 factors)", "pass", 40.0, "", ""),
    ], "51 of 269 factors real")
    text = (tmp_path / "r.md").read_text()
    assert "Open data (22 factors)" in text
    assert "`written` to `verified`" in text, \
        "a pass must say what it now permits, or nothing is promoted"
