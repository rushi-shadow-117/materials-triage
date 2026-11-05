"""The supporting sentence must name the candidate itself, not only a mixed system that contains
it (review F02). Quotes are the real ones from the review's live run of the brief."""

from __future__ import annotations

import pytest

from materials_triage.verify.subject import names_candidate

MIXED = [
    (
        "B2O3",
        "On the basis of electrical characterization, the detailed dielectric properties of SiO2 "
        "and B2O3/passivation SiO2 films were extensively discussed including the k-value, flat "
        "band voltage, and leakage currents.",
    ),
    (
        "P2O5",
        "Thin SiO 2 -P 2 O 5 -CaO films have been produced by a sol-gel process from "
        "film-forming solutions.",
    ),
    (
        "P2O5",
        "Thin films were obtained from film-forming solutions by the sol-gel method on the "
        "basis of the SiO2-P2O5-СаO system.",
    ),
    (
        "Al2O3",
        "The deposition of Li 2 O–Al 2 O 3 thin films by ALD has been accomplished by combining "
        "ALD processes for lithium oxide/hydroxide and aluminum oxide.",
    ),
    (
        "B2O3",
        "In this work, we have investigated experimentally the $c$-axis orientation process of the "
        "$L{1}_{0}$ FePt in nanostructured $\\mathrm{Fe}\\mathrm{Pt}∕{\\mathrm{B}}_{2}"
        "{\\mathrm{O}}_{3}$ thin films, and its orientation mechanism is proposed on the basis of "
        "the micromechanics concept.",
    ),
]

STANDALONE = [
    ("Al2O3", "Magnetron‐sputtered Al2O3 thin films were annealed in ambient air."),
    ("Al2O3", "Al2O3 thin films have been prepared by photo-CVD under oxygen atmosphere."),
    ("HfO2", "HfO2-based gate stacks were deposited by ALD."),
    ("HfO2", "Hafnia films were grown by sputtering."),
    ("Al2O3", "Al₂O₃ films were deposited at 200 C."),
    ("B2O3", "Films produced by co-evaporation of Ni80Fe20 and B2O3 have a columnar structure."),
    ("Al2O3", "Al2O3-coated Si wafers were annealed."),
]

SYNONYMS = {"HfO2": ["hafnia", "hafnium dioxide"], "Al2O3": ["alumina", "aluminum oxide"]}


@pytest.mark.parametrize(("composition", "sentence"), MIXED)
def test_a_mixed_system_is_not_the_candidate(composition: str, sentence: str) -> None:
    assert names_candidate(sentence, composition, SYNONYMS.get(composition, [])) is False


@pytest.mark.parametrize(("composition", "sentence"), STANDALONE)
def test_a_standalone_formula_or_synonym_names_the_candidate(
    composition: str, sentence: str
) -> None:
    assert names_candidate(sentence, composition, SYNONYMS.get(composition, [])) is True


def test_a_sentence_that_never_names_the_candidate_fails() -> None:
    sentence = (
        "First, a precursor solution of cetyltrimethylammonium bromide (C16TAB), H3PO4, ethanol, "
        "and water was deposited on a silicon substrate by a spin-coating method."
    )
    assert names_candidate(sentence, "P2O5", []) is False


def test_a_longer_formula_containing_the_candidate_is_not_the_candidate() -> None:
    assert names_candidate("La2O3 and LaAlO3 films were compared.", "AlO3", []) is False
    assert names_candidate("TiO2 was deposited.", "TiO2", []) is True
    assert names_candidate("SrTiO3 was deposited.", "TiO2", []) is False
