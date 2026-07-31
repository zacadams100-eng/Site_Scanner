"""
Contour — site summary generation
---------------------------------
Turns a computed site report into one plain-English paragraph.

Shared by app.py (real Earth Engine backend) and mock_ee_backend.py, so the
frontend gets an identical contract either way.

The API key lives here, server-side, and never reaches the browser. If
ANTHROPIC_API_KEY is not set — or the anthropic package isn't installed, or
the call fails — a deterministic paragraph is written from the same figures
instead, so the report panel always has something to show.

  pip install anthropic
  export ANTHROPIC_API_KEY="sk-ant-..."
"""

import os
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

MODEL = "claude-opus-5"

# Thinking is on by default on this model and counts against max_tokens
# alongside the response text, so the ceiling is well above what one
# paragraph needs.
MAX_TOKENS = 8000

# ESA WorldCover code -> human label, for prose rather than raw codes.
WORLDCOVER_LABELS: Dict[str, str] = {
    "10": "tree cover",
    "20": "shrubland",
    "30": "grassland",
    "40": "cropland",
    "50": "built-up land",
    "60": "bare or sparsely vegetated ground",
    "70": "snow and ice",
    "80": "open water",
    "90": "herbaceous wetland",
    "95": "mangroves",
    "100": "moss and lichen",
}

SYSTEM_PROMPT = """You write short site notes for UK land agents, developers \
and habitat bank operators doing early-stage Biodiversity Net Gain screening.

Write exactly one paragraph of plain English, under 120 words. No headings, \
no bullet points, no preamble — start with the substance.

Ground every claim in the figures you are given. Do not invent numbers, \
designations, planning history, or site names. If the figures are weak or \
ambiguous, say so rather than padding.

Say what the land appears to be, what stands out for BNG purposes, and \
whether it looks worth a closer look. Where a figure is flagged as simulated \
or as a proxy, do not present it as measured fact.

Close by noting this is an automated screen from satellite data, not a \
Biodiversity Metric assessment or a substitute for a site visit."""


class SummaryRequest(BaseModel):
    """Everything the frontend already computed, so the server doesn't
    recompute it and the paragraph matches what the user is looking at."""

    year: int
    stats: dict                          # the /api/stats payload
    score: Optional[dict] = None         # {"overall": int, "band": str, "categories": [...]}
    simulated: Optional[dict] = None     # layers with no real backing, e.g. {"Solar potential": "1043 kWh/m²/yr"}


# ---------------------------------------------------------------------------
# Turning the payload into something readable
# ---------------------------------------------------------------------------
def _composition(histogram: Dict[str, Any]) -> List[str]:
    """Land cover as descending 'grassland 46%' strings."""
    if not histogram:
        return []
    total = sum(float(v) for v in histogram.values()) or 1.0
    parts = sorted(
        ((code, float(v) / total * 100.0) for code, v in histogram.items()),
        key=lambda kv: kv[1],
        reverse=True,
    )
    return [
        f"{WORLDCOVER_LABELS.get(code, f'class {code}')} {pct:.0f}%"
        for code, pct in parts
        if pct >= 0.5
    ]


def _flood_band(value: Optional[float]) -> str:
    if value is None:
        return "unknown"
    if value < 0.15:
        return "low"
    if value < 0.35:
        return "moderate"
    if value < 0.6:
        return "elevated"
    return "high"


def _ndvi_band(value: Optional[float]) -> str:
    if value is None:
        return "unknown"
    if value < 0.3:
        return "sparse"
    if value < 0.5:
        return "moderate"
    if value < 0.68:
        return "healthy"
    return "dense"


