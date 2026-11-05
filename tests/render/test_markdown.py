"""Rendered views match golden files, read the polymorph summary only, and resolve caveats."""

from __future__ import annotations

import csv
import io
import os
from pathlib import Path

import pytest

from materials_triage.config import schema as cs
from materials_triage.records.bundle import Caveat, CaveatId, ProvenanceBundle
from materials_triage.render import caveats, csv_export, glossary, markdown
from materials_triage.verify.verifier import verify

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "fixtures" / "bundles" / "sample_bundle.json"
GOLDEN = Path(__file__).parent / "golden"
REGEN = os.environ.get("REGEN_GOLDEN") == "1"


def _golden(name: str, text: str) -> None:
    path = GOLDEN / name
    if REGEN or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    assert path.read_text() == text, f"{name} changed; set REGEN_GOLDEN=1 to accept"


@pytest.fixture(scope="module")
def bundle() -> ProvenanceBundle:
    raw = ProvenanceBundle.model_validate_json(SAMPLE.read_text())
    verified, _ = verify(raw)
    return verified


@pytest.fixture(scope="module")
def site() -> cs.SiteProfile:
    return cs.site_profile_from_yaml(cs.default_paths()["site_profile"])


@pytest.fixture(scope="module")
def caveat_config() -> caveats.CaveatConfig:
    return caveats.CaveatConfig.load()


def _with_settings(bundle: ProvenanceBundle, **settings: str) -> ProvenanceBundle:
    crit = bundle.criteria.model_copy(
        update={"effective_settings": {**bundle.criteria.effective_settings, **settings}}
    )
    return bundle.model_copy(update={"criteria": crit})


@pytest.mark.parametrize("view", ["pi_summary", "audit"])
@pytest.mark.parametrize("units", ["eV", "meV"])
@pytest.mark.parametrize("terminology", ["technical", "general"])
def test_views_match_golden(
    bundle: ProvenanceBundle,
    site: cs.SiteProfile,
    caveat_config: caveats.CaveatConfig,
    view: str,
    units: str,
    terminology: str,
) -> None:
    b = _with_settings(bundle, units=units, terminology=terminology)
    text = markdown.render(b, view=view, site=site, caveats=caveat_config)
    _golden(f"{view}_{units}_{terminology}.md", text)


def test_pi_summary_has_the_planned_sections(
    bundle: ProvenanceBundle, site: cs.SiteProfile
) -> None:
    text = markdown.render_pi_summary(bundle, site)
    assert "| 1= | Al2O3 |" in text and "| 1= | HfO2 |" in text
    assert "Equal scores are tied; tied rows are listed alphabetically." in text
    assert "HfO2 ranks 1= on stability (energy above hull) and band gap; see caveats." in text
    assert "SiO2 (reference): would place 1st of 9, above Al2O3" in text
    assert "ThO2: hazard.radioactive_exclude" in text and "BeO: hazard.exclude" in text
    assert "band_offsets_not_checked: Band offsets to the substrate are not checked" in text
    assert "- breakdown field" in text and "leakage current density" in text
    assert "thin_film_deposited" in text  # HfO2's verified evidence tier
    assert "failures removed (1 failure(s))" in text


def test_audit_view_shows_values_with_provenance_and_the_polymorph_summary_only(
    bundle: ProvenanceBundle, site: cs.SiteProfile
) -> None:
    text = markdown.render_audit(bundle, site)
    assert "- Config sha: " + bundle.run.config_sha in text
    assert "Source versions: materials_project=2026.09.28" in text
    assert "| band gap | 5.55 eV | experimental_median |" in text
    assert "Polymorphs: 15 with MP ids (5 observed, 10 theoretical, 0 unknown)." in text
    assert "- Ground state: mp-352 (P2_1/c), hull 0.000 eV/atom, observed" in text
    assert text.count("- mp-") <= sum(
        len(c.group.polymorphs.top_by_hull) for c in [*bundle.candidates, *bundle.anchors]
    )
    assert "Hazard: no GHS hazard codes in 344 notifications (ECHA attribution applies)" in text
    assert 'verified quote: "Here, we present a structural study' in text
    assert "quote_mismatch" in text  # the dropped hit is listed under Verifier only
    assert "## Verifier" in text and "quote_mismatch at evidence:" in text
    assert "## Decision log" in text and "pipeline build_sample" in text
    excluded_line = (
        "Excluded: hazard.radioactive_exclude (['Th'] has no stable isotope); "
        "rule source config/hazard_policy.yaml#tiers.radioactive_exclude"
    )
    assert excluded_line in text


def test_mev_units_flow_through_the_values(bundle: ProvenanceBundle, site: cs.SiteProfile) -> None:
    text = markdown.render_audit(_with_settings(bundle, units="meV"), site)
    assert "| band gap | 5550 meV |" in text and "hull 0 meV/atom" in text


