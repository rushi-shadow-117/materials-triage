from pathlib import Path

import pytest

from materials_triage.config import schema as cs

ROOT = Path(__file__).resolve().parents[1]


def _profile(**over) -> cs.ScoringProfile:  # type: ignore[no-untyped-def]
    base = dict(
        name="test",
        stability=cs.StabilitySettings(cutoff_mev_per_atom=94, near_cutoff_band_mev_per_atom=24),
        band_gap=cs.BandGapSettings(soft_preference_start_ev=5.0),
    )
    base.update(over)
    return cs.ScoringProfile(**base)  # type: ignore[arg-type]


def test_precedence_and_clamping_reports_every_clamp() -> None:
    site = cs.SiteProfile(
        weight_bounds={
            **{c: cs.Bounds() for c in cs.CRITERIA},
            "band_gap": cs.Bounds(min=0.2, max=0.8),
        },
        top_n_max=20,
    )
    query = cs.QuerySettings(
        profile="test",
        weights={"band_gap": 5.0, "hazard": 0.5},
        top_n=99,
        exclude_radioactive=False,
    )
    eff, clamps = cs.resolve(cs.CoreConfig(), site, _profile(), query)
    assert eff.weights["band_gap"] == 0.8 and eff.weights["hazard"] == 0.5
    assert eff.top_n == 20 and eff.exclude_radioactive is True
    assert {c.setting for c in clamps} == {"weights.band_gap", "top_n", "exclude_radioactive"}
    assert all(c.bound.startswith("site.") for c in clamps)


def test_query_defaults_fall_back_to_site_then_fragments_are_fixed() -> None:
    site = cs.SiteProfile(default_view=cs.View.AUDIT, default_verbosity=cs.Verbosity.CONCISE)
    eff, clamps = cs.resolve(cs.CoreConfig(), site, _profile(), cs.QuerySettings(profile="test"))
    assert clamps == [] and eff.view is cs.View.AUDIT and eff.verbosity is cs.Verbosity.CONCISE
    assert eff.fragments == {
        "verbosity": "verbosity.concise",
        "terminology": "terminology.technical",
        "units": "units.eV",
        "view": "view.audit",
    }


def test_same_settings_same_sha_and_different_settings_differ() -> None:
    site = cs.SiteProfile()
    a, _ = cs.resolve(cs.CoreConfig(), site, _profile(), cs.QuerySettings(profile="test", top_n=5))
    b, _ = cs.resolve(cs.CoreConfig(), site, _profile(), cs.QuerySettings(profile="test", top_n=5))
    c, _ = cs.resolve(cs.CoreConfig(), site, _profile(), cs.QuerySettings(profile="test", top_n=6))
    assert a.config_sha == b.config_sha != c.config_sha


def test_unknown_keys_and_criteria_are_rejected() -> None:
    with pytest.raises(ValueError):
        cs.QuerySettings(profile="test", bogus=1)  # type: ignore[call-arg]
    with pytest.raises(ValueError):
        cs.resolve(
            cs.CoreConfig(),
            cs.SiteProfile(),
            _profile(),
            cs.QuerySettings(profile="test", weights={"colour": 1.0}),
        )
    with pytest.raises(ValueError):
        _profile(weights={"stability": -1.0})


def test_site_can_restrict_profiles() -> None:
    with pytest.raises(ValueError, match="not allowed"):
        cs.resolve(
            cs.CoreConfig(),
            cs.SiteProfile(allowed_profiles=["other"]),
            _profile(),
            cs.QuerySettings(profile="test"),
        )


def test_every_enum_value_has_a_fragment() -> None:
    for enum, key in (
        (cs.Verbosity, "verbosity"),
        (cs.Terminology, "terminology"),
        (cs.Units, "units"),
        (cs.View, "view"),
    ):
        assert set(cs.TEMPLATE_FRAGMENTS[key]) == {e.value for e in enum}


