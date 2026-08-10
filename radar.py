"""
Investigation radar — what about this site deserves a closer look.

`insights.py` reads a report and says what the numbers did. This asks the next
question, which is the one people actually arrive with: **is there anything
here I should investigate before I commit money to it?**

It produces two things:

- **Flags.** Observations that cross a stated threshold. "31% of this site is
  in Flood Zone 3." Each one carries the value, the threshold it crossed, the
  factors it came from and how well those factors have been proven.
- **Investigations.** The standard surveys and searches those flags would
  normally prompt, ranked. Nothing appears here unless a flag raised it, and
  each one names which flags did.

That is the move from GIS to decision support, and it is also the most
dangerous thing in this codebase, because a flag is *judgement-shaped*. A
percentage is checkable; "⚠️ Flood" is a conclusion, and people act on
conclusions without checking them. `LEGAL_RISK_REGISTER.md` L4 records exactly
this hazard for the 30 generated `suitability`/`risk`/`flag` factors. So four
rules hold this module up, and none of them is negotiable.

## 1. A flag may only come from real data

If the series behind a rule is generated, the rule does not fire — it reports
`not_assessed`. It never fires with a "demo data" caveat attached, because a
caveat protects a *measurement* ("NDVI fell 12%, demo data") far better than it
protects a *recommendation* ("commission a ground investigation, demo data").
The first invites a check; the second has already done the damage by the time
anyone reads the parenthesis.

## 2. Four outcomes, never one

A radar that lists only what it found reads as "we looked at everything and
this is what is wrong". Silence would then mean safety, and here silence
usually means **Terrain: every slope factor in this catalogue is generated**.
So a finding is one of four things:

- `flagged` — crossed a threshold, and it is worth acting on.
- `clear` — **checked against a real source and found below threshold.**
- `informational` — measured, and neither good nor bad. Site area, mean NDVI,
  dominant land cover. Without these the radar is only a problem-finder, and a
  tool that can exclusively deliver bad news is one people stop opening.
- `not_assessed` — not looked at. Split by cause, because one is a click and
  the other is a wall: `not_selected` (add the layer and re-run) and
  `demo_data` (the factor is generated; nothing the user can do).

**`clear` is the load-bearing one.** "Generated data indicates no flood risk"
is not the same claim as "we checked the Environment Agency's dataset and found
none", and the two must never render as the same green tick. So `clear`
requires real *and* assessed *and* below threshold. Anything else is
`not_assessed`. `test_generated_data_can_never_produce_a_clear` guards it.

A topic gets `partial` when some of its checks ran and others could not — a
topic with two checks where only one ran is not a clear topic, and calling it
one is the same overstatement one level up.

## 3. An investigation must trace to a flag

No free-floating advice. `why` lists the flag ids that raised it, so every
recommendation can be walked back to the number underneath it.

## 4. It prompts, it does not conclude

These are the checks a surveyor would normally run given these observations —
not an opinion on whether the site is suitable, developable or safe. The
thresholds are Contour's own reporting thresholds, chosen to be legible, and
they are **not** regulatory tests. `LIMITS` says so in the payload, and says
what this cannot see, because the honest reading of an empty radar is "nothing
crossed a threshold in the layers you loaded" and never "this site is fine".
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import insights

#: Severity of a flag, worst first. Also the priority scale for investigations.
SEVERITIES = ("high", "medium", "low")

#: The product's whole philosophy in two sentences, served with every report so
#: it travels into any UI, export or integration rather than living in a design
#: document nobody reads. It is also the answer to "what makes you different
#: from a risk score", which is the question a professional buyer asks.
PRINCIPLE = ("A clear result means we checked. "
             "An empty result means we could not.")


def _rank(sev: str) -> int:
    return SEVERITIES.index(sev) if sev in SEVERITIES else len(SEVERITIES)


# ---------------------------------------------------------------------------
# Topics
# ---------------------------------------------------------------------------
#: Declared independently of the rules, so a topic no rule can currently answer
#: still appears in the output as `not_assessed`. If topics were derived from
#: the rules that ran, Terrain would silently vanish from a report — and a
#: missing heading is indistinguishable from a clean one.
TOPICS: Dict[str, str] = {
    "flood": "Flood",
    "water": "Surface water",
    "ground": "Ground and historical land use",
    "terrain": "Terrain",
    "vegetation": "Vegetation",
    "ecology": "Habitats and designations",
    "planning": "Planning and heritage",
}


# ---------------------------------------------------------------------------
# Investigations
# ---------------------------------------------------------------------------
#: The recognised name for each check, so a user can put it in an email to a
#: consultant without translating. Deliberately the standard UK terms.
INVESTIGATIONS: Dict[str, Dict[str, str]] = {
    "flood_risk_assessment": {
        "name": "Flood risk assessment",
        "blurb": "A site-specific FRA is normally required where any part of a "
                 "site falls in Flood Zone 2 or 3.",
        "next_step": "Commission or review a site-specific flood risk assessment.",
    },
    "drainage_strategy": {
        "name": "Drainage strategy and SuDS",
        "blurb": "How surface water leaves the site, and where it goes.",
        "next_step": "Ask a drainage engineer for an outline surface-water strategy.",
    },
    "watercourse_check": {
        "name": "Watercourse and consent check",
        "blurb": "Standing or seasonal water may bring ordinary watercourse "
                 "consent, byelaw margins or a land drainage consent.",
        "next_step": "Check the lead local flood authority's ordinary watercourse register.",
    },
    "ground_investigation": {
        "name": "Ground investigation",
        "blurb": "Intrusive site investigation — boreholes, trial pits, "
                 "geotechnical and contamination sampling.",
        "next_step": "Scope an intrusive site investigation with a geotechnical engineer.",
    },
    "contamination_desk_study": {
        "name": "Phase 1 contamination desk study",
        "blurb": "Historical maps, landfill records and previous uses, to "
                 "establish whether intrusive work is warranted.",
        "next_step": "Order a Phase 1 desk study with historical mapping.",
    },
    "topographic_survey": {
        "name": "Topographic survey",
        "blurb": "Measured levels across the site. The only reliable source of "
                 "slope and fall.",
        "next_step": "Commission a measured topographic survey.",
    },
    "ecology_survey": {
        "name": "Preliminary ecological appraisal",
        "blurb": "Habitat survey, protected species scoping, and the baseline "
                 "a BNG calculation is built on.",
        "next_step": "Instruct a preliminary ecological appraisal, ideally in season.",
    },
    "arboricultural_survey": {
        "name": "Arboricultural survey",
        "blurb": "Tree survey to BS 5837, and the constraints protected trees "
                 "place on a layout.",
        "next_step": "Commission a BS 5837 tree survey before fixing a layout.",
    },
    "planning_history": {
        "name": "Planning history review",
        "blurb": "What has been applied for here and nearby, what was granted, "
                 "and on what grounds anything was refused.",
        "next_step": "Search the local authority's planning register for this site and its neighbours.",
    },
    "heritage_statement": {
        "name": "Heritage statement",
        "blurb": "Assessment of effect on designated heritage assets and their "
                 "setting.",
        "next_step": "Instruct a heritage consultant to assess setting and significance.",
    },
    "landscape_appraisal": {
        "name": "Landscape and visual appraisal",
        "blurb": "How the site reads in a protected or sensitive landscape.",
        "next_step": "Commission a landscape and visual appraisal.",
    },
    "policy_review": {
        "name": "Planning policy review",
        "blurb": "The development plan position for this parcel, and what it "
                 "permits in principle.",
        "next_step": "Read the adopted local plan allocation and policies for this parcel.",
    },
    "utilities_search": {
        "name": "Utilities search",
        "blurb": "Buried services, easements and wayleaves crossing the site.",
        "next_step": "Order a utilities search from the statutory undertakers.",
    },
}


# ---------------------------------------------------------------------------
# Reading a series
# ---------------------------------------------------------------------------
def _real_values(series: Dict[str, Any]) -> List[Tuple[str, float]]:
    """(period, value) for genuine observations — no gaps, no carried-forward.

    Same exclusion as `insights._real_points`, for the same reason: a census
    figure held flat across 144 months is not 144 observations.
    """
    out: List[Tuple[str, float]] = []
    points = series.get("points")
    # A malformed series must not raise here. This is called from `_state_of`,
    # which runs *outside* the try/except that guards rule execution — so a
    # `points` that is a string rather than a list would take down the whole
    # radar rather than one rule, and the radar is a nicety over a report the
    # user has already paid for.
    if not isinstance(points, list):
        return out
    for p in points:
        if not isinstance(p, dict):
            continue
        if p.get("value") is None or p.get("interpolated"):
            continue
        try:
            out.append((p["t"], float(p["value"])))
        except (TypeError, ValueError):
            continue
    return out


def _level(series: Dict[str, Any]) -> Optional[Tuple[str, float]]:
    """The value that describes the site now.

    For a designation — green belt, a conservation area — every point is the
    same figure and any one of them will do. For a measured series it is the
    most recent real observation. Returns the period too, because "3% of the
    site is water" and "3% of the site was water in March 2019" are different
    claims and only one of them is defensible.
    """
    values = _real_values(series)
    if not values:
        return None
    return values[-1]


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs)


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------
class Insufficient:
    """A rule ran and could not evaluate.

    `None` cannot carry two meanings. "I evaluated and found nothing" and "I
    could not evaluate" are different epistemic states with opposite
    consequences — the first is a `clear` and the second is a `not_assessed` —
    and collapsing them into one falsy return is how a live series with two
    usable years produced a clean bill of health.

    A class rather than a dict key, so the distinction is visible at the call
    site and cannot be created by a typo in a string.
    """

    __slots__ = ("reason",)

    def __init__(self, reason: str) -> None:
        #: A sentence a user reads. What was missing, not merely that
        #: something was.
        self.reason = reason


class Rule:
    """One thing worth noticing, and what it would prompt.

    `needs` is the factors the test cannot run without. Every one of them must
    be in the report *and* real, or the rule reports `not_assessed` rather than
    guessing from what it does have — a flood rule that quietly drops Zone 3
    and answers from Zone 2 alone is worse than one that says it could not
    look.
    """

    def __init__(self, id: str, topic: str, needs: Sequence[str],
                 test: Callable[[Dict[str, Dict[str, Any]]], Optional[Dict[str, Any]]],
                 investigations: Sequence[str], asks: str,
                 kind: str = "flag",
                 meta: Optional[Dict[str, Any]] = None) -> None:
        self.id = id
        self.topic = topic
        self.needs = tuple(needs)
        self.test = test
        self.investigations = tuple(investigations)
        #: What this rule is looking for, in one line. Shown against a topic
        #: that could not be assessed, so "not assessed" says what was missed.
        self.asks = asks
        #: `flag` — crosses a threshold and may raise an investigation.
        #: `info` — a measured fact that is neither good nor bad. An info rule
        #: never raises an investigation and never sets a topic to flagged; it
        #: is still bound by the real-data rule, because "generated data says
        #: this site averages 61 m elevation" is a fabricated fact about a real
        #: place whether or not anyone would act on it.
        self.kind = kind
        #: What the rule is, for the evidence drawer — its threshold, what kind
        #: of threshold that is, and what it is for. Carried onto every flag it
        #: raises, so the distinction between *the measurement* and *Contour's
        #: decision to surface the measurement* is visible rather than implied.
        self.meta = dict(meta or {})


def _pct(v: float) -> str:
    return f"{v:.0f}%" if v >= 1 else f"{v:.1f}%"


# --- Flood ------------------------------------------------------------------
def _flood(s: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    z3 = _level(s["flood_zone3_pct"])
    if z3 is None:
        return None
    period, pct = z3
    if pct <= 0:
        return None
    # Any intersection at all is material: Flood Zone 3 is an Environment
    # Agency designation, and a site that touches it is treated differently by
    # the planning system regardless of how much of it does. The bands below
    # are Contour's own, for wording only — they are not a regulatory test.
    severity = "high" if pct >= 5 else "medium"
    return {
        "severity": severity,
        "text": (f"{_pct(pct)} of this site intersects Flood Zone 3, the "
                 f"Environment Agency's highest-probability fluvial and tidal "
                 f"zone."),
        "evidence": {"flood_zone3_pct": pct, "threshold": "any intersection",
                     "as_of": period},
    }


def _flood_zone2(s: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    z2 = _level(s["flood_zone2_pct"])
    if z2 is None:
        return None
    period, pct = z2
    if pct < 5:
        return None
    return {
        "severity": "medium",
        "text": (f"{_pct(pct)} of this site intersects Flood Zone 2 — the "
                 f"medium-probability zone, which is wider than Zone 3 and "
                 f"still engages the sequential test."),
        "evidence": {"flood_zone2_pct": pct, "threshold": "5%",
                     "as_of": period},
    }


# --- Surface water ----------------------------------------------------------
def _standing_water(s: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    occ = _level(s["water_occurrence"])
    if occ is None:
        return None
    period, pct = occ
    if pct < 2:
        return None
    severity = "high" if pct >= 15 else "medium"
    return {
        "severity": severity,
        "text": (f"Open water was present over {_pct(pct)} of this site in the "
                 f"satellite record — persistent enough to be a watercourse, "
                 f"pond or wet ground rather than a one-off wet week."),
        "evidence": {"water_occurrence_pct": pct, "threshold": "2%",
                     "as_of": period},
    }


def _seasonal_water(s: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    seas = _level(s["water_seasonality"])
    if seas is None:
        return None
    period, months = seas
    if months < 1:
        return None
    return {
        "severity": "medium" if months >= 3 else "low",
        "text": (f"Water is present here for about {months:.0f} months of a "
                 f"typical year and absent for the rest — seasonal wet ground, "
                 f"which a single site visit in summer would miss entirely."),
        "evidence": {"water_seasonality_months": months, "threshold": "1 month",
                     "as_of": period},
    }


# --- Ground and historical land use ----------------------------------------
def _previously_developed(s: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """A built or stripped signature earlier in the record than now.

    The classic brownfield tell from imagery: ground that read as built-up or
    bare a decade ago and reads as vegetation today. It is a *prompt to check
    the history*, not a finding that the land is contaminated — which is why it
    raises a desk study rather than a remediation estimate.
    """
    ndbi = _real_values(s["ndbi"])
    bare = _real_values(s["bare_soil_index"])
    if len(ndbi) < 24 or len(bare) < 24:
        return None

    third = max(6, len(ndbi) // 3)
    early_built, late_built = _mean([v for _, v in ndbi[:third]]), _mean([v for _, v in ndbi[-third:]])
    third_b = max(6, len(bare) // 3)
    early_bare = _mean([v for _, v in bare[:third_b]])
    late_bare = _mean([v for _, v in bare[-third_b:]])

    # Both indices have to agree. Either one alone moves with drought, crop
    # rotation and harvest; a built-up signature that fell *and* a bare-soil
    # signature that fell is a change in what the ground is, not what the
    # weather was.
    built_drop = early_built - late_built
    bare_drop = early_bare - late_bare
    if built_drop < 0.05 or bare_drop < 0.05:
        return None

    return {
        "severity": "medium",
        "text": ("Earlier imagery reads as more built-up and more bare ground "
                 "than recent imagery does, which is the signature of land "
                 "that was previously developed or stripped and has since "
                 "greened over."),
        "evidence": {
            "ndbi_early": round(early_built, 3), "ndbi_recent": round(late_built, 3),
            "bare_soil_early": round(early_bare, 3),
            "bare_soil_recent": round(late_bare, 3),
            "threshold": "both indices down by 0.05 or more",
            "window": f"{ndbi[0][0]} to {ndbi[-1][0]}",
        },
    }


def _brownfield_register(s: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    reg = _level(s["brownfield_register_pct"])
    if reg is None:
        return None
    period, pct = reg
    if pct <= 0:
        return None
    return {
        "severity": "medium",
        "text": (f"{_pct(pct)} of this site sits on land the local authority "
                 f"has entered on its brownfield land register — a formal "
                 f"record that it was previously developed."),
        "evidence": {"brownfield_register_pct": pct,
                     "threshold": "any intersection", "as_of": period},
    }


# --- Terrain ----------------------------------------------------------------
def _steep_ground(s: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Written, and currently unreachable — by design.

    Every slope factor in this catalogue is generated, so this rule reports
    `not_assessed` on every run. It exists rather than being omitted for two
    reasons: the radar can then *name* what it could not check, and the day
    `slope_max` becomes real the rule starts working with no code change. A
    rule that is waiting is more honest than a heading that is missing.
    """
    level = _level(s["slope_max"])
    if level is None:
        return None
    period, deg = level
    if deg < 8:
        return None
    return {
        "severity": "medium" if deg < 15 else "high",
        "text": (f"Ground here reaches about {deg:.0f}° at its steepest, which "
                 f"affects earthworks, access gradients and drainage falls."),
        "evidence": {"slope_max_deg": deg, "threshold": "8°", "as_of": period},
    }


