"""The EIA-library spike, pinned in CI.

These tests do not assert that the de-identifier is good. It is not. They
assert that the *measurement* still works and that the conclusions in
`experiments/eia_library/FINDINGS.md` still hold, so that nobody reads a
six-month-old markdown file and builds an upload button on the strength of it.

Two of them are deliberately inverted — they assert that the redactor still
fails. If somebody improves it enough to pass, that is a real result and the
findings document needs rewriting; a failing test is the right way to be told.
"""

import pytest

from experiments.eia_library.corpus import ALL_CORPUS, DEV_CORPUS, HELDOUT_CORPUS
from experiments.eia_library.deidentify import redact
from experiments.eia_library.evaluate import score
from experiments.eia_library import spatial


# ---------------------------------------------------------------------------
# The corpus itself
# ---------------------------------------------------------------------------
def test_ground_truth_is_actually_present():
    """A `must_remove` string that is not in its own passage would score as a
    free success and quietly inflate every number here."""
    for p in ALL_CORPUS:
        for s in p.must_remove + p.must_keep:
            assert s.lower() in p.text.lower(), f"{p.name}: {s!r} not in the passage"


def test_dev_and_heldout_do_not_overlap():
    dev = {p.name for p in DEV_CORPUS}
    held = {p.name for p in HELDOUT_CORPUS}
    assert not (dev & held)


# ---------------------------------------------------------------------------
# Test A — the conclusions that must keep holding
# ---------------------------------------------------------------------------
def test_the_redactor_still_leaks_on_held_out_text():
    """The headline finding: pattern rules do not reach zero leaks.

    Inverted on purpose. If this fails, the redactor got better than the
    findings document says and the document is now wrong.
    """
    s = score(HELDOUT_CORPUS)
    assert s.leaks, (
        "The redactor no longer leaks on held-out text. That is good news and "
        "it invalidates FINDINGS.md — rewrite it, and take the corpus further "
        "before trusting the result."
    )


def test_the_leaks_are_the_ones_we_understand():
    """Bare settlement names and client-name variants. Both need reference
    data or uploader input, which is the design conclusion."""
    leaked = {s.lower() for s in score(HELDOUT_CORPUS).leaks}
    assert "guildford" in leaked or "effingham" in leaked, \
        "settlement names should still leak — no gazetteer is loaded"
    assert "bhse" in leaked or "bloor's" in leaked, \
        "client-name variants should still leak — the client is not declared"


def test_findings_are_not_destroyed():
    """The other half of the measurement. A redactor that removes the ecology
    is safe and worthless, and only reporting the leak rate hides that."""
    for corpus, label in ((DEV_CORPUS, "dev"), (HELDOUT_CORPUS, "heldout")):
        s = score(corpus)
        assert s.retention == 1.0, \
            f"{label}: destroyed {s.destroyed}"


def test_taxonomy_survives_person_matching():
    """`Quercus robur L.` and `J. Hartley` are the same shape. Getting this
    wrong once removed the species list; getting the guard wrong the other way
    shielded the client name behind a false species match."""
    out, _ = redact(
        "Two Quercus robur L. were recorded. Surveyed by J. Hartley."
    )
    assert "Quercus robur L." in out
    assert "Hartley" not in out


def test_a_plant_genus_is_not_a_shield_for_a_developer():
    """`Persimmon` is a genus. A botanical allowlist would protect the
    developer's name along with the species."""
    out, _ = redact("The applicant, Persimmon Homes Thames Valley, has committed.")
    assert "Persimmon Homes" not in out


def test_common_english_is_not_mistaken_for_latin():
    """The bug that cost two attempts: `Road frontage` and `Homes ownership`
    parsed as binomials, and a protected span blocks every redaction rule — so
    the false species match shielded the site and the client behind it."""
    out, _ = redact(
        "The Ockham Road frontage adjoins the Bloor Homes ownership boundary."
    )
    assert "Ockham Road" not in out
    assert "Bloor Homes" not in out


def test_valuable_phrases_are_not_read_as_people():
    """`Priority Habitat`, `Statutory Biodiversity Metric` and `District Level
    Licence` are all two or three capitalised words, exactly like a name."""
    text = ("A Priority Habitat was identified. Figures use the Statutory "
            "Biodiversity Metric and a District Level Licence was obtained.")
    out, _ = redact(text)
    for phrase in ("Priority Habitat", "Statutory Biodiversity Metric",
                   "District Level Licence"):
        assert phrase in out, f"{phrase!r} was redacted as a person"


# ---------------------------------------------------------------------------
# Test B — the spatial conclusion
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def sites():
    return spatial.make_sites()


def test_the_synthetic_sites_are_a_realistic_size(sites):
    """The descriptors are scaled for hectare-sized parcels. A generator bug
    once produced 0.0–0.6 ha sites, which would have made the matching result
    meaningless."""
    areas = [spatial.area_ha(s) for s in sites]
    assert 0.2 < min(areas) < 1.0
    assert 5.0 < max(areas) < 10.0


def test_metre_precision_fuzzing_does_not_anonymise_anything(sites):
    """Rounding a boundary to ~1 m leaves every site matchable to itself."""
    table = {r.places: r for r in spatial.fuzz_table(sites)}
    assert table[5].uniquely_matched > 0.95


def test_fuzzing_only_works_once_it_has_destroyed_the_shape(sites):
    """The trap. Rounding to ~111 m does anonymise — and a 0.3 ha parcel is
    about 60 m across, so at that point there is no boundary left to publish.
    Fuzzing that works and fuzzing that preserves the data are disjoint."""
    table = {r.places: r for r in spatial.fuzz_table(sites)}
    assert table[3].uniquely_matched < 0.2
    assert table[3].metres > min(
        spatial.perimeter_m(s) / 4 for s in sites)


def test_hiding_a_site_needs_a_cell_of_square_kilometres(sites):
    """The decisive number. Anything at or below H3 resolution 8 — a 74 ha
    cell — still identifies the site, so the library cannot answer questions
    at the scale a site screen is asked at."""
    rows = {c.resolution: c for c in spatial.cell_table(sites)}
    assert rows[8].sites_per_cell < 2
    assert rows[9].sites_per_cell < 2
    assert rows[6].sites_per_cell > 5


def test_the_k5_density_requirement_is_implausible_at_site_scale(sites):
    """Density-free version of the same finding: for a 74 ha cell to hide one
    site among five, EIA'd sites would have to occur about seven times per
    square kilometre, everywhere."""
    rows = {c.resolution: c for c in spatial.cell_table(sites)}
    assert rows[8].density_for_k5 > 5
    assert rows[6].density_for_k5 < 1
