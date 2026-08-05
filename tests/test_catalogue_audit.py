"""
The audit runs in CI, not just when someone remembers to run it.

"Real" is the strongest claim this application makes and it is made 46 times.
A mislabel is not a crash — nothing breaks, a number just quietly acquires an
authority it has not earned — so the only way it gets caught is a test.

`scripts/audit_catalogue.py` documents what each check is for.
"""

import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "audit_catalogue", ROOT / "scripts" / "audit_catalogue.py")
audit_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit_mod)


@pytest.fixture(scope="module")
def audited():
    registry, provenance = audit_mod.build_registry()
    findings, summary = audit_mod.audit(registry, provenance)
    return registry, provenance, findings, summary


def test_no_factor_makes_a_claim_it_cannot_back(audited):
    _, _, findings, _ = audited
    failures = [f"{fid}: {detail}" for sev, fid, detail in findings if sev == "fail"]
    assert not failures, "\n".join(failures)


def test_the_only_warnings_are_the_known_sentinel_licence_question(audited):
    """Warnings are allowed, but not anonymous. Every one here should trace to
    an open question someone has written down — today that is Sentinel-2's
    licence, in docs/licensing/DECISION-LOG.md. A warning about anything else
    means something new appeared and nobody noticed."""
    _, _, findings, _ = audited
    unexpected = [(fid, detail) for sev, fid, detail in findings
                  if sev == "warn" and "sentinel2_sr" not in detail]
    assert not unexpected, f"undocumented warnings: {unexpected}"


def test_every_real_factor_says_whether_anyone_has_run_it(audited):
    """The distinction the whole provenance mechanism exists for. A factor may
    be `written`; it may not be silent about which it is."""
    registry, provenance, _, _ = audited
    for factor_id in registry:
        status = provenance[factor_id]["status"]
        assert status in ("verified", "written"), f"{factor_id}: {status!r}"


def test_the_open_data_factors_are_not_yet_claimed_as_verified(audited):
    """They have never been run against a live endpoint — this environment
    cannot reach any of the five hosts. If someone promotes them, they should
    have run scripts/check_open_data.py first and this test should be updated
    deliberately, not discovered to be failing."""
    _, provenance, _, _ = audited
    open_data_factors = [f for f, p in provenance.items()
                         if "earthengine" not in p["endpoint"]]
    assert open_data_factors, "the open-data factors did not register at all"
    claimed = [f for f in open_data_factors
               if provenance[f]["status"] == "verified"]
    assert not claimed, (
        f"{claimed} claim to be verified; run scripts/check_open_data.py and "
        "record the run in docs/OPEN-DATA.md before promoting them")


def test_the_publisher_and_the_endpoint_are_both_recorded(audited):
    """They differ for 46 of 46 real factors — everything real in this
    catalogue is served by someone other than whoever published it."""
    registry, provenance, _, _ = audited
    for factor_id in registry:
        prov = provenance[factor_id]
        assert prov["source"], factor_id
        assert prov["endpoint"], factor_id


def test_the_summary_the_ui_shows_adds_up(audited):
    """The ratio in the factor browser comes from these numbers. If they do not
    sum to the catalogue, the interface is showing arithmetic that is wrong in
    a way users can check."""
    import catalog

    _, _, _, summary = audited
    assert summary["real"] + summary["generated"] == len(catalog.FACTORS)
    assert summary["verified"] + summary["written"] == summary["real"]
    assert 0 < summary["real_share"] < 1


def test_the_api_reports_the_same_ratio_the_audit_computes():
    """Two independent paths to the same number: the audit builds its own
    registry, the API reports whatever the running backend registered. They
    must agree, or the UI is showing something the audit never checked."""
    from fastapi.testclient import TestClient

    import mock_ee_backend
    import routes_catalog

    client = TestClient(mock_ee_backend.app)
    body = client.get("/api/catalog").json()
    summary = body["summary"]

    assert summary["real_factor_count"] == len(routes_catalog.REAL_SERIES)
    assert (summary["real_factor_count"] + summary["generated_factor_count"]
            == summary["factor_count"])
    for factor in body["factors"]:
        if factor["real"]:
            assert factor["provenance"]["source"], factor["id"]
            assert factor["provenance"]["status"] in ("verified", "written")
        else:
            assert "provenance" not in factor, (
                f"{factor['id']} is generated but carries provenance")
