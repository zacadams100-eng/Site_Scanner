"""
The investigation workspace, and the proof that it is domain-agnostic.

Two of these tests matter more than the rest.

`test_a_coastal_investigation_assembles_with_no_land_assumptions` builds a
workspace for a domain this codebase has never seen — shoreline retreat — from
fabricated metadata alone. If it ever requires a change to `investigation.py`
to pass, the abstraction has been broken and the diff is the evidence.

`test_the_workspace_module_contains_no_domain_vocabulary` scans the module for
land words. It is crude and cannot tell a good abstraction from a bad one; it
catches the realistic failure, which is someone writing "the site" into a
label at 5pm.

Together they are the executable form of the constraint this feature was built
under: *the workspace must render an investigation without knowing whether the
subject is land, habitat, infrastructure, mining or coastline.*
"""

import ast
import pathlib

import investigation

GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[
        [-0.58, 51.235], [-0.56, 51.235], [-0.56, 51.245],
        [-0.58, 51.245], [-0.58, 51.235],
    ]],
}


def fetch(client, factor_ids=("ndvi",)):
    r = client.post("/api/series", json={
        "geometry": GEOMETRY, "factor_ids": list(factor_ids)})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# The abstraction, proven rather than claimed
# ---------------------------------------------------------------------------
def test_a_coastal_investigation_assembles_with_no_land_assumptions():
    """A domain this repository does not implement, assembled from metadata.

    Nothing here exists in `catalog.py`, `radar.RULES` or any rule: the
    subject is a stretch of shoreline, the factor is a retreat rate, the
    investigation is a coastal process study. If `investigation.report` can
    assemble it unchanged, the workspace genuinely carries no land assumptions
    — which is the claim `docs/VERTICAL_DISCOVERY.md` rests on and the one this
    feature was built to keep true.
    """
    radar_payload = {
        "investigations": [{
            "id": "coastal_process_study",
            "name": "Coastal process study",
            "blurb": "Sediment transport, wave climate and the retreat record.",
            "next_step": "Commission a coastal process study covering the frontage.",
            "priority": "high",
            "why": ["shoreline_retreat"],
        }],
        "flags": [{
            "id": "shoreline_retreat",
            "text": "Mean high water has retreated 14 m since the baseline period.",
            "severity": "high",
            "threshold": "10 m retreat (Contour reporting threshold)",
            "factors": ["shoreline_position"],
            "rule_meta": {
                "rule": "Shoreline retreat",
                "threshold_type": "Contour reporting threshold",
                "threshold_status": "product-defined; not a regulatory standard",
                "method_version": "coast-1",
                "not_evidence_of": "It is not evidence of accelerating erosion.",
            },
        }],
    }
    entries = [{
        "factor": "shoreline_position",
        "name": "Mean high water position",
        "state": "flagged",
        "assessed_at": "2026-08-10T00:00:00+00:00",
        "source": {"publisher": "Copernicus / ESA",
                   "endpoint": "earthengine.googleapis.com",
                   "dataset": "Sentinel-2 Surface Reflectance",
                   "licence": "CC BY-SA 3.0 IGO", "attribution": "…",
                   "runtime": "verified", "kind": "earth-engine"},
        "findings": [{"id": "shoreline_retreat", "kind": "flag",
                      "text": "Mean high water has retreated 14 m.",
                      "threshold": "10 m retreat",
                      "evidence": {"retreat_m": -14.0},
                      "rule_meta": radar_payload["flags"][0]["rule_meta"]}],
        "claims": {
            "established": ["Mean high water has retreated 14 m."],
            "not_established": ["It is not evidence of accelerating erosion."],
        },
    }]

    out = investigation.report(radar_payload, entries)
    assert len(out) == 1

    work = out[0]
    assert work["name"] == "Coastal process study"
    assert work["priority"] == "high"
    assert work["raised_by"][0]["rule"] == "Shoreline retreat"
    assert work["raised_by"][0]["method"] == "coast-1"
    assert work["established"] == ["Mean high water has retreated 14 m."]
    assert work["not_established"] == ["It is not evidence of accelerating erosion."]

    pack = work["evidence"][0]
    assert pack["name"] == "Mean high water position"
    assert pack["publisher"] == "Copernicus / ESA"
    assert pack["measurements"][0]["evidence"] == {"retreat_m": -14.0}