def test_repo_yaml_files_load_and_only_entered_values_are_usable() -> None:
    paths = cs.default_paths()
    profile, notes = cs.scoring_profile_from_yaml(paths["scoring_profile"])
    assert (
        profile.stability.cutoff_mev_per_atom == 94
        and profile.stability.near_cutoff_band_mev_per_atom == 24
    )
    assert profile.band_gap.soft_preference_start_ev == 5.0
    assert profile.band_gap.conflict_tolerance_ev == 1.345  # derived by Track E, see the file
    assert (
        profile.dielectric_constant.target_band is None
        and profile.dielectric_constant.weight == 0.0
    )  # pending verification
    assert profile.anchors == ["SiO2"]
    assert any("dielectric" in n for n in notes)
    site = cs.site_profile_from_yaml(paths["site_profile"])
    assert len(site.screen_cannot_tell_you) == 7 and len(site.deposition_methods) == 9
    for name in ("hazard_policy", "reference_values"):
        entries = cs.entries_with_status(cs.load_yaml(paths[name]))
        assert entries and all(e.status in cs.EntryStatus for _, e in entries)
        assert any(e.usable for _, e in entries)


def test_query_hull_cutoff_is_clamped_to_the_site_bounds() -> None:
    paths = cs.default_paths()
    profile, _ = cs.scoring_profile_from_yaml(paths["scoring_profile"])
    site = cs.site_profile_from_yaml(paths["site_profile"])
    assert site.stability_cutoff_bounds == cs.Bounds(min=0.0, max=94.0)
    assert site.weight_bounds["hazard"].min == 0.1  # the CLI and eval path reads the bounds
    default, clamps = cs.resolve(cs.CoreConfig(), site, profile, cs.QuerySettings(profile="p"))
    assert default.stability_cutoff_mev == 94.0 and clamps == []
    on_hull, clamps = cs.resolve(
        cs.CoreConfig(), site, profile, cs.QuerySettings(profile="p", e_above_hull_max_mev=0.0)
    )
    assert on_hull.stability_cutoff_mev == 0.0 and clamps == []
    assert on_hull.config_sha != default.config_sha
    loose, clamps = cs.resolve(
        cs.CoreConfig(), site, profile, cs.QuerySettings(profile="p", e_above_hull_max_mev=2000.0)
    )
    assert loose.stability_cutoff_mev == 94.0
    assert [(c.setting, c.requested, c.applied, c.bound) for c in clamps] == [
        ("e_above_hull_max_mev", 2000.0, 94.0, "site.stability_cutoff_bounds")
    ]


def test_physical_ranges_are_clamped_and_reported() -> None:
    # review F12, owner decision 2026-11-05: band gap bounds 0 to 15 eV, element count 1 to 6
    paths = cs.default_paths()
    profile, _ = cs.scoring_profile_from_yaml(paths["scoring_profile"])
    site = cs.site_profile_from_yaml(paths["site_profile"])
    assert site.band_gap_bounds_ev == cs.Bounds(min=0.0, max=15.0)
    assert site.max_elements_bounds == cs.Bounds(min=1.0, max=6.0)
    q = cs.QuerySettings(profile="p", band_gap_min_ev=50.0, band_gap_max_ev=-2.0, max_elements=40)
    eff, clamps = cs.resolve(cs.CoreConfig(), site, profile, q)
    assert (eff.query.band_gap_min_ev, eff.query.band_gap_max_ev, eff.query.max_elements) == (
        15.0,
        0.0,
        6,
    )
    assert [(c.setting, c.requested, c.applied, c.bound) for c in clamps] == [
        ("band_gap_min_ev", 50.0, 15.0, "site.band_gap_bounds_ev"),
        ("band_gap_max_ev", -2.0, 0.0, "site.band_gap_bounds_ev"),
        ("max_elements", 40, 6, "site.max_elements_bounds"),
    ]
    ok, none = cs.resolve(
        cs.CoreConfig(), site, profile, cs.QuerySettings(profile="p", band_gap_min_ev=4.0)
    )
    assert none == [] and ok.query.band_gap_min_ev == 4.0


def test_non_finite_numbers_are_refused() -> None:
    with pytest.raises(ValueError, match="finite"):
        cs.QuerySettings(profile="p", band_gap_min_ev=float("inf"))
