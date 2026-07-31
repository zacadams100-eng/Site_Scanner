"""
summary.py — the site-note endpoint.

No network: the Anthropic client is stubbed, so these cover the branch
selection and the prompt, not the model's prose.
"""

import types

import pytest

from summary import (
    MODEL,
    SummaryRequest,
    build_prompt,
    fallback_summary,
    generate_summary,
)

STATS = {
    "ndvi_mean": 0.62,
    "landcover_histogram": {"30": 7000.0, "40": 2500.0, "50": 500.0},
    "flood_proxy_mean": 0.18,
    "area_ha": 100.0,
}
SCORE = {
    "overall": 58,
    "band": "Good baseline",
    "categories": [
        {"name": "Habitat quality", "score": 52, "simulated": False},
        {"name": "Solar potential", "score": 71, "simulated": True},
    ],
}


def req(**kw):
    return SummaryRequest(**{"year": 2024, "stats": STATS, **kw})


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------
def test_prompt_carries_every_figure():
    p = build_prompt(req(score=SCORE))
    assert "2024" in p
    assert "100.00 hectares" in p
    assert "0.620" in p
    assert "58/100" in p


def test_prompt_uses_labels_not_raw_esa_codes():
    p = build_prompt(req())
    assert "grassland" in p and "cropland" in p and "built-up" in p
    assert "class 30" not in p


def test_prompt_orders_land_cover_by_share():
    p = build_prompt(req())
    line = next(l for l in p.splitlines() if l.startswith("Land cover"))
    assert line.index("grassland") < line.index("cropland") < line.index("built-up")


def test_prompt_flags_simulated_categories():
    p = build_prompt(req(score=SCORE))
    solar = next(l for l in p.splitlines() if "Solar potential" in l)
    assert "SIMULATED" in solar
    habitat = next(l for l in p.splitlines() if "Habitat quality" in l)
    assert "SIMULATED" not in habitat


def test_prompt_marks_the_flood_figure_as_a_proxy():
    """The model must not describe this as Environment Agency flood data."""
    p = build_prompt(req())
    assert "NOT Environment Agency" in p


def test_prompt_handles_missing_figures():
    p = build_prompt(SummaryRequest(year=2024, stats={}))
    assert "2024" in p          # no KeyError, no invented numbers
    assert "hectares" not in p


# ---------------------------------------------------------------------------
# Fallback text
# ---------------------------------------------------------------------------
def test_fallback_mentions_the_real_numbers():
    text = fallback_summary(req(score=SCORE))
    assert "100.0 ha" in text
    assert "0.62" in text
    assert "58/100" in text


def test_fallback_always_carries_the_disclaimer():
    assert "not a Biodiversity Metric" in fallback_summary(req())


def test_fallback_is_grammatical_for_every_flood_band():
    """'a elevated reading' — the article has to agree."""
    for proxy in (0.05, 0.25, 0.45, 0.9):
        text = fallback_summary(req(stats={**STATS, "flood_proxy_mean": proxy}))
        assert " a elevated " not in text
        assert " a unknown " not in text


def test_fallback_survives_empty_stats():
    text = fallback_summary(SummaryRequest(year=2024, stats={}))
    assert isinstance(text, str) and text


