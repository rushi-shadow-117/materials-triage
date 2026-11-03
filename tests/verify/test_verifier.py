"""Planted fabrications are caught; real formulas, ids, and rounded numbers pass."""

from __future__ import annotations

from pathlib import Path

import pytest

from materials_triage.records.bundle import (
    EvidenceHit,
    EvidenceLabel,
    ProvenanceBundle,
    RationaleSlot,
)
from materials_triage.render import tokens
from materials_triage.verify import verifier as v
from materials_triage.verify.quotes import EMPTY, NOT_FOUND, check_quote

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "fixtures" / "bundles" / "sample_bundle.json"
SLOT = "candidate:HfO2:one_line"


@pytest.fixture(scope="module")
def bundle() -> ProvenanceBundle:
    return ProvenanceBundle.model_validate_json(SAMPLE.read_text())


@pytest.fixture(scope="module")
def index(bundle: ProvenanceBundle) -> tokens.BundleIndex:
    return tokens.BundleIndex.build(bundle)


@pytest.fixture(scope="module")
def scope(bundle: ProvenanceBundle, index: tokens.BundleIndex) -> v.SlotScope:
    s = v.scope_for(bundle, index, SLOT)
    assert s is not None
    return s


def _check(text: str, scope: v.SlotScope, index: tokens.BundleIndex) -> v.SentenceCheck:
    return v.check_sentence(text, scope, index)


# ----------------------------------------------------------------------- planted fabrications


def test_invented_record_id_is_caught(scope: v.SlotScope, index: tokens.BundleIndex) -> None:
    r = _check("The ground state is mp-999999999 in the database.", scope, index)
    assert (r.ok, r.kind, r.fragment) == (False, "unknown_record_id", "mp-999999999")


def test_wrong_number_is_caught(scope: v.SlotScope, index: tokens.BundleIndex) -> None:
    r = _check("The band gap is 7.3 eV.", scope, index)
    assert (r.ok, r.kind, r.fragment) == (False, "unresolved_number", "7.3")


def test_number_hidden_in_a_formula_like_token_is_caught(
    scope: v.SlotScope, index: tokens.BundleIndex
) -> None:
    for planted in ("Hf2O5", "HfO2.5", "Hf3O7"):
        r = _check(f"The phase {planted} is stable.", scope, index)
        assert (r.ok, r.kind, r.fragment) == (False, "formula_not_in_bundle", planted), planted


def test_unknown_template_token_is_caught(scope: v.SlotScope, index: tokens.BundleIndex) -> None:
    r = _check("{formula:PbO} is better.", scope, index)
    assert (r.ok, r.kind) == (False, "formula_not_in_bundle")
    r = _check("{id:mp-1} is the record.", scope, index)
    assert (r.ok, r.kind) == (False, "unknown_record_id")


def test_oxidation_state_token_needs_the_element_in_the_composition(
    scope: v.SlotScope, index: tokens.BundleIndex
) -> None:
    r = _check("Contains Cr(VI).", scope, index)
    assert (r.ok, r.kind, r.fragment) == (False, "formula_not_in_bundle", "Cr(VI)")
    assert _check("Hf(IV) is the oxidation state.", scope, index).ok


# ----------------------------------------------------------------------- real content passes


def test_real_formulas_ids_years_and_rounded_numbers_pass(
    scope: v.SlotScope, index: tokens.BundleIndex
) -> None:
    good = [
        "{formula:HfO2} ranks {rank:HfO2} on {criterion:stability}.",
        "HfO2 is the composition and mp-352 its ground state.",
        "The experimental gap is 5.55 eV, about 5.6 eV, or 5550 meV.",
        "JVASP-43367 and W2024600253 are records; https://openalex.org/W2024600253 too.",
        "PubChem CID:292779 reports 344 notifications in 2015.",
        "Films grown by CVD, ALD, or PLD; see Fig. 2 of Smith et al. for ZrO2.",
        "The hull energy is 0.000 eV/atom and there are 15 polymorphs.",
        "Ranked 2 of 8 candidates.",
    ]
    for text in good:
        r = _check(text, scope, index)
        assert r.ok, (text, r.kind, r.fragment)