# --- Vegetation -------------------------------------------------------------
def _vegetation_decline(s: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """A significant downward NDVI trend.

    Delegates to `insights.trend` rather than fitting its own line, so the
    significance test that stops this narrating noise is the same one the
    Findings tab uses. Two components of the product must not disagree about
    whether a trend exists.
    """
    found = insights.trend({**s["ndvi"], "factor_id": "ndvi"})
    if not found or found.get("slope_per_step", 0) >= 0:
        return None
    pct = found.get("pct_change")
    if pct is None or abs(pct) < 10:
        return None
    return {
        "severity": "medium" if abs(pct) < 25 else "high",
        "text": (f"Vegetation vigour across this site has fallen about "
                 f"{abs(pct):.0f}% over the record. Loss of cover has a cause "
                 f"— drainage, works, grazing change or dieback — and which "
                 f"one it is matters."),
        "evidence": {"ndvi_pct_change": round(pct, 1), "r2": found.get("r2"),
                     "t": found.get("t"), "n": found.get("n"),
                     "threshold": "10% decline, significant at |t| ≥ 2"},
    }


# --- Habitats and designations ---------------------------------------------
def _designation(field: str, label: str, severity: str,
                 investigations: Sequence[str], topic: str, rule_id: str,
                 asks: str) -> Rule:
    """A rule for "any part of this site is inside X".

    Most designations work identically — the only things that vary are the
    name, how serious it is and what it prompts — so they are generated from
    one function rather than written out seven times with seven chances to get
    the percentage formatting subtly different.
    """
    def test(s: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        level = _level(s[field])
        if level is None:
            return None
        period, pct = level
        if pct <= 0:
            return None
        return {
            "severity": severity,
            "text": f"{_pct(pct)} of this site {label}",
            "evidence": {field: pct, "threshold": "any intersection",
                         "as_of": period},
        }

    return Rule(rule_id, topic, [field], test, investigations, asks)


def _listed_density(s: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    level = _level(s["listed_building_density"])
    if level is None:
        return None
    period, density = level
    if density < 2:
        return None
    return {
        "severity": "medium",
        "text": (f"Listed buildings stand at about {density:.0f} per km² "
                 f"around this site. Setting is a material consideration even "
                 f"where no listed building is on the site itself."),
        "evidence": {"listed_building_density": density, "threshold": "2 per km²",
                     "as_of": period},
    }


def _planning_pressure(s: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Nearby application activity — written, currently unreachable.

    This is the "multiple planning applications within 250m" check. It needs
    `planning_apps`, which is generated today, so like `_steep_ground` it
    reports `not_assessed` and waits.
    """
    apps = _real_values(s["planning_apps"])
    if not apps:
        return None
    recent = [v for _, v in apps[-12:]]
    total = sum(recent)
    if total < 3:
        return None
    return {
        "severity": "low",
        "text": (f"About {total:.0f} planning applications have been made "
                 f"nearby in the last year. What was granted and what was "
                 f"refused is the cheapest read on what this authority will "
                 f"accept here."),
        "evidence": {"applications_12m": total, "threshold": "3"},
    }


# --- Informational ----------------------------------------------------------
def _info(field: str, topic: str, rule_id: str, label: str, asks: str,
          fmt: Callable[[float], str] = lambda v: f"{v:,.1f}") -> Rule:
    """A measured fact, stated without judgement.

    These exist so the radar is not exclusively a problem-finder. A tool that
    can only ever deliver bad news is one people stop opening, and "78%
    grassland" is the sort of thing a land agent writes down first.

    Bound by the same real-data rule as a flag. A generated informational
    finding is still a fabricated fact about a real place — it merely omits the
    step where someone acts on it.
    """
    def test(s: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        level = _level(s[field])
        if level is None:
            return None
        period, value = level
        # The period is part of the statement, not a footnote to it.
        #
        # An informational reading is the most recent observation, and for a
        # seasonal factor that is one month rather than a summary of the
        # record. Without the date, "Mean vegetation vigour: 0.21" sits beside
        # a historical baseline of 0.61 and reads as a contradiction — the two
        # are measuring different things and only one of them says so.
        return {
            "text": f"{label}: {fmt(value)} ({period})",
            "evidence": {field: value, "as_of": period,
                         "basis": "most recent observation"},
        }

    return Rule(rule_id, topic, [field], test, (), asks, kind="info")


RULES: Tuple[Rule, ...] = (
    # Informational first in the source, so it is obvious they are part of the
    # model rather than an afterthought bolted on beside the warnings.
    _info("lc_dominant", "vegetation", "info_land_cover", "Dominant land cover",
          "what the site is mostly covered by", fmt=lambda v: str(v)),
    _info("lc_tree_pct", "vegetation", "info_tree_cover", "Tree cover",
          "how much of the site is trees", fmt=lambda v: f"{v:.0f}% of the site"),
    _info("ndvi", "vegetation", "info_ndvi", "Mean vegetation vigour (NDVI)",
          "the site's average greenness", fmt=lambda v: f"{v:.2f}"),
    _info("elevation_mean", "terrain", "info_elevation", "Mean elevation",
          "how high the site sits", fmt=lambda v: f"{v:,.0f} m"),
    _info("built_pct", "ground", "info_built", "Built surface",
          "how much of the site is built on",
          fmt=lambda v: f"{v:.0f}% of the site"),
    Rule("flood_zone3", "flood", ["flood_zone3_pct"], _flood,
         ["flood_risk_assessment", "drainage_strategy"],
         "whether any of the site lies in Flood Zone 3"),
    Rule("flood_zone2", "flood", ["flood_zone2_pct"], _flood_zone2,
         ["flood_risk_assessment"],
         "whether any of the site lies in Flood Zone 2"),
    Rule("standing_water", "water", ["water_occurrence"], _standing_water,
         ["watercourse_check", "drainage_strategy", "ecology_survey"],
         "whether open water is present on the site"),
    Rule("seasonal_water", "water", ["water_seasonality"], _seasonal_water,
         ["drainage_strategy", "ground_investigation"],
         "whether the site is seasonally wet"),
    Rule("previously_developed", "ground", ["ndbi", "bare_soil_index"],
         _previously_developed,
         ["contamination_desk_study", "ground_investigation", "utilities_search"],
         "whether imagery suggests earlier developed or stripped ground"),
    Rule("brownfield_register", "ground", ["brownfield_register_pct"],
         _brownfield_register,
         ["contamination_desk_study", "planning_history"],
         "whether the site is on a brownfield land register"),
    Rule("steep_ground", "terrain", ["slope_max"], _steep_ground,
         ["topographic_survey", "ground_investigation"],
         "whether any part of the site is steeply sloping"),
    Rule("vegetation_decline", "vegetation", ["ndvi"], _vegetation_decline,
         ["ecology_survey"],
         "whether vegetation cover has declined over the record"),
    _designation("sssi_pct", "is within a Site of Special Scientific Interest, "
                 "which brings statutory consultation and consent requirements.",
                 "high", ["ecology_survey", "policy_review"], "ecology",
                 "sssi", "whether the site is within an SSSI"),
    _designation("ancient_woodland_pct", "is ancient woodland — an irreplaceable "
                 "habitat that national policy protects from loss or "
                 "deterioration.", "high",
                 ["ecology_survey", "arboricultural_survey", "policy_review"],
                 "ecology", "ancient_woodland",
                 "whether the site contains ancient woodland"),
    _designation("national_park_pct", "is within a National Park.", "medium",
                 ["landscape_appraisal", "policy_review"], "ecology",
                 "national_park", "whether the site is within a National Park"),
    _designation("aonb_pct", "is within a National Landscape (formerly AONB).",
                 "medium", ["landscape_appraisal", "policy_review"], "ecology",
                 "aonb", "whether the site is within a National Landscape"),
    _designation("green_belt_pct", "is designated Green Belt, where most new "
                 "building is inappropriate development by default.", "high",
                 ["policy_review", "planning_history"], "planning",
                 "green_belt", "whether the site is Green Belt"),
    _designation("conservation_area_pct", "is within a conservation area, which "
                 "restricts demolition and alters permitted development "
                 "rights.", "medium",
                 ["heritage_statement", "planning_history", "arboricultural_survey"],
                 "planning", "conservation_area",
                 "whether the site is in a conservation area"),
    _designation("scheduled_monument_pct", "is a scheduled monument. Works "
                 "affecting one need scheduled monument consent, separately "
                 "from planning permission.", "high",
                 ["heritage_statement", "planning_history"], "planning",
                 "scheduled_monument",
                 "whether the site contains a scheduled monument"),
    _designation("article4_pct", "is covered by an Article 4 direction, which "
                 "withdraws permitted development rights.", "medium",
                 ["planning_history", "policy_review"], "planning",
                 "article4", "whether an Article 4 direction applies"),
    _designation("tpo_density", "carries tree preservation orders — protected "
                 "trees constrain layout and cannot be felled without "
                 "consent.", "medium",
                 ["arboricultural_survey", "ecology_survey"], "planning",
                 "tpo", "whether protected trees are present"),
    Rule("listed_buildings", "planning", ["listed_building_density"],
         _listed_density, ["heritage_statement", "planning_history"],
         "whether listed buildings stand on or near the site"),
    Rule("planning_pressure", "planning", ["planning_apps"], _planning_pressure,
         ["planning_history"],
         "how much application activity there has been nearby"),
)


def _rules_from(module_name: str) -> Tuple[Rule, ...]:
    """Rules contributed by another package.

    The engine collects rules; it does not know what they measure. There is no
    branch anywhere below that asks whether a rule came from here — a
    contributed rule is an ordinary `Rule` and travels the identical path, which
    is the architectural point of `HISTORICAL_EVIDENCE_MODEL.md`.

    `build(Rule)` is called with the class rather than the package importing
    `radar` itself, so the direction of knowledge stays one-way and there is no
    circular import to work around.

    A contributing package that fails to import must not take the radar down
    with it: the rules it would have added are simply absent, and every topic
    they served reports `not_assessed` — which is the honest outcome and the
    one the whole model is built to produce.
    """
    try:
        module = __import__(module_name, fromlist=["build"])
        return tuple(module.build(Rule, Insufficient))
    except Exception:                                       # noqa: BLE001
        return ()


RULES = RULES + _rules_from("historical.rules")


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
#: Sources that count as a real observation. Same list as `routes_catalog`
#: uses for `real_factors`; a flag is only ever raised from one of these.
REAL_SOURCES = ("earth-engine", "open-data")

LIMITS = (
    "This lists what crossed a threshold in the layers loaded, nothing more. "
    "An empty radar means nothing crossed a threshold — not that the site is "
    "sound. Thresholds are Contour's own reporting thresholds, chosen to be "
    "legible; they are not regulatory tests, and the investigations named are "
    "the checks these observations would normally prompt rather than "
    "professional advice on this site. Flags are raised only from real data: "
    "anything marked not assessed was not looked at."
)


def _state_of(rule: Rule, series: Dict[str, Any],
              real_capable: Optional[set] = None) -> Tuple[str, Optional[str], List[str]]:
    """Can this rule run, and if not, whose fault is it.

    Returns `(state, reason, blocking_factor_ids)`. The distinction between
    "you didn't load it" and "we generated it" is the useful part: one is a
    click, the other is a wall.

    `real_capable` is the set of factor ids the server can actually fetch real
    data for. Without it, a factor that is *both* unselected and generated
    reports `not_selected`, and the UI offers an "add this layer" button that
    leads straight to "not assessed — demo data". Promising a check that cannot
    be delivered is a smaller lie than a false flag, but it is the same kind,
    and it is the kind this module exists to refuse.
    """
    missing = [f for f in rule.needs if f not in series]
    if missing:
        if real_capable is not None:
            hopeless = [f for f in missing if f not in real_capable]
            if hopeless:
                return "not_assessed", "demo_data", hopeless
        return "not_assessed", "not_selected", missing
    demo = [f for f in rule.needs
            if (series[f] or {}).get("source") not in REAL_SOURCES]
    if demo:
        return "not_assessed", "demo_data", demo
    # A real source that answered with nothing is not a clean result. Letting
    # the rule run would produce no finding, which reads as "checked, clear" —
    # the same false zero as reporting 0% for an unreadable geometry, one level
    # up. The service was asked and did not answer; say that.
    silent = [f for f in rule.needs if not _real_values(series[f] or {})]
    if silent:
        return "not_assessed", "no_data", silent
    return "ready", None, []


def _catalog_name(factor_id: str) -> str:
    """A factor's display name, for a suggestion about a layer not in the
    report — there is no series to read the name off, and "Add
    flood_zone2_pct" is a database column, not a sentence."""
    try:
        import catalog
        return catalog.FACTOR_BY_ID.get(factor_id, {}).get("name") or factor_id
    except Exception:                                       # noqa: BLE001
        return factor_id


def _provenance_for(needs: Sequence[str], series: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Where each number came from and how well it has been proven.

    A flag from a `verified` factor and a flag from a `written` one look
    identical on screen unless this travels with them, and they are not the
    same claim — `written` means implemented against the documented API and
    never yet run against the live service.
    """
    out = []
    for fid in needs:
        s = series.get(fid) or {}
        prov = s.get("provenance") or {}
        out.append({
            "factor": fid,
            "name": (s.get("meta") or {}).get("name") or fid,
            "source": s.get("source"),
            "publisher": prov.get("source"),
            "endpoint": prov.get("endpoint"),
            "status": prov.get("status", "unknown"),
        })
    return out


def assess(report: Dict[str, Any],
           real_capable: Optional[set] = None,
           *,
           topic_names: Optional[Dict[str, str]] = None,
           rules: Optional[Sequence["Rule"]] = None) -> Dict[str, Any]:
    """Run every rule over a report and assemble the radar.

    `real_capable` is the set of factor ids the server has a real
    implementation for; pass it so an "add this layer" suggestion is never made
    for a layer that would come back generated. See `_state_of`.

    A rule either raises a flag, states an informational fact, comes back clear,
    or could not run. A topic takes the strongest of those, and gets `partial`
    when some of its checks ran and others could not — a topic with two checks
    where only one ran is not a clear topic.
    """
    series = (report or {}).get("series") or {}
    at = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")

    # The scanner's vocabulary and checks. Defaulted to this module's own so
    # every existing caller is unaffected, and injectable so a second scanner
    # is a configuration rather than a fork. The engine below reads only these
    # two names; it has never known what a topic means.
    topic_names = TOPICS if topic_names is None else topic_names
    rules = RULES if rules is None else rules

    flags: List[Dict[str, Any]] = []
    info: List[Dict[str, Any]] = []
    # topic -> the states its rules reached
    topic_states: Dict[str, List[str]] = {t: [] for t in topic_names}
    checked: Dict[str, List[str]] = {t: [] for t in topic_names}
    unavailable: List[Dict[str, Any]] = []
    # Per-topic ledger of every risk check and what became of it. "Flood:
    # flagged" hides whether one indicator was read or three; a professional
    # needs to know that Zone 3 was assessed and Zone 2 was not, because those
    # are different statements about the same site.
    topic_checks: Dict[str, List[Dict[str, Any]]] = {t: [] for t in topic_names}
    # The audit trail: one row per factor any rule wanted, and what became of
    # it. Written here rather than reconstructed by the UI, because "why did
    # the report say that in August" is a question with one correct answer and
    # the server is the only place that knows it.
    log: Dict[str, Dict[str, Any]] = {}

    def record(fid: str, state: str) -> None:
        if fid in log and log[fid]["state"] == "assessed":
            return
        s = series.get(fid) or {}
        prov = s.get("provenance") or {}
        log[fid] = {
            "factor": fid,
            "name": (s.get("meta") or {}).get("name") or _catalog_name(fid),
            "state": state,
            "publisher": prov.get("source"),
            "endpoint": prov.get("endpoint"),
            # `verified` means someone ran it against the live service and
            # checked the answer. `written` does not.
            "status": prov.get("status") if state == "assessed" else None,
            "source": s.get("source"),
            "at": at,
        }

    for rule in rules:
        state, reason, blocking = _state_of(rule, series, real_capable)
        names = [(series.get(f) or {}).get("meta", {}).get("name")
                 or _catalog_name(f) for f in rule.needs]
        if rule.kind == "flag":
            topic_checks.setdefault(rule.topic, []).append({
                "rule": rule.id,
                "asks": rule.asks,
                "indicators": names,
                "assessed": state != "not_assessed",
                "reason": reason,
            })
        if state == "not_assessed":
            # Only a *risk* check can leave a topic incompletely screened. An
            # unmeasured informational fact — tree cover, mean elevation — is
            # not a gap in the screening, and letting it set `partial` made a
            # topic read "1/1, partly checked", which is a contradiction the
            # user has to resolve rather than a finding.
            topic_states.setdefault(rule.topic, []).append(
                "not_assessed" if rule.kind == "flag" else "info_missing")
            for f in rule.needs:
                record(f, "generated" if (reason == "demo_data" and f in blocking)
                       else "not_selected" if f in blocking else "assessed")
            unavailable.append({
                "rule": rule.id,
                "topic": rule.topic,
                "topic_name": topic_names.get(rule.topic, rule.topic),
                "asks": rule.asks,
                # Which investigations this check would have contributed to had
                # it run. Without this a workspace can show the evidence behind
                # an investigation but not the evidence *missing* from it, and
                # a reader would take the pack as complete — the same false
                # completeness the coverage strip exists to prevent, one level
                # in. The rule already knows; it was simply never exposed.
                "investigations": list(rule.investigations),
                "reason": reason,
                "factors": blocking,
                "factor_names": [
                    (series.get(f) or {}).get("meta", {}).get("name")
                    or _catalog_name(f) for f in blocking],
                # The sentence a user reads. Two different fixes, so two
                # different sentences — never one vague "unavailable".
                "text": (
                    f"Not assessed — {rule.asks}. "
                    + ("Add " + ", ".join(blocking) + " to this report and run "
                       "it again." if reason == "not_selected"
                       else "The source returned no usable observation for this "
                       "area, so nothing was concluded from it."
                       if reason == "no_data" else
                       "The data behind it is generated demo data, so no flag "
                       "can honestly be raised from it.")),
            })
            continue

        try:
            found = rule.test({f: series[f] for f in rule.needs})
        except Exception:                                   # noqa: BLE001
            # A radar is a nicety over a report the user already has. One bad
            # number must never take the whole response down — same rule as
            # insights.for_series.
            continue

        # A rule that ran but could not evaluate is not a clear result.
        #
        # `_state_of` can only see whether the inputs exist and are real; it
        # cannot know that a rule needs six usable years and found two. Without
        # this branch, such a rule returns None and the engine reads it as
        # "checked, nothing found" — the same false zero as EM6, arriving one
        # layer higher. General on purpose: any rule may declare insufficient
        # evidence, and the engine does not know or care which one did.
        if isinstance(found, Insufficient):
            topic_states.setdefault(rule.topic, []).append("not_assessed")
            for check in topic_checks.get(rule.topic, []):
                if check["rule"] == rule.id:
                    check["assessed"] = False
                    check["reason"] = "no_data"
            for f in rule.needs:
                record(f, "no_data")
            unavailable.append({
                "rule": rule.id,
                "topic": rule.topic,
                "topic_name": topic_names.get(rule.topic, rule.topic),
                "asks": rule.asks,
                "reason": "no_data",
                "factors": list(rule.needs),
                "factor_names": [
                    (series.get(f) or {}).get("meta", {}).get("name")
                    or _catalog_name(f) for f in rule.needs],
                "text": f"Not assessed — {rule.asks}. {found.reason}",
            })
            continue

        checked.setdefault(rule.topic, []).extend(rule.needs)
        for f in rule.needs:
            record(f, "assessed")

        if not found:
            # Reached only when every factor the rule needed was real and
            # present — see _state_of. This is the one place `clear` is
            # produced, which is what makes the invariant checkable.
            topic_states.setdefault(rule.topic, []).append(
                "clear" if rule.kind == "flag" else "info")
            continue

        if rule.kind == "info":
            topic_states.setdefault(rule.topic, []).append("info")
            info.append({
                "id": rule.id,
                "topic": rule.topic,
                "topic_name": topic_names.get(rule.topic, rule.topic),
                "text": found["text"],
                "evidence": found.get("evidence", {}),
                "factors": list(rule.needs),
                "provenance": _provenance_for(rule.needs, series),
            })
            continue

        topic_states.setdefault(rule.topic, []).append("flagged")
        flags.append({
            "id": rule.id,
            "topic": rule.topic,
            "topic_name": topic_names.get(rule.topic, rule.topic),
            "severity": found["severity"],
            "text": found["text"],
            "evidence": found.get("evidence", {}),
            "threshold": found.get("evidence", {}).get("threshold"),
            "factors": list(rule.needs),
            "provenance": _provenance_for(rule.needs, series),
            "investigations": list(rule.investigations),
            "rule_meta": rule.meta,
            "assessed_at": at,
        })

    flags.sort(key=lambda f: (_rank(f["severity"]), f["topic"]))

    topics = []
    for tid, name in topic_names.items():
        states = topic_states.get(tid, [])
        gaps = "not_assessed" in states
        if "flagged" in states:
            state = "flagged"
        elif "clear" in states:
            # Some checks ran and some did not. Calling that clear is the same
            # overstatement as calling a generated zero clear, one level up.
            state = "partial" if gaps else "clear"
        elif "info" in states and not gaps:
            # Measured something, screened nothing that could flag. Only
            # `clear` when the topic has no risk checks outstanding.
            state = "clear" if any(c["assessed"] for c in topic_checks.get(tid, [])) \
                    or not topic_checks.get(tid) else "not_assessed"
        else:
            state = "not_assessed"
        checks = topic_checks.get(tid, [])
        done = [c for c in checks if c["assessed"]]
        missed = [c for c in checks if not c["assessed"]]
        topics.append({
            "id": tid,
            "name": name,
            "state": state,
            "flags": sum(1 for f in flags if f["topic"] == tid),
            "checked": sorted(set(checked.get(tid, []))),
            # "2 / 3 indicators assessed" is what makes `flagged` and `clear`
            # mean something. Without it both are bare adjectives.
            "coverage": {"assessed": len(done), "total": len(checks)},
            "checks": checks,
            "detail": _topic_detail(done, missed),
            "informational": sum(1 for i in info if i["topic"] == tid),
        })

    rows = sorted(log.values(), key=lambda r: (r["state"] != "assessed", r["name"]))
    assessed = [r for r in rows if r["state"] == "assessed"]

    return {
        "flags": flags,
        "informational": info,
        "topics": topics,
        "investigations": _investigations(flags),
        "not_assessed": unavailable,
        # The audit trail. Every factor a rule wanted, what became of it, and
        # who published it — so a report read three months later can be
        # understood rather than trusted.
        "log": rows,
        "assessed_at": at,
        "coverage": _coverage(rows, assessed, flags, info),
        "counts": {
            "flags": len(flags),
            "high": sum(1 for f in flags if f["severity"] == "high"),
            "informational": len(info),
            "topics_flagged": sum(1 for t in topics if t["state"] == "flagged"),
            "topics_clear": sum(1 for t in topics if t["state"] == "clear"),
            "topics_partial": sum(1 for t in topics if t["state"] == "partial"),
            "topics_not_assessed": sum(1 for t in topics
                                       if t["state"] == "not_assessed"),
        },
        "principle": PRINCIPLE,
        "limits": LIMITS,
    }


#: Said wherever coverage is shown, and deliberately not optional. A percentage
#: on a screen becomes a score in a reader's head within about two seconds, and
#: a score is exactly what this number is not.
COVERAGE_NOTE = (
    "Coverage is how much of this site we were able to look at — not how good "
    "the site is. A site at 90% is not better than one at 50%; we simply know "
    "more about it."
)


def _topic_detail(done: Sequence[Dict[str, Any]],
                  missed: Sequence[Dict[str, Any]]) -> str:
    """One sentence naming what was read and what was not.

    This is what stops `clear` being a bare adjective. "Protected sites —
    clear, 3 of 3 assessed" is a finding; "Protected sites — clear" is a mood.
    Missed checks are separated by cause, because "not loaded" and "no live
    source" are different problems with different owners.
    """
    parts: List[str] = []
    if done:
        names = sorted({n for c in done for n in c["indicators"]})
        parts.append(_join(names) + (" was" if len(names) == 1 else " were")
                     + " assessed.")
    not_loaded = sorted({n for c in missed if c["reason"] == "not_selected"
                         for n in c["indicators"]})
    generated = sorted({n for c in missed if c["reason"] == "demo_data"
                        for n in c["indicators"]})
    if not_loaded:
        parts.append(_join(not_loaded) + (" was" if len(not_loaded) == 1
                                          else " were") + " not loaded.")
    silent = sorted({n for c in missed if c["reason"] == "no_data"
                     for n in c["indicators"]})
    if silent:
        parts.append(_join(silent) + (" returned" if len(silent) == 1
                                      else " returned")
                     + " no usable observation for this area.")
    if generated:
        one = len(generated) == 1
        parts.append(_join(generated) + (" has" if one else " have")
                     + " no live source, so nothing was claimed from "
                     + ("it." if one else "them."))
    return " ".join(parts)


def _join(items: Sequence[str]) -> str:
    if len(items) <= 1:
        return items[0] if items else ""
    return ", ".join(items[:-1]) + " and " + items[-1]


def _coverage(rows: Sequence[Dict[str, Any]], assessed: Sequence[Dict[str, Any]],
              flags: Sequence[Dict[str, Any]],
              info: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """How much of what this radar knows how to check, it actually checked.

    Denominator is the factors the rules wanted for *this* report, not the 273
    in the catalogue — "42 of 273" would be a meaningless number that made
    every site look unexamined.

    Deliberately **not** a score, and `COVERAGE_NOTE` travels with it saying so.
    The temptation to collapse this into "Site health: 72/100" is the single
    most commercially attractive wrong turn available to this product: a score
    hides its own inputs, and the entire argument for this tool is that it
    shows them.
    """
    total = len(rows)
    n_assessed = len(assessed)
    flagged_factors = {f for flag in flags for f in flag["factors"]}
    info_factors = {f for i in info for f in i["factors"]}
    clear = sum(1 for r in assessed
                if r["factor"] not in flagged_factors
                and r["factor"] not in info_factors)
    return {
        "relevant": total,
        "assessed": n_assessed,
        "share": round(n_assessed / total, 3) if total else 0.0,
        "flagged": len(flagged_factors),
        "clear": clear,
        "informational": len(info_factors),
        "not_assessed": total - n_assessed,
        # Split by cause, because one number is actionable and the other is not.
        "not_selected": sum(1 for r in rows if r["state"] == "not_selected"),
        "generated": sum(1 for r in rows if r["state"] == "generated"),
        "verified": sum(1 for r in assessed if r.get("status") == "verified"),
        "note": COVERAGE_NOTE,
    }


def outcome_for(payload: Dict[str, Any], rule_id: str) -> Dict[str, Any]:
    """What the engine decided for one rule, for a caller that needs to join.

    Read-only over an assembled payload. Exists so that a composition layer —
    a route, an export, a report — can pair a rule's numbers with its finding
    **without recomputing the finding**, which is EM11 applied one layer below
    the UI. Returns the state, the reason where there is one, and the flag
    itself where one was raised.
    """
    for flag in payload.get("flags") or []:
        if flag.get("id") == rule_id:
            return {"state": "flagged", "reason": None, "flag": flag}
    for entry in payload.get("not_assessed") or []:
        if entry.get("rule") == rule_id:
            return {"state": "not_assessed", "reason": entry.get("reason"),
                    "flag": None, "text": entry.get("text")}
    for item in payload.get("informational") or []:
        if item.get("id") == rule_id:
            return {"state": "informational", "reason": None, "flag": item}
    # A rule that is neither flagged nor unavailable ran and found nothing.
    return {"state": "clear", "reason": None, "flag": None}


def _investigations(flags: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The checks the flags prompt, ranked, each naming what raised it.

    Priority is the strongest severity among the flags that raised it, with one
    promotion: a `medium` raised by two or more flags **resting on different
    factors** becomes `high`.

    The factor condition is the whole of it. Standing water *and* a brownfield
    register entry both pointing at ground investigation is genuinely stronger
    than either alone, because they are independent observations. Two rules
    reading the same NDVI series — a trend test and a baseline-change test —
    are two methods on one measurement, and promoting on that is counting the
    same evidence twice. It looks identical in the payload, which is why the
    condition is on the factors rather than on the flag count.

    The promotion only ever runs medium → high; a pile of low-severity flags
    never becomes urgent by accumulation, because that is how a checklist turns
    into noise.
    """
    raised: Dict[str, List[Dict[str, Any]]] = {}
    for flag in flags:
        for inv in flag.get("investigations", []):
            raised.setdefault(inv, []).append(flag)

    out = []
    for inv_id, causes in raised.items():
        meta = INVESTIGATIONS.get(inv_id)
        if not meta:
            continue
        priority = min((c["severity"] for c in causes), key=_rank)
        independent = {f for c in causes for f in c["factors"]}
        if priority == "medium" and len(independent) >= 2:
            priority = "high"
        out.append({
            "id": inv_id,
            "name": meta["name"],
            "blurb": meta["blurb"],
            # What to actually do. A recommendation that stops at naming a
            # survey leaves the reader to work out who to ring.
            "next_step": meta.get("next_step", ""),
            # The factors behind it, so a reader can open the evidence rather
            # than take the recommendation on faith.
            "evidence_factors": sorted({f for c in causes for f in c["factors"]}),
            "priority": priority,
            "why": [c["id"] for c in causes],
            "why_text": [c["text"] for c in causes],
        })

    out.sort(key=lambda i: (_rank(i["priority"]), -len(i["why"]), i["name"]))
    return out
