"""Band gap policy on recorded data: source order, conflict rule, hard window, missing."""

from datetime import UTC, datetime

from materials_triage.config.schema import Aggregate, BandGapPolicy, BandGapSettings, OnConflict
from materials_triage.records import (
    CompositionGroup,
    Ids,
    MissingReason,
    Polymorph,
    Provenance,
    Value,
)
from materials_triage.records.bundle import CaveatId, ExclusionRule, Flag
from materials_triage.scoring.band_gap import band_gap, experimental_pool
from materials_triage.scoring.polymorphs import select_scored
from materials_triage.scoring.profile import LoadedReferenceValues


def settings(**over: object) -> BandGapSettings:
    base: dict[str, object] = dict(
        policy=BandGapPolicy.BEST_AVAILABLE,
        source_order=["experimental", "tbmbj", "pbe"],
        soft_preference_start_ev=5.0,
        aggregate=Aggregate.MEDIAN,
        conflict_tolerance_ev=None,
        on_conflict=OnConflict.NEXT_SOURCE,
    )
    base.update(over)
    return BandGapSettings(**base)  # type: ignore[arg-type]


def outcome(group: CompositionGroup, refs: LoadedReferenceValues, **over: object):  # type: ignore[no-untyped-def]
    return band_gap(
        select_scored(group),
        experimental=group.experimental_gaps,
        references=[r for r in refs.entered if r.composition == group.composition],
        settings=settings(**over),
        query_min_ev=None,
        query_max_ev=None,
        source_ref="profile#band_gap",
        standing_caveat_ref="profile#band_gap.standing_caveat",
    )


def test_tho2_pool_mixes_compendium_and_entered_reference_values(
    baseline_groups, references
) -> None:  # type: ignore[no-untyped-def]
    g = baseline_groups["ThO2"]
    pool = experimental_pool(
        g.experimental_gaps, [r for r in references.entered if r.composition == "ThO2"]
    )
    assert sorted(pool.points) == [3.3, 3.5, 5.4, 5.9]
    assert (pool.low, pool.high) == (3.3, 7.0)  # the 6 to 7 eV range widens the shown range
    assert pool.n_sources == 5
    assert {p.source for p in pool.provenances} == {"expt_gap", "config"}


def test_tho2_conflict_fires_under_a_test_tolerance_and_falls_to_tbmbj(
    baseline_groups, references
) -> None:  # type: ignore[no-untyped-def]
    g = baseline_groups["ThO2"]
    o = outcome(g, references, conflict_tolerance_ev=0.5)
    assert o.candidates["experimental"].value == 4.45 and o.candidates["tbmbj"].value == 5.013
    assert o.conflict is True and Flag.BAND_GAP_CONFLICT in o.result.flags
    assert o.source_used == "tbmbj" and o.result.raw_value == 5.013
    assert o.result.provenance is not None and o.result.provenance.source == "jarvis_dft_3d"
    minimum = outcome(g, references, conflict_tolerance_ev=0.5, on_conflict=OnConflict.MINIMUM)
    assert minimum.source_used == "conflict_minimum" and minimum.result.raw_value == 4.45


def test_no_tolerance_means_shown_but_not_compared(baseline_groups, references) -> None:  # type: ignore[no-untyped-def]
    o = outcome(baseline_groups["ThO2"], references)
    assert o.conflict is False and Flag.BAND_GAP_SOURCES_UNCOMPARED in o.result.flags
    assert o.source_used == "experimental_median" and o.result.raw_value == 4.45
    assert any("not compared" in n for n in o.result.notes)
    ids = {c.id for c in o.result.caveats}
    assert {
        CaveatId.EXPERIMENTAL_GAP_COMPOSITION_LEVEL,
        CaveatId.EXPERIMENTAL_GAP_UNREFERENCED,
        CaveatId.BAND_OFFSETS_NOT_CHECKED,
    } <= ids