# ---------------------------------------------------------------------------
# Branch selection
# ---------------------------------------------------------------------------
def test_no_api_key_uses_the_fallback(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = generate_summary(req())
    assert out["generated_by"] == "fallback"
    assert out["model"] is None
    assert "ANTHROPIC_API_KEY" in out["detail"]


def _stub_anthropic(monkeypatch, *, content=None, stop_reason="end_turn", raises=None):
    """Install a fake anthropic module so no network call is made."""
    captured = {}

    class FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            if raises:
                raise raises
            return types.SimpleNamespace(
                stop_reason=stop_reason,
                content=content if content is not None else
                [types.SimpleNamespace(type="text", text="A grassland-dominated parcel.")],
            )

    class FakeAnthropic:
        def __init__(self, *a, **k):
            self.messages = FakeMessages()

    monkeypatch.setitem(
        __import__("sys").modules, "anthropic", types.SimpleNamespace(Anthropic=FakeAnthropic)
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    return captured


def test_uses_claude_when_a_key_is_present(monkeypatch):
    captured = _stub_anthropic(monkeypatch)
    out = generate_summary(req(score=SCORE))
    assert out["generated_by"] == "claude"
    assert out["model"] == MODEL
    assert out["summary"] == "A grassland-dominated parcel."


def test_request_parameters(monkeypatch):
    captured = _stub_anthropic(monkeypatch)
    generate_summary(req())

    assert captured["model"] == MODEL
    # max_tokens caps thinking *and* response text on this model, so it needs
    # far more headroom than one paragraph would suggest.
    assert captured["max_tokens"] >= 4000
    assert captured["output_config"] == {"effort": "low"}
    assert captured["messages"][0]["role"] == "user"
    assert "Site screening figures" in captured["messages"][0]["content"]
    assert "under 120 words" in captured["system"]


def test_no_key_is_ever_sent_from_the_request_body(monkeypatch):
    """The key comes from the environment, never from the caller."""
    captured = _stub_anthropic(monkeypatch)
    generate_summary(req())
    assert "api_key" not in captured


def test_refusal_falls_back(monkeypatch):
    _stub_anthropic(monkeypatch, stop_reason="refusal", content=[])
    out = generate_summary(req())
    assert out["generated_by"] == "fallback"
    assert "declined" in out["detail"]
    assert out["summary"]


def test_api_error_falls_back(monkeypatch):
    _stub_anthropic(monkeypatch, raises=RuntimeError("connection reset"))
    out = generate_summary(req())
    assert out["generated_by"] == "fallback"
    assert "connection reset" in out["detail"]
    assert out["summary"]


def test_empty_response_falls_back(monkeypatch):
    _stub_anthropic(monkeypatch, content=[])
    out = generate_summary(req())
    assert out["generated_by"] == "fallback"
    assert out["summary"]


def test_thinking_blocks_are_ignored(monkeypatch):
    """Only text blocks are prose; a thinking block must not leak into the UI."""
    _stub_anthropic(monkeypatch, content=[
        types.SimpleNamespace(type="thinking", thinking="internal reasoning"),
        types.SimpleNamespace(type="text", text="The visible paragraph."),
    ])
    out = generate_summary(req())
    assert out["summary"] == "The visible paragraph."
    assert "internal reasoning" not in out["summary"]


def test_missing_anthropic_package_falls_back(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("No module named 'anthropic'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    out = generate_summary(req())
    assert out["generated_by"] == "fallback"
    assert "not installed" in out["detail"]


# ---------------------------------------------------------------------------
# Response contract
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("with_key", [True, False])
def test_response_always_has_the_same_keys(monkeypatch, with_key):
    if with_key:
        _stub_anthropic(monkeypatch)
    else:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = generate_summary(req())
    assert {"summary", "generated_by", "model"} <= set(out)
    assert out["generated_by"] in ("claude", "fallback")


# ---------------------------------------------------------------------------
# Caveats — where the screen is weak. These matter most because the paragraph
# is the artefact a land agent is most likely to forward to a client.
# ---------------------------------------------------------------------------
CAVEAT = ("Grassland is 62% of the site. Grassland spans modified pasture "
          "through to species-rich meadow.")


def test_caveats_reach_the_prompt():
    p = build_prompt(req(caveats=[CAVEAT]))
    assert "Known limits of this screen" in p
    assert CAVEAT in p


def test_system_prompt_requires_caveats_to_be_honoured():
    from summary import SYSTEM_PROMPT

    assert "limit of the screen" in SYSTEM_PROMPT
    assert "forward this note to a client" in SYSTEM_PROMPT


def test_caveats_reach_the_fallback_text():
    assert CAVEAT in fallback_summary(req(caveats=[CAVEAT]))


def test_caveats_are_optional():
    assert "Known limits" not in build_prompt(req())
    assert fallback_summary(req(caveats=[]))


def test_caveats_survive_the_round_trip(monkeypatch):
    captured = _stub_anthropic(monkeypatch)
    generate_summary(req(caveats=[CAVEAT]))
    assert CAVEAT in captured["messages"][0]["content"]