def test_bare_acronyms_are_not_formulas_and_carry_no_numbers(
    scope: v.SlotScope, index: tokens.BundleIndex
) -> None:
    assert _check("Deposited by CVD and characterized by XPS.", scope, index).ok
    r = _check("Fig. 2 of Smith et al. is CVD at 400 degrees.", scope, index)
    assert (r.ok, r.fragment) == (False, "400")


def test_renderer_output_round_trips_through_the_verifier(
    bundle: ProvenanceBundle, index: tokens.BundleIndex
) -> None:
    for row in [*bundle.candidates, *bundle.anchors]:
        kind = "anchor" if row.composition == "SiO2" else "candidate"
        scope = v.scope_for(bundle, index, f"{kind}:{row.composition}:x")
        assert scope is not None
        for units in ("eV", "meV"):
            for crit in ("stability", "band_gap", "simplicity", "evidence", "dielectric_constant"):
                rendered = tokens.resolve(index, "value", f"{row.composition}:{crit}", units=units)
                r = _check(f"The value is {rendered}.", scope, index)
                assert r.ok, (row.composition, crit, rendered, r.fragment)
            for fld in ("polymorphs", "hits", "matched", "notifications"):
                rendered = tokens.resolve(index, "count", f"{row.composition}:{fld}")
                assert _check(f"There are {rendered}.", scope, index).ok, (row.composition, fld)
            assert _check(tokens.resolve(index, "ghs", row.composition) + ".", scope, index).ok


# ----------------------------------------------------------------------- slot removal


def test_failing_sentence_is_removed_whole_and_logged(
    scope: v.SlotScope, index: tokens.BundleIndex
) -> None:
    slot = RationaleSlot(
        slot=SLOT,
        text="A sentence citing mp-999. {formula:HfO2} is ranked {rank:HfO2}. Gap near 7.3 eV!",
        verified=False,
    )
    checked, failures = v.verify_slot(slot, scope, index)
    assert checked.text == "{formula:HfO2} is ranked {rank:HfO2}."
    assert checked.verified is False
    assert checked.removed_fragments == ["A sentence citing mp-999.", "Gap near 7.3 eV!"]
    assert [(f.kind, f.fragment, f.action) for f in failures] == [
        ("unknown_record_id", "A sentence citing mp-999.", "removed"),
        ("unresolved_number", "Gap near 7.3 eV!", "removed"),
    ]


def test_clean_slot_is_verified_and_empty_slot_is_not(
    scope: v.SlotScope, index: tokens.BundleIndex
) -> None:
    clean, failures = v.verify_slot(
        RationaleSlot(slot=SLOT, text="{formula:HfO2} ranks {rank:HfO2}.", verified=False),
        scope,
        index,
    )
    assert clean.verified is True and failures == []
    gone, failures = v.verify_slot(
        RationaleSlot(slot=SLOT, text="Gap of 7.3 eV.", verified=True), scope, index
    )
    assert gone.text == "" and gone.verified is False and len(failures) == 1


def test_sentence_split_is_deterministic_and_protects_abbreviations() -> None:
    text = "See Smith et al. for details. The gap is large! Is it stable? {formula:HfO2} is."
    assert v.split_sentences(text) == [
        "See Smith et al. for details.",
        "The gap is large!",
        "Is it stable?",
        "{formula:HfO2} is.",
    ]
    assert v.split_sentences(text) == v.split_sentences(text)


# ----------------------------------------------------------------------- evidence quotes


def test_quote_check_is_exact_substring_and_rejects_empty() -> None:
    assert check_quote("the cat sat", "and the cat sat down").ok
    assert check_quote("The cat sat", "and the cat sat down").note == NOT_FOUND
    assert check_quote("   ", "x").note == EMPTY
    assert check_quote(None, "x").note == EMPTY
    assert check_quote("x", None).ok is False