def test_pbe_only_and_single_source(baseline_groups, references) -> None:  # type: ignore[no-untyped-def]
    o = outcome(baseline_groups["HfO2"], references, policy=BandGapPolicy.PBE_ONLY)
    assert o.source_used == "pbe" and o.result.raw_value is not None
    assert abs(o.result.raw_value - 4.0162) < 1e-9
    assert o.result.normalized is not None and abs(o.result.normalized - 4.0162 / 5.0) < 1e-9
    assert Flag.BAND_GAP_SINGLE_SOURCE not in o.result.flags  # three sources exist, pbe chosen
    # Al2O3 has no compendium row; entered reference values (6.6 and 8.7 points) give 7.65
    a = outcome(baseline_groups["Al2O3"], references)
    assert a.source_used == "experimental_median" and a.result.raw_value is not None
    assert abs(a.result.raw_value - 7.65) < 1e-9
    assert a.result.normalized == 1.0
    # ThO2 with references removed and no JARVIS match would be single source; synthesize it
    o2 = outcome(baseline_groups["Y2O3"], LoadedReferenceValues(entered=[], pending=[]))
    assert o2.source_used == "experimental_median"  # Y2O3 has one compendium value and PBE
    assert Flag.BAND_GAP_SINGLE_SOURCE not in o2.result.flags


def test_hard_window_uses_the_stricter_of_profile_and_query(baseline_groups, references) -> None:  # type: ignore[no-untyped-def]
    g = baseline_groups["TiO2"]
    scored = select_scored(g)
    refs = [r for r in references.entered if r.composition == "TiO2"]

    def run(**kw):  # type: ignore[no-untyped-def]
        return band_gap(
            scored,
            experimental=g.experimental_gaps,
            references=refs,
            settings=settings(**kw.pop("settings", {})),
            source_ref="r",
            standing_caveat_ref=None,
            **kw,
        )

    base = run(query_min_ev=None, query_max_ev=None)
    assert base.result.raw_value == 3.3 and base.result.exclusion is None
    tight = run(query_min_ev=4.0, query_max_ev=None)
    assert tight.result.exclusion is not None
    assert tight.result.exclusion.rule is ExclusionRule.BAND_GAP_HARD_MIN
    loose = run(query_min_ev=1.0, query_max_ev=None, settings={"hard_min_ev": 3.5})
    assert loose.result.exclusion is not None and any("looser" in n for n in loose.result.notes)
    window = run(query_min_ev=None, query_max_ev=None, settings={"hard_max_ev": 3.0})
    assert window.result.exclusion is not None
    assert window.result.exclusion.rule is ExclusionRule.BAND_GAP_HARD_MAX


def test_missing_gap_is_missing_never_zero() -> None:
    prov = Provenance(
        source="materials_project",
        source_record_id="mp-0",
        raw_response_id=None,
        raw_sha256="c" * 64,
        fetched_at=datetime(2026, 11, 2, tzinfo=UTC),
    )
    p = Polymorph(
        composition="XO2",
        spacegroup_number=1,
        spacegroup_symbol="P1",
        ids=Ids(mp="mp-0"),
        observed=None,
        hull_energy={"GGA_GGA+U_R2SCAN": Value[float](value=0.0, unit="eV/atom", provenance=prov)},
        band_gap={
            "mp_summary": Value[float](
                value=None, unit="eV", missing_reason=MissingReason.ABSENT, provenance=prov
            )
        },
        provenance=[prov],
    )
    o = band_gap(
        p,
        experimental=None,
        references=[],
        settings=settings(),
        query_min_ev=None,
        query_max_ev=None,
        source_ref="r",
        standing_caveat_ref=None,
    )
    assert o.result.normalized is None and o.result.raw_value is None
    assert o.result.exclusion is None and o.source_used is None
    assert o.result.missing_reason is not None
    assert o.result.to_score("band_gap", 1.0).contribution == 0.0