def test_glossary_applies_only_in_general_terminology(
    bundle: ProvenanceBundle, site: cs.SiteProfile
) -> None:
    glossed = site.model_copy(
        update={"glossary": {"band gap": "energy gap", "hull": "stability margin"}}
    )
    technical = markdown.render_pi_summary(_with_settings(bundle, terminology="technical"), glossed)
    general = markdown.render_pi_summary(_with_settings(bundle, terminology="general"), glossed)
    assert "band gap" in technical and "energy gap" not in technical
    assert "energy gap" in general and "band gap" not in general
    assert glossary.apply("the band gap and bandgap", {"band gap": "x"}) == "the x and bandgap"
    assert glossary.apply("band gap energy", {"band gap": "a", "band gap energy": "b"}) == "b"


def test_unverified_llm_bundle_is_refused(site: cs.SiteProfile) -> None:
    raw = ProvenanceBundle.model_validate_json(SAMPLE.read_text())
    llm_run = raw.model_copy(
        update={"run": raw.run.model_copy(update={"model_version": "m"}), "verifier": None}
    )
    with pytest.raises(markdown.UnverifiedBundleError):
        markdown.render_pi_summary(llm_run, site)
    with pytest.raises(ValueError, match="unknown view"):
        markdown.render(raw, view="pdf", site=site)


def test_caveat_resolver_uses_entered_config_text_and_marks_the_rest(
    caveat_config: caveats.CaveatConfig,
) -> None:
    r = caveat_config.resolve
    assert r(Caveat(id=CaveatId.BAND_OFFSETS_NOT_CHECKED)).text.startswith("Band offsets")
    assert r(Caveat(id=CaveatId.STABILITY_CUTOFF_HULL_MISMATCH)).text.startswith("The 94 meV/atom")
    cr = r(Caveat(id=CaveatId.HAZARD_FLAG, subject="Cr"))
    assert cr.entered and "Cr(VI)" in cr.text and cr.source.endswith("tiers.flag.Cr")
    ba = r(Caveat(id=CaveatId.HAZARD_FLAG, subject="Ba"))
    assert ba.entered and "barium" in ba.text.lower()
    unknown_el = r(Caveat(id=CaveatId.HAZARD_FLAG, subject="Xx"))
    assert not unknown_el.entered and unknown_el.text == "caveat text not entered: hazard_flag"
    assert r(Caveat(id=CaveatId.HAZARD_UNKNOWN)).text.startswith(
        "A compound with no PubChem record"
    )
    sio2 = r(Caveat(id=CaveatId.PROCESS_HAZARD, subject="SiO2"))
    assert (
        sio2.text.startswith("Particulate hazard during processing")
        and "Crystalline silica" in sio2.text
    )
    assert "{material_specific_classification}" not in sio2.text
    hfo2 = r(Caveat(id=CaveatId.PROCESS_HAZARD, subject="HfO2"))
    assert "Crystalline silica" not in hfo2.text and "  " not in hfo2.text
    assert r(Caveat(id=CaveatId.EVIDENCE_UNCLASSIFIED)).source == "system"
    echa = r(Caveat(id=CaveatId.ATTRIBUTION_ECHA))
    assert echa.entered or echa.text == "caveat text not entered: attribution_echa"


def test_ghs_flag_set_caveat_is_filled_from_the_row_record(
    caveat_config: caveats.CaveatConfig, bundle: ProvenanceBundle
) -> None:
    """SiO2 carries H350 (in the flag set): the owner's sentence names the codes and the
    notification counts from the PubChem record; without the row there is no text to invent."""
    sio2 = next(a for a in bundle.anchors if a.composition == "SiO2")
    assert sio2.group.hazard is not None and "H350" in sio2.group.hazard.h_codes
    with_row = caveat_config.resolve(Caveat(id=CaveatId.HAZARD_FLAG, subject="SiO2"), sio2)
    assert with_row.entered and with_row.source.endswith("ghs_flag_codes.caveat_template")
    assert with_row.text.startswith("Flagged: a suspected carcinogenic") and "H350" in with_row.text
    total = sio2.group.hazard.notifications_total
    assert total is not None and f"of {total} notifications" in with_row.text
    without = caveat_config.resolve(Caveat(id=CaveatId.HAZARD_FLAG, subject="SiO2"))
    assert not without.entered


def test_csv_has_one_row_per_candidate_and_anchor(bundle: ProvenanceBundle) -> None:
    text = csv_export.export_csv(bundle)
    rows = list(csv.DictReader(io.StringIO(text)))
    assert len(rows) == len(bundle.candidates) + len(bundle.anchors)
    assert rows[0]["composition"] == "Al2O3" and rows[0]["rank"] == "1"
    hf = next(r for r in rows if r["composition"] == "HfO2")
    assert hf["band_gap_raw"] == "5.55" and hf["band_gap_unit"] == "eV"
    assert hf["stability_raw"] == "0.000" and hf["ground_state_mp_id"] == "mp-352"
    assert hf["caveats"] == "band_offsets_not_checked" and hf["polymorph_count"] == "15"
    th = next(r for r in rows if r["composition"] == "ThO2")
    assert th["rank"] == "" and th["excluded_rule"] == "hazard.radioactive_exclude"
    si = next(r for r in rows if r["kind"] == "anchor")
    assert si["would_rank"] == "1" and si["out_of"] == "9"  # the anchor counts itself
    assert hf["cross_checked"] == "yes"
    mev = list(csv.DictReader(io.StringIO(csv_export.export_csv(bundle, units="meV"))))
    assert next(r for r in mev if r["composition"] == "HfO2")["band_gap_unit"] == "meV"
    _golden("export.csv", text)


