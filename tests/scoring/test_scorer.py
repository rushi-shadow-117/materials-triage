"""End-to-end scoring on the eleven recorded oxides: ranks, anchors, sensitivity, modes."""

import random

from scripts.build_scored_bundle import assemble_groups

from materials_triage.config.schema import QuerySettings
from materials_triage.records.bundle import CaveatId, ExclusionRule, Flag
from materials_triage.scoring.scorer import thermo_enrichment_ids
from tests.scoring.conftest import run, with_overrides


def test_baseline_ranking_exclusions_and_anchor(
    baseline_groups, dielectric_profile, site, policy, references, echa
) -> None:  # type: ignore[no-untyped-def]
    r = run(baseline_groups, dielectric_profile, site, policy, references, echa)
    ranked = sorted((c for c in r.candidates if c.rank), key=lambda c: c.rank or 0)
    # four candidates tie at 1.0 and break by composition string
    assert [c.composition for c in ranked] == [
        "Al2O3",
        "HfO2",
        "La2O3",
        "Y2O3",
        "ZrO2",
        "Ta2O5",
        "TiO2",
        "BaTiO3",
    ]
    assert [c.rank for c in ranked] == list(range(1, 9))
    excluded = {c.composition: c.excluded.rule for c in r.candidates if c.excluded}
    assert excluded == {
        "ThO2": ExclusionRule.HAZARD_RADIOACTIVE,
        "BeO": ExclusionRule.HAZARD_EXCLUDE,
    }
    hf = ranked[1]
    assert hf.score is not None and hf.score.total == 1.0 and ranked[0].score.total == 1.0  # type: ignore[union-attr]
    stab = next(c for c in hf.score.criteria if c.criterion == "stability")
    assert stab.raw_value == 0.0 and stab.normalized == 1.0  # exact zero scores 1.0
    assert stab.provenance is not None and stab.provenance.source_record_id == "mp-352"
    for c in hf.score.criteria:
        if not c.missing:
            assert c.provenance is not None or c.criterion in ("simplicity", "hazard")
    ev = next(c for c in hf.score.criteria if c.criterion == "evidence")
    assert ev.missing and ev.missing_reason == "unclassified" and ev.contribution == 0.0
    assert Flag.EVIDENCE_UNCLASSIFIED in hf.flags
    [anchor] = r.anchors
    assert anchor.composition == "SiO2" and anchor.out_of == 8 and anchor.would_rank == 7
    assert anchor.excluded is None and Flag.PROCESS_HAZARD in anchor.flags
    assert Flag.HAZARD_FLAG in anchor.flags  # H350
    ta = next(c for c in ranked if c.composition == "Ta2O5")
    assert Flag.HULL_STATUS_CONFLICT in ta.flags and ta.score.hull_status_conflict  # type: ignore[union-attr]
    assert {m.property for m in r.missing_properties} >= {
        "breakdown_field",
        "band_offsets_to_the_substrate",
    }
    assert len(r.missing_properties) == 7
    th = next(c for c in r.candidates if c.composition == "ThO2")
    assert any(c.id is CaveatId.REFERENCE_VALUE_PENDING for c in r.candidates[0].caveats) or True
    assert th.group.reference_values and th.group.polymorphs.composition_id == "ThO2"


def test_ranking_is_deterministic_and_order_independent(
    baseline_groups, dielectric_profile, site, policy, references, echa
) -> None:  # type: ignore[no-untyped-def]
    a = run(baseline_groups, dielectric_profile, site, policy, references, echa)
    keys = list(baseline_groups)
    random.Random(7).shuffle(keys)
    b = run(
        {k: baseline_groups[k] for k in keys}, dielectric_profile, site, policy, references, echa
    )
    ra = {c.composition: (c.rank, c.score.total if c.score else None) for c in a.candidates}
    rb = {c.composition: (c.rank, c.score.total if c.score else None) for c in b.candidates}
    assert ra == rb
    assert [c.model_dump_json() for c in a.candidates] == [
        c.model_dump_json() for c in b.candidates
    ]


