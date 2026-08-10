"""
The scanner registry.

A scanner is a **configuration**, not a subclass and not a plugin. It names a
vocabulary, a set of checks, the follow-up investigations those checks prompt,
the factors it exposes and where it is valid. Everything else — the assessment
engine, evidence states, coverage, the claim boundary, the investigation
workspace, the brief — is shared and unchanged.

    Site Scanner
      → scanner registry
        → land · habitat · coastal
          → shared assessment engine
          → shared evidence and provenance
          → shared investigation workspace
          → shared brief

## Why this is a dataclass and not a framework

`tests/test_multi_scanner_experiment.py` measured what was actually required to
run a second domain through the engine, and the answer was: a topic dict, a
rule sequence and an investigation dict. No lifecycle, no hooks, no base class,
no loader. Anything more would be an abstraction built for an imagined
requirement rather than a measured one — and `docs/MULTI_SCANNER_AUDIT.md`
records the measurement so the next person can check rather than trust.

## Land is built from the existing globals, never copied

`LAND` reads `radar.TOPICS`, `radar.RULES`, `radar.INVESTIGATIONS` and
`catalog.FACTORS` directly. Copying them would create a second definition that
drifts, and the first symptom would be a rule that runs in tests and not in
production. The registry is a lens over what already exists.

## Habitat is built; coastal is declared and deliberately empty

Habitat (scanner #2) contributes its rules through `radar.rules_from`, the same
package contract `historical.rules` uses. Adding it required **no engine
change** — the seam already existed.

Coastal has a name, an id and no content. That is not an oversight: rules and
thresholds are product decisions with scientific consequences, and inventing
them to make a registry look populated is exactly the failure this codebase
spends its effort preventing. An unbuilt scanner is honest about being unbuilt,
and `coverage=None` means **no coverage has been established** — distinct from
"covers nowhere" and from silently inheriting England.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

import catalog
import radar
from habitat import rules as habitat_rules


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
    topics: Mapping[str, str]
    rules: Tuple[Any, ...]
    investigations: Mapping[str, Mapping[str, str]]
    #: The factor ids this scanner exposes. A scanner sees only its own.
    factors: Tuple[str, ...]
    #: Where this scanner is valid. `None` means no coverage has been
    #: established — not "everywhere", and not England by default.
    coverage: Optional[Mapping[str, float]] = None
    #: The name of that coverage, for the message a user reads.
    coverage_name: str = ""

    @property
    def implemented(self) -> bool:
        """Whether this scanner can assess anything at all.

        A scanner with no rules is registered and unbuilt. Saying so is more
        useful than hiding it: the API can refuse the request with a reason
        rather than returning an empty report that looks like a clean site.
        """
        return bool(self.rules)

    def sees(self, factor_id: str) -> bool:
        return factor_id in self.factors


#: The land scanner — today's behaviour, named.
#:
#: Every field reads the existing global rather than restating it, so this is a
#: description of what already runs rather than a second source of truth.
LAND = Scanner(
    id="land",
    name="Land",
    subject="A site, parcel or landholding",
    topics=radar.TOPICS,
    rules=tuple(radar.RULES),
    investigations=radar.INVESTIGATIONS,
    factors=tuple(f["id"] for f in catalog.FACTORS),
    coverage=catalog.ENGLAND_BBOX,
    coverage_name="England",
)

#: Scanner #2. One flagged check and five informational readings — see
#: `HABITAT_SCANNER.md`, which records the questions a habitat scanner should
#: answer and cannot yet, each with its specific blocker, rather than filling
#: them with invented thresholds.
#:
#: Its rules come through `radar.rules_from`, the same contributing-package
#: contract `historical.rules` uses, so the engine gained nothing to support
#: this scanner and knows nothing about ecology.
#:
#: Coverage is England — not because the factors are England-limited (they are
#: global Sentinel-2, WorldCover and JRC) but because that is where this
#: deployment has been exercised, and claiming more would assert something
#: untested.
HABITAT = Scanner(
    id="habitat",
    name="Habitat",
    subject="A habitat parcel, reserve or landscape unit",
    topics=habitat_rules.TOPICS,
    rules=radar.rules_from("habitat.rules"),
    investigations=habitat_rules.INVESTIGATIONS,
    factors=habitat_rules.FACTORS,
    coverage=catalog.ENGLAND_BBOX,
    coverage_name="England",
)

COASTAL = Scanner(
    id="coastal",
    name="Coastal",
    subject="A frontage or coastal cell",
    topics={},
    rules=(),
    investigations={},
    factors=(),
    coverage=None,
)


SCANNERS: Dict[str, Scanner] = {s.id: s for s in (LAND, HABITAT, COASTAL)}

#: What a request gets when it does not say. Every existing caller predates
#: scanner identity, and the land scanner is what they have always meant.
DEFAULT_SCANNER = LAND.id


class UnknownScanner(LookupError):
    """Raised for an id that is not registered.

    Its own type rather than a `KeyError` so the API layer can turn it into a
    400 with the valid ids listed, instead of a 500 that tells the caller
    nothing about what they should have sent.
    """


def resolve(scanner_id: Optional[str]) -> Scanner:
    """`"land"` → the land scanner. `None` → the default.

    The only way to obtain a scanner. Nothing reads `SCANNERS` directly, so
    there is one place where an unknown id is rejected and one place to look
    when adding a scanner.
    """
    key = (scanner_id or DEFAULT_SCANNER).strip().lower()
    try:
        return SCANNERS[key]
    except KeyError:
        raise UnknownScanner(key) from None


def ids() -> Tuple[str, ...]:
    """Registered ids, for an error message that tells the caller what to send."""
    return tuple(SCANNERS)
