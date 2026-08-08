"""A rule-based de-identifier for EIA text, built to be measured.

Rules rather than a model, for one reason: this runs on the deployed API, which
has no `ANTHROPIC_API_KEY` and no GPU, and a safety control that only works
when a key is present is not a safety control. The same argument `nlq.py`
already makes about answering questions.

The order of the passes matters and is the interesting part. Protecting
taxonomy has to happen *before* person-name matching, because `Quercus robur
L.` and `J. Hartley` are the same shape and a person-name rule applied first
eats the species list — which is most of what an ecological record is worth.

Everything is replaced with a labelled placeholder rather than deleted, so a
reader can see that something was removed and what kind of thing it was. A
silently shortened sentence is worse than a visibly redacted one: it reads as
the author's own words.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# Things that must survive. Applied first, as protection.
# ---------------------------------------------------------------------------

# Botanical and zoological authorities: the `L.` in `Quercus robur L.` is
# Linnaeus. Also the common multi-letter ones a UK report actually uses.
_AUTHORITY = r"(?:L|Mill|DC|Huds|Sm|Scop|Roth|Willd|Lam|Pers|Beauv)\."

# A binomial is two capitalised-then-lowercase Latin words — but so is most of
# an English sentence. The first version of this pattern matched `Homes
# ownership` and `Hartley and`, and because a protected span blocks every
# redaction rule, it punched a hole straight through the thing it was meant to
# protect: `Bloor Homes` and `J. Hartley` both survived because a false species
# match overlapped them.
#
# So the shape alone is not enough. A pair qualifies only if something
# corroborates the Latin: a recognised epithet ending, a trailing authority, or
# a known genus. This is narrower than real taxonomy and will miss binomials
# that satisfy none of the three — the trade is deliberate, because a missed
# species name costs a word of the finding and a false protection costs a leak.
# Second attempt. The first ending list included `-e`, `-a`, `-is` and `-i`,
# which are Latin epithet endings and also the endings of a large fraction of
# ordinary English words: `Road frontage` and `Homes ownership` both parsed as
# species and shielded the site name and the client name behind them.
#
# So the common endings are gone, and the cost is explicit — `Lolium perenne`
# no longer qualifies on shape and survives only because `Lolium` is in the
# genus list below. That is the honest shape of this problem: the genus list is
# doing the work, and a heuristic is standing in for a checklist.
_EPITHET = (
    r"[a-z]{2,}(?:us|um|ii|ata|atum|atus|osa|osus|ensis|oides|ana|"
    r"ina|alis|aria|escens|ifera|iflora|folia|folium)"
)

# A stub for a real species checklist. The NBN Atlas and GBIF both publish a
# complete UK one, and a deployment would load that rather than this — twenty
# genera cover a hedgerow survey and nothing else, and any species outside them
# is protected only if its epithet ends Latin enough to be recognised.
_GENERA = (
    r"Quercus|Fraxinus|Betula|Acer|Fagus|Ulmus|Salix|Populus|Pinus|Taxus|"
    r"Crataegus|Prunus|Corylus|Ilex|Sorbus|Alnus|Tilia|Castanea|Carpinus|"
    r"Lolium|Holcus|Plantago|Pipistrellus|Triturus|Rubus|Hedera|Urtica"
)
_BINOMIAL = re.compile(
    r"\b(?:"
    # genus we know, any epithet
    rf"(?:{_GENERA})\s+[a-z]{{3,}}"
    r"|"
    # any capitalised genus, but only with a Latin-looking epithet
    rf"[A-Z][a-z]{{2,}}\s+{_EPITHET}"
    r")"
    r"(?:\s+(?:subsp|var|ssp)\.\s+[a-z]{3,})?"
    r"(?:\s+" + _AUTHORITY + r")?"
)

# Given names, for the one rule that cannot work on shape alone. `Sarah
# Mbeki-Wright` and `Priority Habitat` are the same pattern — two capitalised
# words — and the only thing separating them is knowing that `Sarah` is a name
# and `Priority` is not. A real deployment needs a full gazetteer (ONS publishes
# one); this stub is enough to show the mechanism and not enough to rely on,
# which is itself part of the finding.
_GIVEN_NAMES = (
    r"Sarah|Jennifer|James|John|Robert|Michael|David|Thomas|Emma|Charlotte|"
    r"Rebecca|Daniel|Matthew|Andrew|Richard|Katherine|Elizabeth|Rachel|"
    r"Hannah|Laura|Peter|Simon|Nicholas|Christopher|Alexander|Olivia|Sophie"
)

# Professional post-nominals and body names, which look like acronyms but are
# not clients.
_KNOWN_ACRONYMS = {
    "CIEEM", "MCIEEM", "ACIEEM", "FCIEEM", "UKHab", "NERC", "DEFRA", "NE",
    "EIA", "PEA", "BNG", "SSSI", "SAC", "SPA", "LNR", "NNR", "TPO", "NVC",
    "JNCC", "IEMA", "RSPB", "DNA", "GCN", "EPS", "DLL", "OS", "NGR", "AONB",
}


# ---------------------------------------------------------------------------
# Identifier patterns
# ---------------------------------------------------------------------------
_PATTERNS: List[Tuple[str, re.Pattern]] = [
    # Email before anything else — it contains a name and a company and would
    # otherwise be half-redacted into something still readable.
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),

    ("PHONE", re.compile(r"\b0\d{2,4}\s?\d{3}\s?\d{3,4}\b")),

    ("POSTCODE", re.compile(
        r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}\b")),

    # OS grid references: two letters then 6, 8 or 10 digits, optionally
    # spaced into two groups.
    ("GRIDREF", re.compile(
        r"\b[A-Z]{2}\s?\d{3,5}\s?\d{3,5}\b")),

    # Decimal degrees with a hemisphere letter, and the bare pair.
    ("LATLNG", re.compile(
        r"\b\d{1,3}\.\d{3,}\s?[NSEW]\b")),

    # Natural England protected-species licences.
    ("LICENCE", re.compile(
        r"\b\d{4}-\d{4,6}-[A-Z]{3}-[A-Z]{3}\b")),

    # Planning application references, in the several shapes councils use.
    ("PLANNINGREF", re.compile(
        r"\b(?:[A-Z]{2,3}/)?\d{2,4}/\d{3,5}/[A-Z]{2,4}\b")),

    # Consultancy report references.
    ("REPORTREF", re.compile(
        r"\b[A-Z]{2,4}-\d{3,5}-[A-Z]{2,4}-\d{2,3}\b")),

    # Company names: a run of capitalised words ending in a corporate suffix.
    ("ORG", re.compile(
        r"\b(?:[A-Z][\w&'-]*\s+){1,5}"
        r"(?:Ltd|Limited|LLP|PLC|Plc|Homes|Developments|Estates|Group|"
        r"Partnership|Consulting|Ecology)\b\.?")),

    # Roads. A road number is a coordinate: it locates a site to a few hundred
    # metres and identifies nobody, which is exactly why it gets missed.
    ("ROAD", re.compile(r"\b[AB]\d{3,4}\b")),

    # Titled people. Title first, because it is unambiguous.
    ("PERSON", re.compile(
        r"\b(?:Dr|Mr|Mrs|Ms|Miss|Prof)\.?\s+"
        r"(?:[A-Z]\.?\s+)?[A-Z][a-z]+(?:[-'][A-Z][a-z]+)*"
        r"(?:\s+[A-Z][a-z]+(?:[-'][A-Z][a-z]+)*)?")),

    # Initial-plus-surname, the signature-block form.
    ("PERSON", re.compile(
        r"\b[A-Z]\.\s?[A-Z][a-z]{2,}(?:[-'][A-Z][a-z]+)*\b")),

    # Full names. The first version matched any two capitalised words, which
    # removed `Priority Habitat`, `Statutory Biodiversity Metric` and
    # `District Level Licence` — three of the most valuable phrases in an
    # ecological report — while catching nothing a titled-name rule had not
    # already caught. Anchored on a known given name instead: shape cannot
    # separate `Sarah Mbeki-Wright` from `Priority Habitat`, and pretending
    # otherwise costs the findings.
    ("PERSON", re.compile(
        rf"\b(?:{_GIVEN_NAMES})\s+[A-Z][a-z]{{2,}}(?:[-'][A-Z][a-z]+)*\b")),
]

# Street and place forms: `<Name> Road`, `Land at <Name>`, `<Name> Farm`.
_PLACE = re.compile(
    r"\b(?:[A-Z][\w'-]+\s+){1,3}"
    r"(?:Road|Lane|Street|Avenue|Close|Drive|Way|Farm|Grange|Manor|Court|"
    r"Hill|Green|Common|Wood|Copse|Meadow|Park)\b(?:\s+(?:North|South|East|West))?"
)


def _protected_spans(text: str) -> List[Tuple[int, int]]:
    """Character ranges that no identifier rule may touch.

    Species binomials, and nothing else. Kept deliberately narrow: every
    entry here is a hole in the redaction, so `Persimmon Homes` must not be
    protected merely because `Persimmon` is a genus — which is why the
    binomial pattern requires the *second* word to be lowercase Latin.
    """
    return [(m.start(), m.end()) for m in _BINOMIAL.finditer(text)]


def _overlaps(span: Tuple[int, int], spans: List[Tuple[int, int]]) -> bool:
    return any(not (span[1] <= s or span[0] >= e) for s, e in spans)


def redact(text: str) -> Tuple[str, Dict[str, int]]:
    """Return the redacted text and a count of what was removed, by kind."""
    counts: Dict[str, int] = {}
    protected = _protected_spans(text)

    # Collect every match first, then apply right-to-left, so offsets stay
    # valid and an earlier rule cannot shift a later one's span.
    hits: List[Tuple[int, int, str]] = []

    for label, pattern in _PATTERNS + [("PLACE", _PLACE)]:
        for m in pattern.finditer(text):
            span = (m.start(), m.end())
            if _overlaps(span, protected):
                continue
            matched = m.group(0).strip()
            # A bare professional acronym is not a client.
            if matched.rstrip(".") in _KNOWN_ACRONYMS:
                continue
            hits.append((m.start(), m.end(), label))

    # Longest match wins where two rules overlap: `Bloor Homes South East Ltd`
    # should be redacted as one organisation, not as an organisation plus a
    # stray person name inside it.
    hits.sort(key=lambda h: (h[0], -(h[1] - h[0])))
    chosen: List[Tuple[int, int, str]] = []
    for start, end, label in hits:
        if chosen and start < chosen[-1][1]:
            continue
        chosen.append((start, end, label))

    out = text
    for start, end, label in reversed(chosen):
        out = out[:start] + f"[{label}]" + out[end:]
        counts[label] = counts.get(label, 0) + 1

    return out, counts
