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


THIN_FILM = ("amorphous_film", "thin_film", "crystalline_bulk", "compendium")
CRYSTALLINE = ("crystalline_bulk", "compendium", "thin_film", "amorphous_film")
COMPENDIUM_FIRST = ("compendium", "crystalline_bulk", "thin_film", "amorphous_film")


def test_tho2_pool_never_aggregates_across_forms(baseline_groups, references) -> None:  # type: ignore[no-untyped-def]
    """Human test session, item 4: one form only; the others are kept and shown, not used."""
    g = baseline_groups["ThO2"]
    refs = [r for r in references.entered if r.composition == "ThO2"]
    assert {e.form for e in experimental_pool(g.experimental_gaps, refs, CRYSTALLINE).entries} == {
        "compendium",
        "thin_film",
        "crystalline_bulk",
    }
    crystalline = experimental_pool(g.experimental_gaps, refs, CRYSTALLINE)
    assert crystalline.form == "crystalline_bulk" and crystalline.points == [5.4]
    assert (crystalline.low, crystalline.high) == (5.4, 7.0)  # the 6 to 7 eV range in that form
    assert crystalline.n_sources == 2
    assert crystalline.other_forms == ["compendium", "thin_film"]
    film = experimental_pool(g.experimental_gaps, refs, THIN_FILM)
    assert film.form == "thin_film" and film.points == [5.9]
    compendium = experimental_pool(g.experimental_gaps, refs, COMPENDIUM_FIRST)
    assert sorted(compendium.points) == [3.3, 3.5]
    assert {e.provenance.source for e in compendium.entries if e.used} == {"expt_gap"}


def test_tho2_conflict_fires_under_a_test_tolerance_and_falls_to_tbmbj(
    baseline_groups, references
) -> None:  # type: ignore[no-untyped-def]
    g = baseline_groups["ThO2"]
    o = outcome(g, references, conflict_tolerance_ev=0.5, preferred_forms=COMPENDIUM_FIRST)
    assert o.candidates["experimental"].value == 3.4 and o.candidates["tbmbj"].value == 5.013
    assert o.conflict is True and Flag.BAND_GAP_CONFLICT in o.result.flags
    assert o.source_used == "tbmbj" and o.result.raw_value == 5.013
    assert o.result.provenance is not None and o.result.provenance.source == "jarvis_dft_3d"
    minimum = outcome(
        g,
        references,
        conflict_tolerance_ev=0.5,
        on_conflict=OnConflict.MINIMUM,
        preferred_forms=COMPENDIUM_FIRST,
    )
    assert minimum.source_used == "conflict_minimum" and minimum.result.raw_value == 3.4


def test_no_tolerance_means_shown_but_not_compared(baseline_groups, references) -> None:  # type: ignore[no-untyped-def]
    o = outcome(baseline_groups["ThO2"], references, preferred_forms=COMPENDIUM_FIRST)
    assert o.conflict is False and Flag.BAND_GAP_SOURCES_UNCOMPARED in o.result.flags
    assert o.source_used == "experimental_median" and o.result.raw_value == 3.4
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
    # Al2O3 has no compendium row; crystalline first gives the 8.7 eV point, never a median
    # across the amorphous 6.6 and the crystalline 8.7 (the old 7.65)
    a = outcome(baseline_groups["Al2O3"], references)
    assert a.source_used == "experimental_median" and a.result.raw_value == 8.7
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


def test_al2o3_thin_film_uses_its_film_value(baseline_groups, references) -> None:  # type: ignore[no-untyped-def]
    """Human test session, item 4: the thin-film profile scores Al2O3's amorphous-film point
    (6.6 eV); the crystalline 8.7 eV and the 6 to 7 eV film range are shown, not used."""
    a = outcome(baseline_groups["Al2O3"], references, preferred_forms=THIN_FILM)
    assert a.source_used == "experimental_median" and a.result.raw_value == 6.6
    assert a.result.used_record_ids == ("reference_values.yaml#al2o3_gap_amorphous_ald_point",)
    assert any(
        "form amorphous_film" in n and "not used: crystalline_bulk" in n for n in a.result.notes
    )


def test_profiles_declare_their_form_order(dielectric_profile) -> None:  # type: ignore[no-untyped-def]
    from materials_triage.scoring.profile import load_scoring_profile
    from tests.scoring.conftest import PROFILES

    assert dielectric_profile.profile.band_gap.preferred_forms == THIN_FILM
    for name in ("oxide_photocatalyst", "nitride_wide_gap"):
        loaded = load_scoring_profile(PROFILES / f"{name}.yaml")
        assert loaded.profile.band_gap.preferred_forms == CRYSTALLINE