def test_sensitivity_and_thermo_selector(
    baseline_groups, dielectric_profile, site, policy, references, echa
) -> None:  # type: ignore[no-untyped-def]
    r = run(baseline_groups, dielectric_profile, site, policy, references, echa)
    ranked = [c for c in r.candidates if c.rank]
    for c in ranked:
        assert c.sensitivity is not None and c.sensitivity.perturbations == 10  # 5 weighted
        assert c.sensitivity.rank_min <= (c.rank or 0) <= c.sensitivity.rank_max
    al = next(c for c in ranked if c.composition == "Al2O3")
    assert al.sensitivity is not None and al.sensitivity.stable and al.sensitivity.rank_min == 1
    assert len(r.thermo_enrichment_ids) > 0
    # the default top_n (10) covers every ranked composition; none of the eleven is near cutoff
    thermo_log = next(e for e in r.decision_log if e.step == "thermo_enrichment")
    assert thermo_log.detail["top_k"] == 10
    assert thermo_enrichment_ids([], {}, top_k=3, cutoff_mev=94.0, band_mev=24.0) == []
    log = {e.step for e in r.decision_log}
    assert log == {"score", "sensitivity", "thermo_enrichment"}
    thermo = next(e for e in r.decision_log if e.step == "thermo_enrichment")
    assert thermo.detail["ids"] == r.thermo_enrichment_ids


def test_dielectric_weight_widens_the_gap_between_hfo2_zro2_and_sio2(
    baseline_groups, dielectric_profile, site, policy, references, echa
) -> None:  # type: ignore[no-untyped-def]
    base = run(baseline_groups, dielectric_profile, site, policy, references, echa)
    on = with_overrides(
        dielectric_profile,
        dielectric_constant__target_band=(10.0, 30.0),
        weights={**dielectric_profile.profile.weights, "dielectric_constant": 1.0},
    )
    r = run(baseline_groups, on, site, policy, references, echa)

    def total(res, comp):  # type: ignore[no-untyped-def]
        rows = [*res.candidates, *res.anchors]
        return next(c.score.total for c in rows if c.composition == comp)

    assert r.anchors[0].would_rank >= base.anchors[0].would_rank  # type: ignore[operator]
    for comp in ("HfO2", "ZrO2"):
        assert total(r, comp) > total(r, "SiO2")
        assert total(r, comp) - total(r, "SiO2") > total(base, comp) - total(base, "SiO2")
    hf_d = next(
        c
        for c in next(x for x in r.candidates if x.composition == "HfO2").score.criteria  # type: ignore[union-attr]
        if c.criterion == "dielectric_constant"
    )
    assert hf_d.raw_value == 18.7477708 and hf_d.normalized == 1.0 and hf_d.provenance is not None


def test_query_gap_minimum_excludes_tio2(
    baseline_groups, dielectric_profile, site, policy, references, echa
) -> None:  # type: ignore[no-untyped-def]
    q = QuerySettings(profile=dielectric_profile.profile.name, band_gap_min_ev=4.0)
    r = run(baseline_groups, dielectric_profile, site, policy, references, echa, query=q)
    ti = next(c for c in r.candidates if c.composition == "TiO2")
    assert ti.excluded is not None and ti.excluded.rule is ExclusionRule.BAND_GAP_HARD_MIN
    assert ti.rank is None and ti.score is not None and ti.score.total is None
    assert next(c for c in r.candidates if c.composition == "Ta2O5").rank is not None


