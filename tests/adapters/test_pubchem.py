from materials_triage.adapters import pubchem
from materials_triage.adapters.transport import HttpxTransport


def _hazard(transport: HttpxTransport, cassette, formula: str, name: str):  # type: ignore[no-untyped-def]
    with cassette("pubchem", formula):
        by_name = transport.get(pubchem.plan_cids_by_name(name))
        by_formula = transport.get(pubchem.plan_cids_by_formula(formula))
        cid, _ = pubchem.choose_cid(pubchem.cids(by_name), pubchem.cids(by_formula))
        ghs = transport.get(pubchem.plan_ghs(cid)) if cid else None
        syn = transport.get(pubchem.plan_synonyms(cid)) if cid else None
    return pubchem.hazard(formula, by_name=by_name, by_formula=by_formula, ghs=ghs, syn=syn)


def test_hfo2_counts_and_no_codes(transport: HttpxTransport, cassette) -> None:  # type: ignore[no-untyped-def]
    h = _hazard(transport, cassette, "HfO2", "hafnium dioxide")
    assert h.cid == 292779 and h.chosen_rule == "min CID from name lookup"
    assert (h.notifications_total, h.notifications_not_classified) == (344, 337)
    assert h.h_codes == [] and "Hafnia" in h.synonyms
    assert h.provenance.url == "https://pubchem.ncbi.nlm.nih.gov/compound/292779"


def test_beo_codes_present(transport: HttpxTransport, cassette) -> None:  # type: ignore[no-untyped-def]
    h = _hazard(transport, cassette, "BeO", "beryllium oxide")
    assert {"H330", "H350"} <= set(h.h_codes)
    assert h.notifications_total is not None


def test_hgo_codes_without_aggregate_counts(transport: HttpxTransport, cassette) -> None:  # type: ignore[no-untyped-def]
    h = _hazard(transport, cassette, "HgO", "mercury(II) oxide")
    assert {"H300", "H310", "H330", "H360"} <= set(h.h_codes)
    # The recorded HgO record carries codes but no "N of M" line; the parser must not invent counts.
    assert h.notifications_not_classified is None


def test_tl2o3_has_no_classification_data(transport: HttpxTransport, cassette) -> None:  # type: ignore[no-untyped-def]
    h = _hazard(transport, cassette, "Tl2O3", "thallium(III) oxide")
    assert h.cid == 3579754 and h.h_codes == [] and h.notifications_total is None
    assert "Not Classified" in " ".join(h.raw_strings)


def test_echa_attribution_flag_follows_references(transport: HttpxTransport, cassette) -> None:  # type: ignore[no-untyped-def]
    h = _hazard(transport, cassette, "SiO2", "silicon dioxide")
    assert h.references, "PUG-View GHS record should list its references"
    assert h.echa_attribution_required == any(
        "ECHA" in r or "European Chemicals Agency" in r for r in h.references
    )


def test_choose_cid_is_deterministic() -> None:
    assert pubchem.choose_cid([5, 3], [1]) == (3, "min CID from name lookup")
    assert pubchem.choose_cid([], [9, 2]) == (2, "min CID from formula lookup")
    assert pubchem.choose_cid([], []) == (None, "no CID found")


def test_hfo2_note_never_says_none_when_reports_carry_codes(
    transport: HttpxTransport, cassette
) -> None:  # type: ignore[no-untyped-def]
    # review F14: PubChem says 7 of 344 reports carry hazard codes and 337 report not classified;
    # the note read "GHS codes none in 7 of 344 notifications"
    from materials_triage.scoring.hazard import ghs_counts_text

    h = _hazard(transport, cassette, "HfO2", "hafnium dioxide")
    text = ghs_counts_text(h.h_codes, h.notifications_total, h.notifications_not_classified)
    assert text == (
        "hazard codes reported in 7 of 344 notifications (codes not listed in the record); "
        "337 report not classified"
    )
    assert "none" not in text


def test_codes_are_named_with_both_counts(transport: HttpxTransport, cassette) -> None:  # type: ignore[no-untyped-def]
    from materials_triage.scoring.hazard import ghs_counts_text

    h = _hazard(transport, cassette, "SiO2", "silicon dioxide")
    text = ghs_counts_text(h.h_codes, h.notifications_total, h.notifications_not_classified)
    assert text == (
        "GHS codes H315, H319, H320, H335, H341, H350, H350i, H372, H373 reported in 1403 of "
        "9127 notifications; 7724 report not classified"
    )
    beo = _hazard(transport, cassette, "BeO", "beryllium oxide")
    assert ghs_counts_text(beo.h_codes, beo.notifications_total, None).endswith(
        "reported across 49 notifications; the not-classified count is not reported"
    )
    no_codes = ghs_counts_text([], 10, 10)
    assert no_codes == "no hazard codes: 10 of 10 notifications report not classified"