def test_the_workspace_module_contains_no_domain_vocabulary():
    """Crude on purpose. It catches the realistic failure — a land word
    written into a label — not a subtle design flaw."""
    # Docstrings and comments are stripped with `ast` rather than by matching
    # line prefixes. The prose in this module *has* to name the domains it
    # stays neutral about — "it must not know whether the subject is land or
    # coastline" is the specification — so a naive scan fails on the sentence
    # that states the rule. What is scanned is code and the strings that reach
    # a user: identifiers, keys and labels.
    tree = ast.parse(pathlib.Path(investigation.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:] or [ast.Pass()]
    code = ast.unparse(tree)
    for word in ("site", "planning", "development", "land", "property",
                 "parcel", "consent", "developer"):
        assert word not in code.lower(), (
            f"domain vocabulary '{word}' reached the workspace engine; it must "
            "enter through injected metadata (radar.INVESTIGATIONS, rule_meta)"
        )


def test_the_workspace_imports_nothing_domain_specific():
    """Structural, and stronger than the scan: a module that cannot see the
    catalogue cannot develop an opinion about what a factor means."""
    text = pathlib.Path(investigation.__file__).read_text(encoding="utf-8")
    for banned in ("import catalog", "import radar", "import open_data",
                   "import licensing"):
        assert banned not in text, f"{banned} couples the workspace to a domain"


# ---------------------------------------------------------------------------
# The chain, over the real payload
# ---------------------------------------------------------------------------
def test_the_workspace_answers_the_questions_in_order(mock_client, live_ndvi):
    """Why am I seeing this → what does it establish → what does it not →
    what prompted it → what to check → what to take along."""
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))
    body = fetch(mock_client)

    work = investigation.find(body["workspace"], "ecology_survey")
    assert work, "a flagged vegetation decline must raise an investigation"

    # Why am I seeing this — every raising finding, named by its rule.
    assert work["raised_by"], "an investigation with no cause is free advice"
    assert all(r["rule"] for r in work["raised_by"])

    # What it establishes, and what it does not (EM12, taken not recomposed).
    assert work["established"] and work["not_established"]

    # What prompted it — threshold, its kind, and the method behind it.
    hist = next(r for r in work["raised_by"] if r["method"] == "hist-1")
    assert hist["threshold_type"] == "Contour reporting threshold"
    assert "not a regulatory" in hist["threshold_status"]

    # What to check, and what to take along.
    assert work["next_step"]
    pack = work["evidence"][0]
    assert pack["publisher"] and pack["endpoint"] and pack["assessed_at"]


def test_the_claim_boundary_is_taken_never_recomposed(mock_client, live_ndvi):
    """EM12: one canonical wording. The workspace is a view over findings that
    already carry a boundary, so it unions rather than rewrites."""
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))
    body = fetch(mock_client)

    work = investigation.find(body["workspace"], "ecology_survey")
    entry = next(e for e in body["evidence"] if e["factor"] == "ndvi")
    for clause in entry["claims"]["not_established"]:
        assert clause in work["not_established"]


def test_a_factor_read_by_two_rules_appears_once_in_the_pack(mock_client, live_ndvi):
    """One NDVI series carries two rules. The professional is handed one
    evidence entry for it, not two."""
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))
    body = fetch(mock_client)

    work = investigation.find(body["workspace"], "ecology_survey")
    factors = [e["factor"] for e in work["evidence"]]
    assert len(factors) == len(set(factors))
    # Both rules are still visible, under the one factor.
    assert len(work["evidence"][0]["measurements"]) >= 2


def test_no_investigation_without_a_finding(mock_client):
    """EM8. Every entry traces to what raised it; a workspace with no flags is
    empty rather than encouraging."""
    body = fetch(mock_client)
    for work in body["workspace"]:
        assert work["raised_by"], f"{work['id']} is free-floating advice"


def test_the_workspace_states_no_conclusion(mock_client, live_ndvi):
    """It prepares the professional's question; it does not answer it."""
    from tests.test_historical_end_to_end import declining
    live_ndvi(declining(0.61, 0.47))
    body = fetch(mock_client)

    prose = repr(body["workspace"]).lower()
    for forbidden in ("suitable for", "we recommend developing", "safe to",
                      "no risk", "site is sound"):
        assert forbidden not in prose