def test_paraphrased_quote_is_dropped_and_verbatim_quote_passes(bundle: ProvenanceBundle) -> None:
    out, report = v.verify(bundle)
    assert report.checked_evidence == 2 and report.checked_slots == 8
    assert [e.verified for e in out.evidence] == [True, False]
    assert [(f.kind, f.action) for f in report.failures] == [("quote_mismatch", "hit_dropped")]
    assert report.passed is False and out.verifier == report
    assert all(s.verified for s in out.rationale.values())


def test_fulltext_hit_is_never_verified_and_never_above_computed_only(
    bundle: ProvenanceBundle,
) -> None:
    real = bundle.evidence[0]
    hit = real.model_copy(
        update={"quote_verifiable": False, "label": EvidenceLabel.THIN_FILM_DEPOSITED}
    )
    checked, failure = v.verify_evidence(bundle, hit)
    assert failure is None
    assert checked.verified is False and checked.verifier_note == v.FULLTEXT_NOTE
    assert checked.label == EvidenceLabel.COMPUTED_ONLY


def test_evidence_for_an_unknown_work_is_dropped(bundle: ProvenanceBundle) -> None:
    hit = EvidenceHit(
        composition="HfO2",
        openalex_id="https://openalex.org/W0000000009",
        label=EvidenceLabel.THIN_FILM_DEPOSITED,
        deposition_method=None,
        supporting_sentence="anything",
        verified=True,
        provenance=bundle.evidence[0].provenance,
    )
    checked, failure = v.verify_evidence(bundle, hit)
    assert checked.verified is False and failure is not None
    assert (failure.kind, failure.action) == ("unknown_record_id", "hit_dropped")


def test_slot_with_an_unknown_composition_is_dropped_whole(bundle: ProvenanceBundle) -> None:
    bad = bundle.model_copy(
        update={
            "rationale": {
                "candidate:PbO:one_line": RationaleSlot(
                    slot="candidate:PbO:one_line", text="{formula:PbO} is fine.", verified=True
                )
            }
        }
    )
    out, report = v.verify(bad)
    assert out.rationale == {} and report.failures[0].kind == "unknown_record_id"


def test_ghs_codes_are_accepted_only_when_the_bundle_reports_them(
    bundle: ProvenanceBundle, index: tokens.BundleIndex, scope: v.SlotScope
) -> None:
    r = _check("PubChem lists H350 for this compound.", scope, index)
    assert (r.ok, r.kind, r.fragment) == (False, "unresolved_number", "H350")
    anchor_scope = v.scope_for(bundle, index, "anchor:SiO2:one_line")
    assert anchor_scope is not None
    assert _check("Codes H315 and H350i appear in the notifications.", anchor_scope, index).ok


def test_not_relevant_and_no_abstract_skip_the_quote_check(bundle: ProvenanceBundle) -> None:
    real = bundle.evidence[0]
    for label in (EvidenceLabel.NOT_RELEVANT, EvidenceLabel.NO_ABSTRACT):
        hit = real.model_copy(update={"label": label, "supporting_sentence": None})
        checked, failure = v.verify_evidence(bundle, hit)
        assert failure is None and checked.verified is False and checked.label == label


def test_the_four_tiers_always_need_a_verbatim_sentence(bundle: ProvenanceBundle) -> None:
    real = bundle.evidence[0]
    for label in v.TIER_LABELS:
        missing = real.model_copy(update={"label": label, "supporting_sentence": None})
        checked, failure = v.verify_evidence(bundle, missing)
        assert failure is not None and failure.kind == "quote_mismatch", label
        assert checked.verified is False and checked.verifier_note == EMPTY
        verbatim = real.model_copy(update={"label": label})
        checked, failure = v.verify_evidence(bundle, verbatim)
        assert failure is None and checked.verified is True, label
