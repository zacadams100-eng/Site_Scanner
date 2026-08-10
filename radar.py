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

## 2. Three outcomes, never two

Every topic reports `flagged`, `clear`, or `not_assessed`. A radar that lists
only what it found reads as "we looked at everything and this is what is
wrong". Silence would then mean safety, and here silence usually means
**Terrain: every slope factor in this catalogue is generated**. Saying "not
assessed, and here is why" is the entire difference between a tool that helps
and a tool that gets someone sued.

`not_assessed` distinguishes two causes, because one is fixable in a click:

- `not_selected` — the layer isn't in this report. Add it and re-run.
- `demo_data` — the factor exists but is generated. Nothing the user can do.

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

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import insights

#: Severity of a flag, worst first. Also the priority scale for investigations.
SEVERITIES = ("high", "medium", "low")


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
    },
    "drainage_strategy": {
        "name": "Drainage strategy and SuDS",
        "blurb": "How surface water leaves the site, and where it goes.",
    },
    "watercourse_check": {
        "name": "Watercourse and consent check",
        "blurb": "Standing or seasonal water may bring ordinary watercourse "
                 "consent, byelaw margins or a land drainage consent.",
    },
    "ground_investigation": {
        "name": "Ground investigation",
        "blurb": "Intrusive site investigation — boreholes, trial pits, "
                 "geotechnical and contamination sampling.",
    },
    "contamination_desk_study": {
        "name": "Phase 1 contamination desk study",
        "blurb": "Historical maps, landfill records and previous uses, to "
                 "establish whether intrusive work is warranted.",
    },
    "topographic_survey": {
        "name": "Topographic survey",
        "blurb": "Measured levels across the site. The only reliable source of "
                 "slope and fall.",
    },
    "ecology_survey": {
        "name": "Preliminary ecological appraisal",
        "blurb": "Habitat survey, protected species scoping, and the baseline "
                 "a BNG calculation is built on.",
    },
    "arboricultural_survey": {
        "name": "Arboricultural survey",
        "blurb": "Tree survey to BS 5837, and the constraints protected trees "
                 "place on a layout.",
    },
    "planning_history": {
        "name": "Planning history review",
        "blurb": "What has been applied for here and nearby, what was granted, "
                 "and on what grounds anything was refused.",
    },
    "heritage_statement": {
        "name": "Heritage statement",
        "blurb": "Assessment of effect on designated heritage assets and their "
                 "setting.",
    },
    "landscape_appraisal": {
        "name": "Landscape and visual appraisal",
        "blurb": "How the site reads in a protected or sensitive landscape.",
    },
    "policy_review": {
        "name": "Planning policy review",
        "blurb": "The development plan position for this parcel, and what it "
                 "permits in principle.",
    },
    "utilities_search": {
        "name": "Utilities search",
        "blurb": "Buried services, easements and wayleaves crossing the site.",
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
    for p in series.get("points") or []:
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
                 investigations: Sequence[str], asks: str) -> None:
        self.id = id
        self.topic = topic
        self.needs = tuple(needs)
        self.test = test
        self.investigations = tuple(investigations)
        #: What this rule is looking for, in one line. Shown against a topic
        #: that could not be assessed, so "not assessed" says what was missed.
        self.asks = asks


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


RULES: Tuple[Rule, ...] = (
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
           real_capable: Optional[set] = None) -> Dict[str, Any]:
    """Run every rule over a report and assemble the radar.

    `real_capable` is the set of factor ids the server has a real
    implementation for; pass it so an "add this layer" suggestion is never made
    for a layer that would come back generated. See `_state_of`.

    Rules that raise are flags; rules that ran and found nothing make their
    topic `clear`; rules that could not run make it `not_assessed`. A topic
    takes the strongest of those three, in that order, so one clear check
    never hides a flag and one flag is never softened by four clear ones.
    """
    series = (report or {}).get("series") or {}

    flags: List[Dict[str, Any]] = []
    # topic -> the states its rules reached
    topic_states: Dict[str, List[str]] = {t: [] for t in TOPICS}
    checked: Dict[str, List[str]] = {t: [] for t in TOPICS}
    unavailable: List[Dict[str, Any]] = []

    for rule in RULES:
        state, reason, blocking = _state_of(rule, series, real_capable)
        if state == "not_assessed":
            topic_states.setdefault(rule.topic, []).append("not_assessed")
            unavailable.append({
                "rule": rule.id,
                "topic": rule.topic,
                "topic_name": TOPICS.get(rule.topic, rule.topic),
                "asks": rule.asks,
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
                       "it again." if reason == "not_selected" else
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

        checked.setdefault(rule.topic, []).extend(rule.needs)
        if not found:
            topic_states.setdefault(rule.topic, []).append("clear")
            continue

        topic_states.setdefault(rule.topic, []).append("flagged")
        flags.append({
            "id": rule.id,
            "topic": rule.topic,
            "topic_name": TOPICS.get(rule.topic, rule.topic),
            "severity": found["severity"],
            "text": found["text"],
            "evidence": found.get("evidence", {}),
            "factors": list(rule.needs),
            "provenance": _provenance_for(rule.needs, series),
            "investigations": list(rule.investigations),
        })

    flags.sort(key=lambda f: (_rank(f["severity"]), f["topic"]))

    topics = []
    for tid, name in TOPICS.items():
        states = topic_states.get(tid, [])
        if "flagged" in states:
            state = "flagged"
        elif "clear" in states:
            state = "clear"
        else:
            state = "not_assessed"
        topics.append({
            "id": tid,
            "name": name,
            "state": state,
            "flags": sum(1 for f in flags if f["topic"] == tid),
            "checked": sorted(set(checked.get(tid, []))),
        })

    return {
        "flags": flags,
        "topics": topics,
        "investigations": _investigations(flags),
        "not_assessed": unavailable,
        "counts": {
            "flags": len(flags),
            "high": sum(1 for f in flags if f["severity"] == "high"),
            "topics_flagged": sum(1 for t in topics if t["state"] == "flagged"),
            "topics_clear": sum(1 for t in topics if t["state"] == "clear"),
            "topics_not_assessed": sum(1 for t in topics
                                       if t["state"] == "not_assessed"),
        },
        "limits": LIMITS,
    }


def _investigations(flags: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The checks the flags prompt, ranked, each naming what raised it.

    Priority is the strongest severity among the flags that raised it, with one
    promotion: a `medium` raised by two or more separate flags becomes `high`.
    Converging evidence from independent observations is genuinely stronger
    than either alone — standing water *and* a brownfield entry both pointing
    at ground investigation is a different case from one of them. The promotion
    only ever runs medium → high; a pile of low-severity flags never becomes
    urgent by accumulation, because that is how a checklist turns into noise.
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
        if priority == "medium" and len({c["id"] for c in causes}) >= 2:
            priority = "high"
        out.append({
            "id": inv_id,
            "name": meta["name"],
            "blurb": meta["blurb"],
            "priority": priority,
            "why": [c["id"] for c in causes],
            "why_text": [c["text"] for c in causes],
        })

    out.sort(key=lambda i: (_rank(i["priority"]), -len(i["why"]), i["name"]))
    return out