def _pbe_only(group: CompositionGroup, gap_ev: float) -> Polymorph:
    """The group's scored polymorph with every gap but a PBE one of `gap_ev` removed."""
    p = select_scored(group)
    assert p is not None
    pbe = p.band_gap["mp_summary"].model_copy(update={"value": gap_ev})
    return p.model_copy(update={"band_gap": {"mp_summary": pbe}})


def _nitride_like(scored: Polymorph, *, query_min_ev: float | None = None):  # type: ignore[no-untyped-def]
    return band_gap(
        scored,
        experimental=None,
        references=[],
        settings=settings(
            soft_preference_start_ev=None, hard_min_ev=4.0, discovery_pbe_floor_ev=2.4
        ),
        query_min_ev=query_min_ev,
        query_max_ev=None,
        source_ref="profile#criteria.band_gap",
        standing_caveat_ref=None,
    )


def test_pbe_only_between_floor_and_minimum_is_kept_and_flagged(baseline_groups) -> None:  # type: ignore[no-untyped-def]
    """Human test session, item 5: PBE-only gaps are excluded only below the PBE floor."""
    kept = _nitride_like(_pbe_only(baseline_groups["HfO2"], 3.0))
    assert kept.result.exclusion is None and kept.result.normalized == 1.0
    assert Flag.PBE_ONLY_BELOW_WINDOW in kept.result.flags
    assert [c.id for c in kept.result.caveats] == [CaveatId.PBE_ONLY_BELOW_WINDOW]
    at_floor = _nitride_like(_pbe_only(baseline_groups["HfO2"], 2.4))
    assert at_floor.result.exclusion is None
    below = _nitride_like(_pbe_only(baseline_groups["HfO2"], 2.0))
    assert below.result.exclusion is not None
    assert below.result.exclusion.rule is ExclusionRule.BAND_GAP_HARD_MIN
    assert Flag.PBE_ONLY_BELOW_WINDOW not in below.result.flags
    above = _nitride_like(_pbe_only(baseline_groups["HfO2"], 4.5))
    assert above.result.exclusion is None and Flag.PBE_ONLY_BELOW_WINDOW not in above.result.flags


def test_pbe_window_never_relaxes_a_scientists_minimum(baseline_groups) -> None:  # type: ignore[no-untyped-def]
    o = _nitride_like(_pbe_only(baseline_groups["HfO2"], 3.0), query_min_ev=5.0)
    assert o.result.exclusion is not None and "5 eV minimum" in o.result.exclusion.detail


def test_pbe_window_needs_pbe_to_be_the_only_source(baseline_groups) -> None:  # type: ignore[no-untyped-def]
    """With a TBmBJ or experimental value present, the hard minimum applies as written."""
    p = select_scored(baseline_groups["HfO2"])
    assert p is not None and "jarvis_tbmbj" in p.band_gap
    two = {k: v for k, v in p.band_gap.items() if k in ("mp_summary", "jarvis_tbmbj")}
    two["jarvis_tbmbj"] = two["jarvis_tbmbj"].model_copy(update={"value": 3.0})
    o = _nitride_like(p.model_copy(update={"band_gap": two}))
    assert o.result.exclusion is not None and Flag.PBE_ONLY_BELOW_WINDOW not in o.result.flags


def test_pbe_window_caveat_text_comes_from_each_profile() -> None:
    from materials_triage.records.bundle import Caveat
    from materials_triage.render.caveats import CaveatConfig
    from tests.scoring.conftest import PROFILES

    for name in ("oxide_dielectric_thin_film", "oxide_photocatalyst", "nitride_wide_gap"):
        text = CaveatConfig.load(PROFILES / f"{name}.yaml").resolve(
            Caveat(id=CaveatId.PBE_ONLY_BELOW_WINDOW)
        )
        assert text.entered, name
        assert text.text == (
            "Only a computed PBE gap is available; PBE typically underestimates gaps "
            "(Materials Project documentation)."
        )


def test_a_jarvis_value_names_its_own_record(baseline_groups, references) -> None:  # type: ignore[no-untyped-def]
    """The rule text cites the JARVIS record, matched to the MP polymorph, not the MP id alone."""
    o = outcome(baseline_groups["HfO2"], references)
    tb = o.candidates["tbmbj"]
    record = tb.provenance.source_record_id
    assert record.startswith("JVASP-")
    assert tb.detail == f"jarvis_tbmbj on {record}, matched to mp-352"
    pbe = o.candidates["pbe"]
    assert pbe.detail == "mp_summary on mp-352"
