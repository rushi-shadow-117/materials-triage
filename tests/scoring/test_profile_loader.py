"""The scorer's loaders accept only entered values where weight depends on them."""

from pathlib import Path

import pytest
import yaml

from materials_triage.config import schema as cs
from materials_triage.records.bundle import Caveat, CaveatId
from materials_triage.render.caveats import CaveatConfig
from materials_triage.scoring.profile import (
    UnusableEntryError,
    echa_attribution,
    load_hazard_policy,
    load_reference_values,
    load_scoring_profile,
    load_site_profile,
)

PATHS = cs.default_paths()
PROFILES = cs.CONFIG_DIR / "scoring_profiles"


def test_dielectric_profile_loads_with_the_owner_values() -> None:
    loaded = load_scoring_profile(PROFILES / "oxide_dielectric_thin_film.yaml")
    p = loaded.profile
    assert p.name == "oxide_dielectric_thin_film"
    assert (p.stability.cutoff_mev_per_atom, p.stability.near_cutoff_band_mev_per_atom) == (94, 24)
    assert p.band_gap.soft_preference_start_ev == 5.0
    assert p.band_gap.hard_min_ev is None and p.band_gap.hard_max_ev is None
    # Derived by Track E from the band gap calibration (conflict_tolerance_derivation in the file).
    assert p.band_gap.conflict_tolerance_ev == 1.345
    assert not any("not compared" in n for n in loaded.notes)
    assert p.weights == {
        "stability": 1.0,
        "band_gap": 1.0,
        "hazard": 1.0,
        "simplicity": 1.0,
        "evidence": 1.0,
        "dielectric_constant": 0.0,
        "deposition_method": 0.0,
        "cost": 0.0,
    }
    assert p.dielectric_constant.target_band is None  # pending verification, weight 0
    assert p.anchors == ["SiO2"] and p.synonyms["HfO2"] == ["hafnia", "hafnium dioxide"]
    assert loaded.evidence_tiers["dielectric_characterized"] == 1.0
    assert set(loaded.standing_caveats) == {
        "band_offsets_not_checked",
        "stability_cutoff_hull_mismatch",
        "stability_cutoff_oxide_calibrated",
    }


def test_photocatalyst_profile_has_the_window_and_no_anchor() -> None:
    p = load_scoring_profile(PROFILES / "oxide_photocatalyst.yaml").profile
    assert (p.band_gap.hard_min_ev, p.band_gap.hard_max_ev) == (2.0, 3.3)
    assert p.band_gap.soft_preference_start_ev is None and p.anchors == []


def test_weight_on_a_pending_entry_raises(tmp_path: Path) -> None:
    data = yaml.safe_load((PROFILES / "oxide_dielectric_thin_film.yaml").read_text())
    data["weights"]["values"]["dielectric_constant"] = 0.5  # target band is pending
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump(data))
    with pytest.raises(UnusableEntryError, match="dielectric_constant"):
        load_scoring_profile(bad)
    data["weights"]["values"]["dielectric_constant"] = 0.0
    data["criteria"]["stability"]["status"] = "pending_signoff"
    bad.write_text(yaml.safe_dump(data))
    with pytest.raises(UnusableEntryError, match="stability"):
        load_scoring_profile(bad)
    data["criteria"]["stability"]["status"] = "entered"
    data["weights"]["status"] = "open"
    bad.write_text(yaml.safe_dump(data))
    with pytest.raises(UnusableEntryError, match="weights"):
        load_scoring_profile(bad)


def test_site_profile_reads_bounds_defaults_methods_and_attribution() -> None:
    site = load_site_profile(PATHS["site_profile"])
    assert set(site.weight_bounds) == set(cs.CRITERIA)
    assert site.weight_bounds["band_gap"].max == 1.0
    assert site.top_n_max == 50 and site.radioactive_exclusion_locked is True
    assert site.default_view is cs.View.PI_SUMMARY
    assert len(site.deposition_methods) == 9 and "ALD" in site.deposition_methods
    assert len(site.screen_cannot_tell_you) == 7
    echa = echa_attribution(PATHS["site_profile"])
    assert echa is not None and echa[0].startswith("Source: European Chemicals Agency")


