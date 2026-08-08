"""Realistic EIA passages, with ground truth about what must and must not go.

Every passage is modelled on the genre a UK ecological consultancy actually
produces — Preliminary Ecological Appraisal, UKHab survey, protected-species
report, Biodiversity Net Gain metric summary. The names, references and
locations are invented; the *shapes* are not.

Two lists per passage:

- `must_remove` — strings that identify a client, a site, a person or a
  planning case. A single one of these surviving is a leak, and a leak is the
  whole risk of the feature.
- `must_keep` — the strings carrying the ecological finding. This is what the
  library is *for*. A redactor that removes these is safe and worthless, and
  measuring only the first number is how you end up building one.

The corpus deliberately concentrates on the cases where naive redaction fails,
because the easy cases are not what decides this:

- a client name that is also a plant genus (`Persimmon`)
- a site name embedded mid-sentence in a habitat description
- botanical authorities (`Quercus robur L.`) that look exactly like initials
- the same surveyor written two ways, in two places
- a road number, which names no one and locates the site precisely
"""

from typing import List, NamedTuple


class Passage(NamedTuple):
    name: str
    text: str
    must_remove: List[str]
    must_keep: List[str]
    note: str = ""


# ---------------------------------------------------------------------------
# DEV — visible while writing deidentify.py
# ---------------------------------------------------------------------------
DEV_CORPUS: List[Passage] = [
    Passage(
        name="report-header",
        text=(
            "PRELIMINARY ECOLOGICAL APPRAISAL\n"
            "Land at Ockham Road North, East Horsley, Surrey KT24 6RY\n"
            "Prepared for: Bloor Homes South East Ltd\n"
            "Report reference: EC-4471-PEA-02\n"
            "Author: Dr Jennifer Hartley MCIEEM\n"
            "Natural England licence: 2021-52341-CLS-CLS\n"
            "Central grid reference: TQ 0812 5534\n"
            "Planning application: PL/2023/1847/OUT\n"
            "Survey date: 14 May 2024\n"
        ),
        must_remove=[
            "Ockham Road North", "East Horsley", "KT24 6RY",
            "Bloor Homes South East Ltd", "EC-4471-PEA-02",
            "Jennifer Hartley", "2021-52341-CLS-CLS",
            "TQ 0812 5534", "PL/2023/1847/OUT",
        ],
        must_keep=["PRELIMINARY ECOLOGICAL APPRAISAL", "MCIEEM", "May 2024"],
        note=(
            "The survey month must survive. Whether a bat survey happened in "
            "May or in November decides whether it is valid at all, so a "
            "redactor that eats the date destroys the reader's ability to "
            "judge the finding."
        ),
    ),
    Passage(
        name="habitat-with-site-name",
        text=(
            "The Ockham Road frontage supports 0.8 ha of species-poor "
            "semi-improved grassland, dominated by Lolium perenne and Holcus "
            "lanatus with occasional Plantago lanceolata. The hedgerow along "
            "the northern boundary of the Bloor Homes ownership qualifies as "
            "a Priority Habitat under the NERC Act 2006 and was scored "
            "Moderate condition under UKHab."
        ),
        must_remove=["Ockham Road", "Bloor Homes"],
        must_keep=[
            "0.8 ha", "species-poor semi-improved grassland", "Lolium perenne",
            "Holcus lanatus", "Plantago lanceolata", "Priority Habitat",
            "NERC Act 2006", "Moderate", "UKHab",
        ],
        note=(
            "The hard case. The identifier is mid-sentence in the most "
            "valuable paragraph in the document, so removing it and keeping "
            "the finding are the same operation."
        ),
    ),
    Passage(
        name="species-authorities",
        text=(
            "Two mature Quercus robur L. and a single Fraxinus excelsior L. "
            "were recorded within the northern hedgerow. A soprano "
            "pipistrelle Pipistrellus pygmaeus was recorded foraging along "
            "the treeline at dusk. Surveys were undertaken by J. Hartley and "
            "R. Okonkwo."
        ),
        must_remove=["J. Hartley", "R. Okonkwo"],
        must_keep=[
            "Quercus robur L.", "Fraxinus excelsior L.",
            "Pipistrellus pygmaeus", "soprano pipistrelle",
        ],
        note=(
            "The precision trap. `L.` is Linnaeus, the botanical authority, "
            "and any rule that treats `X. Surname` as a person eats the "
            "taxonomy — which is most of what an ecological record is."
        ),
    ),
    Passage(
        name="bng-metric",
        text=(
            "Baseline habitat value was calculated at 4.62 habitat units. "
            "The post-development scheme delivers 5.31 units, a net gain of "
            "14.9 per cent, exceeding the 10 per cent mandatory requirement. "
            "Figures were produced using the Statutory Biodiversity Metric. "
            "The applicant, Persimmon Homes Thames Valley, has committed to a "
            "30-year management plan."
        ),
        must_remove=["Persimmon Homes Thames Valley"],
        must_keep=[
            "4.62", "5.31", "14.9 per cent", "Statutory Biodiversity Metric",
            "30-year management plan",
        ],
        note=(
            "`Persimmon` is a plant genus. A botanical allowlist protecting "
            "species names would protect the developer's name with it."
        ),
    ),
]


