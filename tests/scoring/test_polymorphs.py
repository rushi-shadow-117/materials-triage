"""Polymorph selection and the summary the bundle carries."""

from materials_triage.records.bundle import ExclusionRule
from materials_triage.scoring.polymorphs import select_scored, summarize_group


def test_hfo2_summary_counts_and_top_five(baseline_groups) -> None:  # type: ignore[no-untyped-def]
    g = baseline_groups["HfO2"]
    s = summarize_group(g, scored=select_scored(g), cutoff_mev=94.0).polymorphs
    assert s.composition_id == "HfO2" and s.total == 15
    assert (s.observed_count, s.theoretical_count, s.unknown_count) == (5, 10, 0)
    assert s.ground_state is not None and s.ground_state.mp_id == "mp-352"
    assert s.lowest_observed is not None and s.lowest_observed.mp_id == "mp-352"
    assert s.scored is not None and s.scored.mp_id == "mp-352"
    assert s.ground_state_is_theoretical is False
    hulls = [r.hull_energy.value for r in s.top_by_hull if r.hull_energy]
    assert len(s.top_by_hull) == 5 and hulls == sorted(hulls) and hulls[0] == 0.0  # type: ignore[type-var]
    assert all(r.excluded_rule is None for r in s.top_by_hull)
    assert s.ground_state.hull_energy is not None
    assert s.ground_state.hull_energy.provenance.source_record_id == "mp-352"
    assert "jarvis_tbmbj" in s.ground_state.band_gap


def test_requested_rocksalt_beo_is_marked_above_cutoff(baseline_groups) -> None:  # type: ignore[no-untyped-def]
    g = baseline_groups["BeO"]
    scored = select_scored(g, requested_mp="mp-1794")
    assert scored is not None and scored.spacegroup_symbol == "Fm-3m" and 163825 in scored.ids.icsd
    s = summarize_group(g, scored=scored, cutoff_mev=94.0).polymorphs
    assert s.scored is not None and s.scored.excluded_rule is ExclusionRule.STABILITY_CUTOFF
    assert s.ground_state is not None and s.ground_state.mp_id == "mp-2542"
    assert s.scored.hull_energy is not None and s.scored.hull_energy.value * 1000 > 400  # type: ignore[operator]


def test_unknown_requested_id_scores_nothing(baseline_groups) -> None:  # type: ignore[no-untyped-def]
    assert select_scored(baseline_groups["HfO2"], requested_mp="mp-999999999") is None