def test_equal_totals_render_as_tied(bundle: ProvenanceBundle, site: cs.SiteProfile) -> None:
    """Human test session, item 7: four rows at 1.000 read as ranks 1 to 4 in name order."""
    from materials_triage.render.tokens import shown_ranks

    ranks = shown_ranks(bundle)
    totals: dict[str, list[str]] = {}
    for c in bundle.ranked():
        assert c.score is not None and c.score.total is not None
        totals.setdefault(f"{c.score.total:.3f}", []).append(c.composition)
    for group in totals.values():
        first = ranks[group[0]].rank
        assert all(ranks[g].rank == first for g in group)
        assert all(ranks[g].tied == (len(group) > 1) for g in group)
    text = markdown.render_pi_summary(bundle, site)
    tied = [g for g in totals.values() if len(g) > 1]
    assert tied, "the sample bundle has a tie"
    assert f"| {ranks[tied[0][0]].rank}= | {tied[0][0]} |" in text
    csv_text = csv_export.export_csv(bundle)
    assert ",yes," in csv_text  # the tied column


def test_key_caveat_is_the_most_row_specific_one() -> None:
    """Human test session, item 8: every row's key caveat was the standing band offsets
    sentence. The key caveat now follows the priority; profile-wide caveats show once above
    the table and never per row."""
    from materials_triage.render import views
    from materials_triage.render.caveats import KEY_PRIORITY, PROFILE_WIDE, key_caveat

    scored = Path(__file__).resolve().parents[2] / "fixtures" / "bundles" / "scored_bundle.json"
    bundle = ProvenanceBundle.model_validate_json(scored.read_text())
    cfg = caveats.CaveatConfig.load()
    view = views.build(bundle, cfg, units="eV", hide_ids=True)
    tio2 = next(r for r in view.rows if r.composition == "TiO2")
    assert tio2.key_caveat.startswith("Flagged: a suspected carcinogenic")
    band_offsets = cfg.resolve(Caveat(id=CaveatId.BAND_OFFSETS_NOT_CHECKED)).text
    for r in [*view.rows, *view.excluded, *view.anchors]:
        assert r.key_caveat != band_offsets, r.composition
        assert all(c.id not in PROFILE_WIDE for c in r.caveats), r.composition
    assert [c.text for c in view.profile_caveats].count(band_offsets) == 1
    # the composition-level gap note is profile-wide too (owner decision, Nov 4)
    composition_level = cfg.resolve(Caveat(id=CaveatId.EXPERIMENTAL_GAP_COMPOSITION_LEVEL)).text
    assert composition_level in [c.text for c in view.profile_caveats]
    assert all(r.key_caveat != composition_level for r in [*view.rows, *view.excluded])
    # priority over a synthetic row: hazard first, then the gap conflict, then the rest
    row = [Caveat(id=i) for i in (CaveatId.NEAR_CUTOFF, CaveatId.BAND_GAP_CONFLICT)]
    assert key_caveat(row) == Caveat(id=CaveatId.BAND_GAP_CONFLICT)
    row.append(Caveat(id=CaveatId.HAZARD_FLAG, subject="Ti"))
    assert key_caveat(row) is not None and key_caveat(row).id is CaveatId.HAZARD_FLAG  # type: ignore[union-attr]
    assert key_caveat([Caveat(id=CaveatId.BAND_OFFSETS_NOT_CHECKED)]) is None
    assert KEY_PRIORITY[0] is CaveatId.HAZARD_FLAG


def test_flag_caveats_carry_the_owner_texts() -> None:
    from materials_triage.scoring.scorer import FLAG_CAVEATS

    cfg = caveats.CaveatConfig.load()
    texts = {f.value: cfg.resolve(Caveat(id=c)).text for f, c in FLAG_CAVEATS.items()}
    assert texts == {
        "band_gap_conflict": "The experimental and computed band gaps disagree beyond the "
        "profile's tolerance; see the audit view.",
        "near_cutoff": "Energy above hull is close to this profile's stability cutoff.",
        "ground_state_is_theoretical": "The lowest-energy polymorph on record is computed, "
        "not observed.",
    }


def test_record_url_links_materials_project_ids_in_older_bundles() -> None:
    from datetime import UTC, datetime

    from materials_triage.records import Provenance, record_url

    def prov(source: str, rid: str, url: str | None = None) -> Provenance:
        return Provenance(
            source=source,
            source_record_id=rid,
            raw_response_id=None,
            raw_sha256="0" * 64,
            fetched_at=datetime(2026, 11, 4, tzinfo=UTC),
            url=url,
        )

    assert record_url(prov("materials_project", "mp-352")) == (
        "https://next-gen.materialsproject.org/materials/mp-352"
    )
    assert record_url(prov("pubchem", "CID:1", "https://x/1")) == "https://x/1"
    assert record_url(prov("expt_gap", "expt_gap:3:HfO2")) is None