# ---------------------------------------------------------------------------
# HELD OUT — written before the redactor, not consulted while writing it.
# These are the numbers to quote.
# ---------------------------------------------------------------------------
HELDOUT_CORPUS: List[Passage] = [
    Passage(
        name="contact-block",
        text=(
            "For further information please contact Sarah Mbeki-Wright at "
            "sarah.mbeki-wright@thomsonecology.co.uk or on 01483 466 000. "
            "The site was visited on 3 October 2023 by the author, "
            "accompanied by the landowner Mr T. Feltham of Manor Farm."
        ),
        must_remove=[
            "Sarah Mbeki-Wright", "sarah.mbeki-wright@thomsonecology.co.uk",
            "01483 466 000", "T. Feltham", "Manor Farm",
        ],
        must_keep=["October 2023"],
        note=(
            "A double-barrelled surname, an email that contains it, and a "
            "landowner named in passing — the last being the one a consultant "
            "would never think to check before uploading."
        ),
    ),
    Passage(
        name="grid-reference-variants",
        text=(
            "The site is centred on NGR SU 89345 47218 (51.2354 N, 0.5712 W) "
            "and comprises 2.4 ha of arable land bounded to the east by the "
            "A247 and to the south by the Guildford to Effingham railway."
        ),
        must_remove=[
            "SU 89345 47218", "51.2354 N", "0.5712 W", "A247",
            "Guildford", "Effingham",
        ],
        must_keep=["2.4 ha", "arable"],
        note=(
            "Three coordinate formats in one sentence, plus two quasi-"
            "identifiers that name no person and locate the site to within a "
            "few hundred metres. A road number is a coordinate."
        ),
    ),
    Passage(
        name="abbreviated-client",
        text=(
            "BHSE instructed this appraisal in March 2024. Bloor's land agent "
            "confirmed that the eastern parcel is outside the red line "
            "boundary. Great crested newt Triturus cristatus eDNA returned a "
            "positive result in Pond 2, and a District Level Licence has been "
            "obtained."
        ),
        must_remove=["BHSE", "Bloor's"],
        must_keep=[
            "Triturus cristatus", "Great crested newt", "eDNA",
            "District Level Licence", "Pond 2",
        ],
        note=(
            "The client returns as an acronym and as a possessive. A redactor "
            "that matched the full company string in the header will sail "
            "past both."
        ),
    ),
    Passage(
        name="clean-findings",
        text=(
            "The grassland is of low botanical diversity and is not "
            "considered to meet the criteria for Priority Habitat. Badger "
            "activity was recorded in the form of a single outlier sett with "
            "two entrances, both showing signs of current use. Mitigation "
            "should follow CIEEM good practice guidance."
        ),
        must_remove=[],
        must_keep=[
            "low botanical diversity", "Priority Habitat", "outlier sett",
            "two entrances", "CIEEM",
        ],
        note=(
            "The control. Nothing here identifies anybody, so a redactor that "
            "damages this passage is destroying value for no safety gain — "
            "the failure mode that a leak-rate-only metric cannot see. Note "
            "that badger sett locations are themselves sensitive, which is a "
            "separate problem from identifying the client."
        ),
    ),
]


ALL_CORPUS = DEV_CORPUS + HELDOUT_CORPUS