def build_prompt(req: SummaryRequest) -> str:
    stats = req.stats or {}
    lines: List[str] = [f"Year analysed: {req.year}"]

    area = stats.get("area_ha")
    if area is not None:
        lines.append(f"Area: {float(area):.2f} hectares")

    ndvi = stats.get("ndvi_mean")
    if ndvi is not None:
        lines.append(
            f"Mean NDVI (vegetation vigour): {float(ndvi):.3f} — {_ndvi_band(float(ndvi))}"
        )

    composition = _composition(stats.get("landcover_histogram") or {})
    if composition:
        lines.append("Land cover (ESA WorldCover): " + ", ".join(composition))

    flood = stats.get("flood_proxy_mean")
    if flood is not None:
        lines.append(
            f"Flood proxy: {float(flood):.3f} — {_flood_band(float(flood))}. "
            "This is a surface-water-and-elevation proxy, NOT Environment Agency flood zone data."
        )

    if req.score:
        overall = req.score.get("overall")
        band = req.score.get("band")
        if overall is not None:
            lines.append(f"Screening score: {overall}/100 ({band})")
        for cat in req.score.get("categories") or []:
            flag = " [SIMULATED — not from satellite data]" if cat.get("simulated") else ""
            lines.append(f"  - {cat.get('name')}: {cat.get('score')}/100{flag}")

    if req.simulated:
        lines.append(
            "Simulated layers (illustrative only, no real data source): "
            + ", ".join(f"{k} {v}" for k, v in req.simulated.items())
        )

    return "Site screening figures:\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Fallback — used when no API key is configured, or the call fails
# ---------------------------------------------------------------------------
def fallback_summary(req: SummaryRequest) -> str:
    stats = req.stats or {}
    area = float(stats.get("area_ha") or 0.0)
    ndvi = stats.get("ndvi_mean")
    flood = stats.get("flood_proxy_mean")
    composition = _composition(stats.get("landcover_histogram") or {})

    bits: List[str] = [
        f"This {area:.1f} ha parcel reads as "
        + (
            f"{composition[0].rsplit(' ', 1)[0]}-dominated"
            if composition
            else "mixed land cover"
        )
        + f" in the {req.year} imagery"
    ]
    if len(composition) > 1:
        bits.append(f", with {' and '.join(composition[1:3])} making up the balance")
    bits.append(". ")

    if ndvi is not None:
        bits.append(
            f"Mean NDVI of {float(ndvi):.2f} indicates {_ndvi_band(float(ndvi))} "
            "vegetation cover across the growing season. "
        )
    if flood is not None:
        band = _flood_band(float(flood))
        article = "an" if band[0] in "aeiou" else "a"
        bits.append(
            f"The flood proxy sits at {float(flood):.2f}, {article} {band} "
            "reading — though that is a surface-water and elevation proxy rather than "
            "Environment Agency flood zone data. "
        )

    if req.score and req.score.get("overall") is not None:
        overall = req.score["overall"]
        bits.append(
            f"The combined screening score of {overall}/100 puts this in the "
            f"{str(req.score.get('band', 'unclassified')).lower()} band"
        )
        bits.append(
            ", which is worth a closer look. "
            if overall >= 55
            else ", so temper expectations before committing survey budget. "
        )

    bits.append(
        "Treat all of the above as an automated satellite screen, not a Biodiversity "
        "Metric assessment or a substitute for a site visit."
    )
    return "".join(bits)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def generate_summary(req: SummaryRequest) -> Dict[str, Any]:
    """Returns {"summary", "generated_by", "model"}.

    generated_by is "claude" when the model wrote it and "fallback" when the
    deterministic text was used, so the frontend can label it honestly.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {
            "summary": fallback_summary(req),
            "generated_by": "fallback",
            "model": None,
            "detail": "ANTHROPIC_API_KEY is not set — using the deterministic summary.",
        }

    try:
        import anthropic
    except ImportError:
        return {
            "summary": fallback_summary(req),
            "generated_by": "fallback",
            "model": None,
            "detail": "The anthropic package is not installed — using the deterministic summary.",
        }

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            # One short paragraph from a handful of numbers — low effort keeps
            # this fast and cheap without disabling thinking entirely.
            output_config={"effort": "low"},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_prompt(req)}],
        )

        if response.stop_reason == "refusal":
            return {
                "summary": fallback_summary(req),
                "generated_by": "fallback",
                "model": MODEL,
                "detail": "The model declined this request — using the deterministic summary.",
            }

        text = "\n".join(
            block.text for block in response.content if block.type == "text"
        ).strip()
        if not text:
            raise ValueError("The model returned no text content")

        return {"summary": text, "generated_by": "claude", "model": MODEL}

    except Exception as e:  # network, auth, rate limit, truncation — all recoverable
        return {
            "summary": fallback_summary(req),
            "generated_by": "fallback",
            "model": MODEL,
            "detail": f"{type(e).__name__}: {e}",
        }