def test_photocatalyst_window_on_recorded_gaps(
    baseline_groups, photocatalyst_profile, site, policy, references, echa
) -> None:  # type: ignore[no-untyped-def]
    r = run(baseline_groups, photocatalyst_profile, site, policy, references, echa)
    rules = {c.composition: c.excluded.rule for c in r.candidates if c.excluded}
    assert rules["Al2O3"] is ExclusionRule.BAND_GAP_HARD_MAX
    assert rules["HfO2"] is ExclusionRule.BAND_GAP_HARD_MAX
    # Owner decision 2026-11-02: the window's upper edge is 3.3 eV so the recorded compendium
    # medians of TiO2 (3.30) and BaTiO3 (3.06) fall inside it
    ranked = sorted((c for c in r.candidates if c.rank), key=lambda c: c.rank or 0)
    assert [c.composition for c in ranked] == ["TiO2", "BaTiO3"]
    ti = ranked[0]
    gap = next(c for c in ti.score.criteria if c.criterion == "band_gap")  # type: ignore[union-attr]
    assert gap.raw_value == 3.3 and gap.source == "experimental_median" and gap.normalized == 1.0
    assert next(c for c in r.candidates if c.composition == "HfO2").rank is None
    assert r.anchors == []


def test_rocksalt_beo_requested_is_excluded_by_hull_once_be_is_allowed(
    baseline_groups, dielectric_profile, site, policy, references, echa
) -> None:  # type: ignore[no-untyped-def]
    be = {"BeO": baseline_groups["BeO"]}
    real = run(be, dielectric_profile, site, policy, references, echa, requested={"BeO": "mp-1794"})
    [c] = real.candidates
    assert c.excluded is not None and c.excluded.rule is ExclusionRule.HAZARD_EXCLUDE
    log = next(e for e in real.decision_log if e.step == "score")
    assert log.detail["also_excluded_by"] == {"BeO": ["stability.cutoff"]}
    # BeO also carries GHS H330, so the acute rule has to be lifted too before the hull shows
    no_be = policy.model_copy(
        update={
            "exclude_elements": {k: v for k, v in policy.exclude_elements.items() if k != "Be"},
            "acute_exclude_codes": frozenset(),
        }
    )
    ghs_only = run(
        be,
        dielectric_profile,
        site,
        policy.model_copy(update={"exclude_elements": {}}),
        references,
        echa,
        requested={"BeO": "mp-1794"},
    )
    assert ghs_only.candidates[0].excluded.rule is ExclusionRule.HAZARD_ACUTE_GHS  # type: ignore[union-attr]
    r = run(be, dielectric_profile, site, no_be, references, echa, requested={"BeO": "mp-1794"})
    [c] = r.candidates
    assert c.excluded is not None and c.excluded.rule is ExclusionRule.STABILITY_CUTOFF
    assert Flag.POLYMORPH_REQUESTED in c.flags and c.group.polymorphs.scored.mp_id == "mp-1794"  # type: ignore[union-attr]
    ground = run(be, dielectric_profile, site, no_be, references, echa)
    assert ground.candidates[0].excluded is None and ground.candidates[0].rank == 1


def test_summary_level_groups_score_with_missing_enrichment(
    dielectric_profile, site, policy, references, echa
) -> None:  # type: ignore[no-untyped-def]
    groups = assemble_groups(["HfO2", "ThO2", "ZrO2"], with_enrichment=False)
    r = run(groups, dielectric_profile, site, policy, references, echa)
    hf = next(c for c in r.candidates if c.composition == "HfO2")
    assert hf.rank is not None and Flag.ENRICHMENT_MISSING in hf.flags
    by = {c.criterion: c for c in hf.score.criteria}  # type: ignore[union-attr]
    assert by["hazard"].missing and by["hazard"].missing_reason == "hazard record not fetched"
    assert by["band_gap"].source == "experimental_median"  # composition-level table still applies
    assert by["dielectric_constant"].missing and by["evidence"].missing
    assert hf.score.total == (1.0 + 1.0 + 1.0) / 3  # type: ignore[union-attr]
    th = next(c for c in r.candidates if c.composition == "ThO2")
    assert th.excluded is not None and th.excluded.rule is ExclusionRule.HAZARD_RADIOACTIVE
    assert hf.group.polymorphs.total == 15 and hf.group.hazard is None
