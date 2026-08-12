"""
The scanner registry.

A scanner is a **configuration**, not a subclass and not a plugin. It names a
vocabulary, a set of checks, the follow-up investigations those checks prompt,
the factors it exposes and where it is valid. Everything else — the assessment
engine, evidence states, coverage, the claim boundary, the investigation
workspace, the brief — is shared and unchanged.

    Site Scanner
      → family        foundation · development · culture · economics
        → scanner     land · water · ecology · planning · …
          → domain    flood · coastal · habitat · woodland · …
            → shared assessment engine
            → shared evidence and provenance
            → shared investigation workspace
            → shared brief

## Why this is dataclasses and not a framework

`tests/test_multi_scanner_experiment.py` measured what was actually required to
run a second domain through the engine, and the answer was: a topic dict, a
rule sequence and an investigation dict. No lifecycle, no hooks, no base class,
no loader. Anything more would be an abstraction built for an imagined
requirement rather than a measured one — and `docs/MULTI_SCANNER_AUDIT.md`
records the measurement so the next person can check rather than trust.

The two structures added since — `Family` and `Domain` — are grouping and
composition. Neither introduces behaviour, and the engine still knows nothing
about either.

## Domains: where the taxonomy became real rather than a rename

The land scanner was carrying seven topics: flood, surface water, ground,
terrain, vegetation, ecology and planning. Twenty-five rules across all of
them. Those are not one subject, and calling them one was an artefact of land
having been built first — the specialist scanners were latent in the rule set
long before anyone drew the taxonomy.

So a **domain** is a named part of a scanner's subject, and a scanner is
composed from domains. Two kinds contribute content:

- **core** — topics of the shared rule set in `radar.py`, named by id.
- **package** — a contributing rules package (`habitat.rules`), through the
  same `radar.rules_from` contract `historical.rules` has always used.

A domain with neither is **declared**: it has a name, a subject, a reason it
has no evidence yet, and no ability to assess anything. Registering is not
implementing, and the registry says which is which rather than leaving a
reader to infer it from an empty report.

## Composition never copies

`_topics_of` and friends return the shared mapping itself when a scanner
covers all of it. A copy would be a second definition that drifts, and the
first symptom would be a rule that runs in tests and not in production. Where
a merge is genuinely required — a scanner drawing on two sources — the merge
is computed once at import and frozen.

## Overlap between scanners is deliberate, and it is not duplication

Flood belongs to Water. It also stays in Land, because Land is the foundation
scanner: the sweep you run when you do not yet know which specialist question
matters. A professional who runs Land and is not told about Flood Zone 3
because flood "moved to the water scanner" has been failed by a taxonomy.

The thing that makes this safe is that **a rule has exactly one definition**.
Land and Water share the *same* `Rule` object, selected by topic, never copied.
Two scanners cannot disagree about a threshold because there is only one
threshold. This is the lesson habitat already learned about importing
`VEGETATION_CHANGE_INVESTIGATION_THRESHOLD` rather than restating it, applied
at the level of the rule instead of the number.

## Migration aliases

`habitat`, `coastal`, `terrain` and `forestry` were top-level scanners. Three
of them are now domains and one is a planned domain, so their ids resolve to
the scanner that absorbed them: a saved link, a stored report or an API client
written against the old vocabulary keeps working, and `ALIASES` is the one
place that mapping exists. `Scanner.id` is always canonical, so nothing
downstream has to know an alias was used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

import catalog
import radar

# ---------------------------------------------------------------------------
# Families
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Family:
    """A group of scanners that answer the same kind of question.

    Purely organisational: the engine never sees a family, and no assessment
    behaviour depends on one. It exists because "nine scanners" is a list and
    "four families of nine scanners" is a product — the library reads this to
    decide its sections, and the alternative is a hard-coded grouping in the
    frontend that drifts from the registry.
    """

    id: str
    name: str
    #: What the scanners in this family have in common, in one line.
    subject: str


FOUNDATION = Family(
    id="foundation", name="Foundation",
    subject="The physical ground truth of a place — what it is made of, how "
            "water moves through it, and what lives on it.")

DEVELOPMENT = Family(
    id="development", name="Development",
    subject="What may be built here, what has been built, and what serves it.")

CULTURE = Family(
    id="culture", name="Culture",
    subject="What a place has been, and what of that record survives in it.")

ECONOMICS = Family(
    id="economics", name="Economics",
    subject="What a place is worth, to whom, and on what evidence.")

#: Order matters: this is the order the scanner library renders its sections.
#: Foundation first because it is the only family with anything live in it, and
#: a library that opens on four planned sections would be a roadmap wearing a
#: product's clothes.
FAMILIES: Tuple[Family, ...] = (FOUNDATION, DEVELOPMENT, CULTURE, ECONOMICS)


# ---------------------------------------------------------------------------
# Domains
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Domain:
    """A named part of one scanner's subject.

    The unit at which this product is honest about coverage. "Water: partial"
    is a claim nobody can check; "Water covers coastal exposure and flood, and
    does not yet cover groundwater or drainage" is one a professional can act
    on — they know to look elsewhere for the second pair rather than reading an
    empty result as an absence of risk.
    """

    id: str
    name: str
    #: What this domain examines, in one line. Shown, not inferred.
    subject: str
    #: Topic ids of the shared rule set (`radar.TOPICS`) this domain owns.
    core_topics: Tuple[str, ...] = ()
    #: A contributing rules package, as `radar.rules_from` takes it.
    package: str = ""
    #: Factors this domain exposes beyond those its rules require. Habitat
    #: exposes `evi` and `lc_dominant` for context that no rule tests on.
    extra_factors: Tuple[str, ...] = ()
    #: Why this domain has no evidence yet. Required when it has no content —
    #: `_check_registry` refuses a declared domain that does not say what is
    #: missing, because "coming soon" is not a statement anyone can plan
    #: around and this product's whole discipline is naming the gap.
    blocked_by: str = ""

    @property
    def implemented(self) -> bool:
        """Whether this domain contributes any check at all."""
        return bool(self.core_topics or self.package)


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------
def _package_module(name: str) -> Any:
    """The contributing package, or a stand-in with empty content.

    A package that fails to import must not take the registry down with it —
    the registry is imported before anything serves, so an ImportError here is
    a dead deployment rather than a degraded one. The scanner then reports
    nothing rather than wrong things, which is the outcome the whole model is
    built to produce.
    """
    try:
        return __import__(name, fromlist=["TOPICS"])
    except Exception:                                       # noqa: BLE001
        return None


def _topics_of(domains: Sequence[Domain]) -> Mapping[str, str]:
    """The scanner's topic vocabulary, merged from its domains.

    Returns `radar.TOPICS` **itself** when the domains cover all of it, so the
    foundation scanner holds no copy of the shared vocabulary. See the module
    note on why copying is the thing to avoid.
    """
    core: Tuple[str, ...] = tuple(
        t for d in domains for t in d.core_topics)
    if set(core) == set(radar.TOPICS) and not any(d.package for d in domains):
        return radar.TOPICS

    out: Dict[str, str] = {}
    for d in domains:
        for t in d.core_topics:
            out[t] = radar.TOPICS[t]
        if d.package:
            module = _package_module(d.package)
            for k, v in (getattr(module, "TOPICS", {}) or {}).items():
                # A collision means two domains claim one topic id and one of
                # them would silently win. Refusing is better than a scanner
                # whose vocabulary depends on domain order.
                if k in out and out[k] != v:
                    raise ValueError(
                        f"topic id {k!r} is claimed by two domains with "
                        f"different names ({out[k]!r} and {v!r}). Rename one: "
                        f"a silent winner makes the vocabulary depend on the "
                        f"order domains happen to be listed in.")
                out[k] = v
    return out


def _rules_of(domains: Sequence[Domain]) -> Tuple[Tuple[Any, ...],
                                                  Mapping[str, str]]:
    """The scanner's rules, and which domain each came from.

    Core rules are `radar.RULES` filtered by topic, which means Land and Water
    share the identical `Rule` object for a flood check. Package rules arrive
    through `radar.rules_from`, unchanged.

    The provenance map is the second return because a finding should be
    attributable to a domain: "Water flagged this, in its coastal domain" tells
    a reader which part of the subject was being examined, and — more usefully
    — which specialist owns the follow-up. Computed here, at composition, so it
    cannot disagree with the rule list it describes.
    """
    by_topic: Dict[str, str] = {
        t: d.id for d in domains for t in d.core_topics}
    out: list = []
    origin: Dict[str, str] = {}
    for r in radar.RULES:
        if r.topic in by_topic:
            out.append(r)
            origin[r.id] = by_topic[r.topic]
    for d in domains:
        if d.package:
            for r in radar.rules_from(d.package):
                out.append(r)
                origin[r.id] = d.id
    return tuple(out), origin


def _investigations_of(domains: Sequence[Domain],
                       rules: Sequence[Any]) -> Mapping[str, Mapping[str, str]]:
    """The investigations this scanner's rules can actually raise.

    Filtered by what the rules reference rather than handed over whole: a
    scanner offering "contamination desk study" in its vocabulary when no rule
    of its can raise one describes a capability it does not have.
    """
    named = {i for r in rules for i in r.investigations}
    if named >= set(radar.INVESTIGATIONS) and not any(d.package for d in domains):
        return radar.INVESTIGATIONS

    out: Dict[str, Mapping[str, str]] = {
        k: v for k, v in radar.INVESTIGATIONS.items() if k in named}
    for d in domains:
        if d.package:
            module = _package_module(d.package)
            for k, v in (getattr(module, "INVESTIGATIONS", {}) or {}).items():
                if k in named:
                    out[k] = v
    return out


def _factors_of(domains: Sequence[Domain], rules: Sequence[Any],
                all_factors: bool) -> Tuple[str, ...]:
    """The factors this scanner exposes.

    For the foundation scanner, the whole catalogue: Land is the sweep, and
    the factor browser is how a user reaches a measurement no rule tests on.

    For a specialist, exactly what its rules need plus what its domains
    declare. A scanner seeing factors it cannot use would show an ecologist
    twenty rainfall series and call them ecology.
    """
    if all_factors:
        return tuple(f["id"] for f in catalog.FACTORS)
    known = {f["id"] for f in catalog.FACTORS}
    seen: Dict[str, None] = {}
    for r in rules:
        for fid in r.needs:
            if fid in known:
                seen[fid] = None
    for d in domains:
        for fid in d.extra_factors:
            if fid in known:
                seen[fid] = None
    return tuple(seen)


@dataclass(frozen=True)
class Scanner:
    """One scanner's configuration.

    Frozen because a scanner is resolved per request and shared across them —
    a mutable config is a cross-request leak waiting to happen, and the
    isolation test exists precisely because that is the failure mode.
    """

    id: str
    #: What the shell shows beside the product name: "Site Scanner · Land".
    name: str
    #: What this scanner investigates, in one line. Shown, not inferred.
    subject: str
    #: Which family it belongs to. Organisational only.
    family: str
    #: The named parts of its subject, in the order it presents them.
    domains: Tuple[Domain, ...]
    topics: Mapping[str, str]
    rules: Tuple[Any, ...]
    investigations: Mapping[str, Mapping[str, str]]
    #: The factor ids this scanner exposes. A scanner sees only its own.
    factors: Tuple[str, ...]
    #: Rule id → the domain that contributed it. Lets a finding say which part
    #: of the subject raised it, and therefore which specialist owns it.
    rule_domains: Mapping[str, str] = field(default_factory=dict)
    #: The scanner's own version. Changes when its rules, thresholds or domains
    #: change — a report carries it so a finding can be traced to the exact
    #: configuration that reached it. See `docs/SITE_EVIDENCE_RECORD.md`.
    version: str = "1.0.0"
    #: The version of the *method* — how the engine turns evidence into
    #: findings. Kept apart from `version` because a new rule and a changed
    #: definition of "assessed" are different events for anyone re-reading an
    #: old report.
    methodology_version: str = "1.0.0"
    #: Where this scanner is valid. `None` means no coverage has been
    #: established — not "everywhere", and not England by default.
    coverage: Optional[Mapping[str, float]] = None
    #: The name of that coverage, for the message a user reads.
    coverage_name: str = ""
    #: The profession that would own this scanner's findings, where one
    #: clearly would. Empty where no single discipline owns it — Land spans
    #: several, and naming one would be an invented claim about who signs.
    #: See `docs/SCANNER_ECOSYSTEM.md`.
    specialist: str = ""

    @property
    def implemented(self) -> bool:
        """Whether this scanner can assess anything at all.

        A scanner with no rules is registered and unbuilt. Saying so is more
        useful than hiding it: the API can refuse the request with a reason
        rather than returning an empty report that looks like a clean site.
        """
        return bool(self.rules)

    @property
    def status(self) -> str:
        """`live`, `partial` or `planned` — derived, never asserted.

        - **planned** — no rules. It cannot assess anything.
        - **partial** — it assesses some of its declared subject. At least one
          domain is declared and unbuilt, so a clear result from this scanner
          is clear *about the domains that ran*, and the report says which.
        - **live** — every domain it declares is built.

        Derived from the domains rather than stored, because a stored status is
        a claim someone has to remember to update and this one cannot go stale.
        A scanner that gains a domain drops to `partial` the moment it does,
        which is the honest direction for that change to move.
        """
        if not self.rules:
            return "planned"
        return "live" if all(d.implemented for d in self.domains) else "partial"

    @property
    def built_domains(self) -> Tuple[Domain, ...]:
        return tuple(d for d in self.domains if d.implemented)

    @property
    def declared_domains(self) -> Tuple[Domain, ...]:
        """Domains with a name and no evidence. The coverage gap, named."""
        return tuple(d for d in self.domains if not d.implemented)

    def sees(self, factor_id: str) -> bool:
        return factor_id in self.factors

    def domain(self, domain_id: str) -> Optional[Domain]:
        for d in self.domains:
            if d.id == domain_id:
                return d
        return None

    def rules_in(self, domain_id: str) -> Tuple[Any, ...]:
        """This scanner's rules that came from one domain.

        The reverse of `rule_domains`, for the caller that has a domain and
        wants its checks — a report grouping findings by domain, or a test
        scoped to the checks one domain contributed.
        """
        return tuple(r for r in self.rules
                     if self.rule_domains.get(r.id) == domain_id)


def _scanner(id: str, name: str, subject: str, family: Family,
             domains: Sequence[Domain], *, coverage_name: str = "",
             version: str = "1.0.0", methodology_version: str = "1.0.0",
             specialist: str = "", all_factors: bool = False) -> Scanner:
    """Build a scanner from its domains.

    Coverage follows content: a scanner with no built domain gets `None`, which
    means *no coverage has been established* — distinct from "covers nowhere"
    and from silently inheriting England. Deriving it here rather than passing
    it per scanner removes the way that could be got wrong, which is a planned
    scanner claiming a coverage area it has never been run in.
    """
    domains = tuple(domains)
    topics = _topics_of(domains)
    rules, rule_domains = _rules_of(domains)
    built = any(d.implemented for d in domains)
    return Scanner(
        id=id, name=name, subject=subject, family=family.id, domains=domains,
        topics=topics, rules=rules, rule_domains=rule_domains,
        investigations=_investigations_of(domains, rules),
        factors=_factors_of(domains, rules, all_factors),
        version=version, methodology_version=methodology_version,
        coverage=catalog.ENGLAND_BBOX if built else None,
        coverage_name=coverage_name if built else "",
        specialist=specialist,
    )


# ---------------------------------------------------------------------------
# FOUNDATION — the physical ground truth
# ---------------------------------------------------------------------------
#: The foundation scanner, and the one every other scanner was extracted from.
#:
#: It keeps all seven core topics and the whole catalogue. That overlap with
#: Water, Ecology and Planning is deliberate and the module note explains why:
#: Land is the sweep you run before you know which specialist question matters,
#: and a professional who runs it and is not told about Flood Zone 3 has been
#: failed by a taxonomy. The rules are shared objects, not copies, so the
#: overlap cannot drift.
#:
#: Terrain is a domain here rather than a scanner. It was registered as a
#: top-level vertical and never built, while land's `terrain` topic had two
#: working rules the whole time — the registry was describing a product
#: boundary that the rule set did not have.
LAND = _scanner(
    "land", "Land",
    "Site constraints and land assessment",
    FOUNDATION,
    (
        Domain("ground", "Ground and historical land use",
               "What the site is made of, and what has been done to it before.",
               core_topics=("ground",)),
        Domain("terrain", "Terrain",
               "Elevation, slope and the shape of the ground.",
               core_topics=("terrain",)),
        Domain("flood", "Flood",
               "Designated fluvial and tidal flood risk.",
               core_topics=("flood",)),
        Domain("water", "Surface water",
               "Standing and seasonal water on the site.",
               core_topics=("water",)),
        Domain("vegetation", "Vegetation",
               "Vegetation extent, vigour and change.",
               core_topics=("vegetation",)),
        Domain("ecology", "Habitats and designations",
               "Designated sites, habitat context and protected land.",
               core_topics=("ecology",)),
        Domain("planning", "Planning and heritage",
               "Designations that govern what may be done here.",
               core_topics=("planning",)),
    ),
    coverage_name="England", all_factors=True,
    version="2.0.0",
)

#: Scanner #2 by construction, though habitat was built first.
#:
#: Water absorbs the coastal package — coastal is a *domain* of water, not a
#: product. A shoreline is one of the ways water reaches a site; groundwater,
#: drainage and catchment are others, and none of those is more or less a
#: product than the coast is.
#:
#: `status` is `partial`, and that is the useful thing this scanner says: it
#: covers flood, surface water and coastal exposure, and it does not cover
#: groundwater, drainage or catchment. A user reading a clear result knows
#: which questions were asked.
WATER = _scanner(
    "water", "Water",
    "Water, flood and coastal assessment",
    FOUNDATION,
    (
        Domain("flood", "Flood",
               "Designated fluvial and tidal flood risk.",
               core_topics=("flood",)),
        Domain("surface_water", "Surface water",
               "Standing and seasonal water, and how its extent changes.",
               core_topics=("water",)),
        Domain("coastal", "Coastal",
               "Low-lying exposure and water-extent change on a coastal site.",
               package="coastal.rules",
               extra_factors=("elevation_min", "elevation_mean",
                              "water_change", "water_occurrence",
                              "water_seasonality", "lc_water_pct",
                              "slope_mean")),
        Domain("groundwater", "Groundwater", "Aquifers, water table and "
               "groundwater-dependent features.",
               blocked_by="No groundwater source is integrated. The Environment "
                          "Agency publishes aquifer designations and source "
                          "protection zones; neither is ingested."),
        Domain("drainage", "Drainage", "Surface water drainage and runoff "
               "behaviour.",
               blocked_by="Requires a drainage network dataset and a runoff "
                          "method. Neither exists here, and a runoff figure "
                          "derived from land cover alone would be a modelled "
                          "number presented as an observation."),
        Domain("catchment", "Catchment", "The catchment a site sits in and "
               "the water bodies it drains to.",
               blocked_by="Requires WFD water body boundaries and catchment "
                          "geometries. The EA publishes both; neither is "
                          "ingested."),
    ),
    coverage_name="England", specialist="Flood risk consultant / hydrologist",
)

#: Ecology absorbs the habitat package, and declares woodland as the domain
#: forestry was going to be.
#:
#: Habitat is a domain, not a product, for the same reason coastal is: an
#: ecologist asking about a site asks about habitats, woodland, protected
#: species and connectivity in one breath, and a product that makes them pick
#: one has organised itself around its own build order.
ECOLOGY = _scanner(
    "ecology", "Ecology",
    "Ecological condition, habitat and biodiversity evidence",
    FOUNDATION,
    (
        Domain("habitat", "Habitat condition",
               "Vegetation condition, moisture, structure and cover, read "
               "from fifteen years of observation.",
               package="habitat.rules",
               extra_factors=("ndvi", "ndmi", "evi", "lc_tree_pct",
                              "lc_dominant", "water_occurrence")),
        Domain("vegetation", "Vegetation",
               "Vegetation extent, vigour and change across the site.",
               core_topics=("vegetation",)),
        Domain("designations", "Designated sites",
               "Statutory and non-statutory designations and habitat context.",
               core_topics=("ecology",)),
        Domain("woodland", "Woodland and trees",
               "Woodland extent, ancient woodland and tree cover change.",
               blocked_by="Requires the Ancient Woodland Inventory and the "
                          "National Forest Inventory. Tree cover percentage is "
                          "available from WorldCover and is not the same "
                          "question — it cannot distinguish ancient woodland "
                          "from a plantation."),
        Domain("species", "Protected species",
               "Records of protected and priority species.",
               blocked_by="Species records come from local environmental "
                          "records centres under licence, and most are not "
                          "open data. Absence of a record is not absence of a "
                          "species, which makes this the domain where a "
                          "confident empty result would be most dangerous."),
        Domain("connectivity", "Ecological connectivity",
               "How habitat here connects to habitat beyond the site.",
               blocked_by="Requires a habitat network dataset. Local Nature "
                          "Recovery Strategies will publish these; they are "
                          "not yet available for most of England."),
    ),
    coverage_name="England", specialist="Ecologist",
)


# ---------------------------------------------------------------------------
# DEVELOPMENT — what may be built, what has been, and what serves it
# ---------------------------------------------------------------------------
#: The planning scanner, built from rules that already existed.
#:
#: Seven rules on the `planning` topic have been running inside the land
#: scanner since before the taxonomy was drawn. Extracting them is not new
#: evidence and this scanner does not claim to be new evidence — it is the same
#: checks, reachable by someone whose question is planning rather than land.
#:
#: The planning *application* domains — history, applications, appeals — are
#: declared and empty. They are the ones a planning consultant would most want,
#: and inventing them is the single most tempting fabrication available in this
#: product, because plausible-looking planning history is easy to generate and
#: impossible for a reader to distinguish from the real thing.
PLANNING = _scanner(
    "planning", "Planning",
    "Planning designations, policy and constraint",
    DEVELOPMENT,
    (
        Domain("designations", "Designations and constraints",
               "Green belt, conservation areas, protected landscapes and the "
               "designations that govern what may be done here.",
               core_topics=("planning",)),
        Domain("applications", "Applications and history",
               "Planning applications, permissions, refusals and appeals.",
               blocked_by="Requires a planning application source. "
                          "planning.data.gov.uk carries designations but not "
                          "application history; that lives in ~330 separate "
                          "local authority registers with no common API."),
        Domain("policy", "Local plan and policy",
               "Adopted and emerging local plan policy, allocations and "
               "development boundaries.",
               blocked_by="Local plans are published as PDFs per authority. "
                          "Extracting policy from them is a language problem, "
                          "not a data problem, and an extracted policy "
                          "position stated as fact would be this product "
                          "giving planning advice."),
    ),
    coverage_name="England", specialist="Planning consultant",
)

DEVELOPMENT_SCANNER = _scanner(
    "development", "Development",
    "Built form, land-use change and development activity",
    DEVELOPMENT,
    (
        Domain("built_form", "Built form",
               "Building footprints, density and the pattern of what exists.",
               blocked_by="Requires OS building footprints. Available under "
                          "the Open Data licence for some products and not "
                          "others; the licence position is unresolved."),
        Domain("land_use_change", "Land-use change",
               "Change in how land here has been used, read from observation.",
               blocked_by="The observation record exists — this is the domain "
                          "closest to buildable. It needs a change-detection "
                          "method that distinguishes development from "
                          "seasonal and agricultural change, and that method "
                          "has not been written or validated."),
        Domain("pipeline", "Development pipeline",
               "Consented and proposed development in and around the site.",
               blocked_by="Depends on planning application data, which is the "
                          "same blocker the Planning scanner records."),
    ),
)

INFRASTRUCTURE = _scanner(
    "infrastructure", "Infrastructure",
    "Utilities, transport and network capacity",
    DEVELOPMENT,
    (
        Domain("electricity", "Electricity",
               "Transmission, distribution, substations and grid capacity.",
               blocked_by="DNOs publish heat maps and capacity registers in "
                          "incompatible formats, several behind registration. "
                          "No national dataset exists."),
        Domain("water_utilities", "Water and sewer",
               "Potable supply, foul and surface water sewer networks.",
               blocked_by="Network data is held by water companies and "
                          "released per enquiry, not as open data."),
        Domain("transport", "Transport",
               "Road and rail networks, and access to them.",
               blocked_by="OS Open Roads and rail network data are open. "
                          "Neither is ingested, and proximity to a road is a "
                          "measurement this product could make honestly — "
                          "this is the most tractable domain here."),
        Domain("telecoms", "Telecommunications",
               "Fixed and mobile connectivity.",
               blocked_by="Ofcom publishes Connected Nations at postcode "
                          "level. Not ingested, and postcode resolution is "
                          "coarser than a site boundary."),
    ),
)


# ---------------------------------------------------------------------------
# CULTURE — what a place has been
# ---------------------------------------------------------------------------
#: Heritage is declared, and it is the clearest example of why declaring is
#: worth doing. Historic England publishes the National Heritage List as open
#: data: listed buildings, scheduled monuments, registered parks and gardens,
#: protected wreck sites and battlefields, all as spatial data under OGL.
#:
#: So this scanner is blocked on ingestion work, not on a licence or a missing
#: source — which is a materially different position from Infrastructure, and
#: the reason each domain records its *specific* blocker rather than a shared
#: "not built yet".
HERITAGE = _scanner(
    "heritage", "Heritage",
    "Designated heritage assets, archaeology and historic landscape",
    CULTURE,
    (
        Domain("designated", "Designated assets",
               "Listed buildings, scheduled monuments, registered parks and "
               "gardens, battlefields and protected wrecks.",
               blocked_by="Historic England publishes the National Heritage "
                          "List for England as open spatial data under OGL. "
                          "It is not ingested. This is ingestion work, not a "
                          "licence or sourcing problem."),
        Domain("conservation_areas", "Conservation areas",
               "Conservation area boundaries and their settings.",
               blocked_by="Boundaries are designated by local authorities and "
                          "aggregated on planning.data.gov.uk with incomplete "
                          "coverage. Partial national coverage stated as "
                          "national coverage would produce false clears."),
        Domain("archaeology", "Archaeology",
               "Recorded archaeology and buried heritage potential.",
               blocked_by="Historic Environment Records are held by county "
                          "and unitary authorities, most not open. Buried "
                          "potential is an archaeological judgement, not a "
                          "dataset — this domain would need a specialist "
                          "contributor rather than a source."),
        Domain("historic_landscape", "Historic landscape",
               "Historic landscape character and historic map evidence.",
               blocked_by="Historic Landscape Characterisation exists per "
                          "county in varying vintages and schemas. Historic "
                          "mapping is largely under commercial licence."),
    ),
    specialist="Heritage consultant / archaeologist",
)


# ---------------------------------------------------------------------------
# ECONOMICS — what a place is worth, and on what evidence
# ---------------------------------------------------------------------------
#: Market is declared, and deliberately the thinnest declaration here.
#:
#: The evidence principles bind hardest in this family. A land value is a
#: professional valuation, and a number derived from comparable transactions
#: and printed without one is the most consequential fabrication this product
#: could commit — it would be relied upon, and it would be wrong in the
#: specific cases where the site differs from its comparables, which is every
#: case anyone pays for advice about.
#:
#: `app.py` already carries a Land Registry price lookup. That is a record of
#: transactions, which is evidence; it is not a valuation, which is a
#: judgement. This scanner exists to hold that line explicitly rather than
#: leaving the distinction to whoever builds it.
MARKET = _scanner(
    "market", "Market",
    "Transaction evidence and local economic context",
    ECONOMICS,
    (
        Domain("transactions", "Transaction evidence",
               "Recorded transactions in the area, as evidence and never as "
               "a valuation of this site.",
               blocked_by="HM Land Registry Price Paid is open and already "
                          "reachable from app.py. It is not wired to a "
                          "scanner because presenting transactions beside a "
                          "site invites reading them as its value. That needs "
                          "a claim boundary written before the feature."),
        Domain("demographics", "Demographics and economy",
               "Population, employment and economic context around the site.",
               blocked_by="ONS releases are ingested for other purposes "
                          "(see ons/). None is bound to a scanner, and "
                          "output-area statistics describe an area, not a "
                          "site."),
        Domain("accessibility", "Accessibility",
               "Journey times and access to services and employment.",
               blocked_by="DfT journey time statistics were discontinued "
                          "after 2019. Stale accessibility figures presented "
                          "as current would be worse than none."),
    ),
    specialist="Chartered surveyor / valuer",
)


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------
#: Order matters: this is the order the scanner library renders, grouped by
#: family, built scanners first within each.
SCANNERS: Dict[str, Scanner] = {
    s.id: s for s in (
        LAND, WATER, ECOLOGY,
        PLANNING, DEVELOPMENT_SCANNER, INFRASTRUCTURE,
        HERITAGE,
        MARKET,
    )
}

#: Ids that used to name a top-level scanner and now name a domain inside one.
#:
#: A saved permalink, a stored report, a bookmark or an API client written
#: against the old vocabulary keeps working. This is the only place the mapping
#: exists, and `resolve` returns the canonical scanner, so nothing downstream
#: ever sees an alias — `Scanner.id` is always the real id.
#:
#: They are not registered scanners: they do not appear in `ids()`, the library
#: does not list them, and `/api/catalog` does not offer them. An alias is a
#: door that still opens, not a product that still exists.
ALIASES: Dict[str, str] = {
    # Absorbed as a domain of the scanner named.
    "habitat": "ecology",
    "coastal": "water",
    "terrain": "land",
    # Never built as a scanner; its subject is Ecology's woodland domain,
    # which is declared and honest about being unbuilt.
    "forestry": "ecology",
}

#: What a request gets when it does not say. Every existing caller predates
#: scanner identity, and the land scanner is what they have always meant.
DEFAULT_SCANNER = LAND.id


class UnknownScanner(LookupError):
    """Raised for an id that is neither registered nor an alias.

    Its own type rather than a `KeyError` so the API layer can turn it into a
    400 with the valid ids listed, instead of a 500 that tells the caller
    nothing about what they should have sent.
    """


def resolve(scanner_id: Optional[str]) -> Scanner:
    """`"land"` → the land scanner. `None` → the default. `"coastal"` → water.

    The only way to obtain a scanner. Nothing reads `SCANNERS` directly, so
    there is one place where an unknown id is rejected, one place where a
    retired id is redirected, and one place to look when adding a scanner.
    """
    key = (scanner_id or DEFAULT_SCANNER).strip().lower()
    key = ALIASES.get(key, key)
    try:
        return SCANNERS[key]
    except KeyError:
        raise UnknownScanner(key) from None


def ids() -> Tuple[str, ...]:
    """Registered ids, for an error message that tells the caller what to send.

    Aliases are deliberately absent: they are compatibility, not product.
    """
    return tuple(SCANNERS)


def families() -> Tuple[Tuple[Family, Tuple[Scanner, ...]], ...]:
    """Families with their scanners, in render order.

    The library's structure comes from here rather than from a grouping written
    into a component, for the same reason its availability does: two lists of
    the product's shape drift, and the frontend's copy is the one that gets
    forgotten.
    """
    return tuple(
        (f, tuple(s for s in SCANNERS.values() if s.family == f.id))
        for f in FAMILIES
    )


def _check_registry() -> None:
    """Invariants that must hold at import, checked at import.

    A registry that violates one of these is a bug that would otherwise surface
    as a strange report rather than as an error — a scanner claiming coverage
    it has not established, or a domain that says nothing about why it is
    empty. Failing here costs a startup; failing later costs a false clear.
    """
    for s in SCANNERS.values():
        assert s.family in {f.id for f in FAMILIES}, (
            f"{s.id} names family {s.family!r}, which is not registered")
        assert s.domains, f"{s.id} declares no domains"
        for d in s.domains:
            assert d.implemented or d.blocked_by, (
                f"{s.id}.{d.id} is declared with no content and no "
                f"`blocked_by`. Say what is missing: an unexplained empty "
                f"domain is a promise, and this product does not make them.")
            # A package named but absent produces *nothing*, silently:
            # `radar.rules_from` swallows the ImportError by design, so the
            # domain would report itself built and contribute no checks. That
            # is the worst available failure — a scanner that says it covers
            # coastal exposure and never looks. Fail at import instead, where
            # it is a dead deployment rather than a false clear.
            if d.package:
                assert any(r.topic in getattr(
                    _package_module(d.package), "TOPICS", {})
                    for r in s.rules), (
                    f"{s.id}.{d.id} names package {d.package!r}, which "
                    f"contributed no rules. Either the package is missing from "
                    f"this environment or its `build()` returned nothing — "
                    f"both leave a domain claiming a subject it never checks.")
        if not s.implemented:
            assert s.coverage is None, (
                f"{s.id} has no rules but claims coverage {s.coverage_name!r}")
    for alias, target in ALIASES.items():
        assert target in SCANNERS, f"alias {alias!r} points at nothing"
        assert alias not in SCANNERS, (
            f"{alias!r} is both an alias and a registered scanner")


_check_registry()