def test_hazard_policy_loads_only_entered_rules() -> None:
    hp = load_hazard_policy(PATHS["hazard_policy"])
    assert set(hp.exclude_elements) == {"As", "Be", "Cd", "Ni"}
    assert set(hp.flag_elements) == {"Cr"}
    assert {
        "Th",
        "U",
        "Tc",
        "Pm",
    } <= hp.radioactive_elements and "Bi" not in hp.radioactive_elements
    assert hp.acute_exclude_codes == {"H300", "H310", "H330", "H360"}
    assert hp.acute_compound_tiers["HgO"].tier == "exclude"
    assert hp.acute_compound_tiers["BaTiO3"].tier == "unknown"
    assert {k: v.tier for k, v in hp.acute_element_tiers.items()} == {
        "Tl": "exclude",
        "Ba": "flag",
        "Hg": "exclude",
        "Pb": "exclude",
    }
    assert hp.ghs_flag_codes == {"H340", "H341", "H350", "H351", "H361", "H370"}
    assert hp.ghs_other_codes_ref == "hazard_policy.yaml#tiers.ghs_other_codes_rule"
    assert set(hp.process_hazard_classifications) == {"SiO2", "TiO2"}
    assert (
        hp.process_hazard_template
        and "{material_specific_classification}" in hp.process_hazard_template
    )
    assert hp.unknown_rule_ref is not None
    assert all(e.source_ref.startswith("hazard_policy.yaml#") for e in hp.exclude_elements.values())


def test_reference_values_split_by_status_with_deterministic_provenance() -> None:
    a = load_reference_values(PATHS["reference_values"])
    b = load_reference_values(PATHS["reference_values"])
    assert [r.entry_id for r in a.entered] == [r.entry_id for r in b.entered]
    assert a.entered[0].provenance == b.entered[0].provenance
    entered = {r.entry_id: r for r in a.entered}
    pending = {r.entry_id: r for r in a.pending}
    assert (
        "sio2_gap_robertson2004" in pending and pending["sio2_gap_robertson2004"].value is not None
    )
    assert pending["sio2_gap_robertson2004"].value.value is None  # type: ignore[union-attr]
    assert entered["tho2_gap_single_crystal_mock2019"].value.value == 5.4  # type: ignore[union-attr]
    assert entered["al2o3_gap_amorphous_ald_range"].value is None
    assert entered["al2o3_gap_amorphous_ald_range"].value_range == (6.0, 7.0)
    assert all(r.provenance.source == "config" for r in a.entered)


def test_site_hazard_weight_floor_clamps_and_is_reported() -> None:
    site = load_site_profile(PATHS["site_profile"])
    assert site.weight_bounds["hazard"].min == 0.1
    loaded = load_scoring_profile(PROFILES / "oxide_dielectric_thin_film.yaml")
    query = cs.QuerySettings(profile=loaded.profile.name, weights={"hazard": 0.0})
    effective, clamps = cs.resolve(cs.CoreConfig(), site, loaded.profile, query)
    assert effective.weights["hazard"] == 0.1
    assert [(c.setting, c.requested, c.applied, c.bound) for c in clamps] == [
        ("weights.hazard", 0.0, 0.1, "site.weight_bounds.hazard")
    ]


def test_calibration_caveat_is_a_standing_caveat_with_entered_text() -> None:
    for name in ("oxide_dielectric_thin_film", "oxide_photocatalyst"):
        loaded = load_scoring_profile(PROFILES / f"{name}.yaml")
        assert loaded.standing_caveats["stability_cutoff_oxide_calibrated"] == (
            f"scoring_profiles/{name}.yaml#criteria.stability.anion_calibration_caveat"
        )
        text = CaveatConfig.load(PROFILES / f"{name}.yaml").resolve(
            Caveat(id=CaveatId.STABILITY_CUTOFF_OXIDE_CALIBRATED, subject="AlN")
        )
        assert text.entered and text.text.startswith("The 94 meV/atom stability cutoff")
