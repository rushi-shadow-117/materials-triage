"""Plan verification 4: the ThO2 composition group assembled from recorded data only."""

from materials_triage.adapters import expt_gap, jarvis, mp, pubchem
from materials_triage.adapters.transport import HttpxTransport
from materials_triage.records import Ids, Polymorph
from materials_triage.records.groups import build_group, merge_matches
from tests.adapters.conftest import SNAPSHOTS


def test_tho2_group_from_recordings(transport: HttpxTransport, cassette, manifest) -> None:  # type: ignore[no-untyped-def]
    with cassette("mp", "summary_ThO2"):
        summary = mp.summary_records(transport.get(mp.plan_summary_by_formula("ThO2")))
    with cassette("mp", "thermo_ThO2"):
        thermo = [
            r
            for c in mp.plan_thermo([s.source_record_id for s in summary])
            for r in mp.thermo_records(transport.get(c))
        ]
    mp_polys = mp.assemble(summary, thermo).polymorphs
    jv_raw = jarvis.load_slice(
        SNAPSHOTS / "jarvis_dft_3d.slice.json", full_file_sha256=manifest["jarvis_dft_3d"]["sha256"]
    )
    jv = [p for p in jarvis.polymorphs(jarvis.records(jv_raw)) if p.composition == "ThO2"]
    gaps_raw = expt_gap.load_slice(
        SNAPSHOTS / "expt_gap.slice.json",
        table="expt_gap",
        file_sha256=manifest["expt_gap"]["sha256"],
    )
    agg = expt_gap.aggregates(expt_gap.records(gaps_raw)[0])["ThO2"]

    merged = merge_matches(mp_polys, jv)
    group = build_group("ThO2", merged, experimental_gaps=agg)

    assert group.ground_state_mp == "mp-643" and group.ground_state_is_theoretical is False
    assert group.lowest_observed_mp == "mp-643"
    fluorite = next(p for p in group.polymorphs if p.ids.mp == "mp-643")
    assert fluorite.ids.jarvis_jid == "JVASP-1169" and fluorite.matched_by is not None
    assert fluorite.matched_by.value == "icsd_intersection"
    assert (
        fluorite.band_gap["jarvis_tbmbj"].value == 5.013
        and fluorite.band_gap["mp_summary"].value is not None
    )
    assert set(fluorite.hull_energy) >= {
        "GGA_GGA+U_R2SCAN",
        "GGA_GGA+U",
        "r2SCAN",
        "jarvis_optb88vdw",
    }
    assert (
        group.experimental_gaps.n,
        group.experimental_gaps.min,
        group.experimental_gaps.max,
    ) == (2, 3.3, 3.5)
    assert len(fluorite.provenance) == 3  # mp summary, mp thermo, jarvis slice
    assert all(p.raw_sha256 for p in fluorite.provenance)


def test_theoretical_ground_state_is_flagged_and_observed_alternative_named() -> None:
    def poly(mp_id: str, hull: float, theoretical: bool, observed: bool | None) -> Polymorph:
        from datetime import UTC, datetime

        from materials_triage.records import Provenance, Value

        prov = Provenance(
            source="materials_project",
            source_record_id=mp_id,
            raw_response_id=None,
            raw_sha256="a" * 64,
            fetched_at=datetime.now(UTC),
        )
        return Polymorph(
            composition="XO2",
            spacegroup_number=1,
            spacegroup_symbol="P1",
            ids=Ids(mp=mp_id),
            observed=observed,
            hull_energy={
                "GGA_GGA+U_R2SCAN": Value[float](value=hull, unit="eV/atom", provenance=prov)
            },
            theoretical=theoretical,
            provenance=[prov],
        )

    g = build_group("XO2", [poly("mp-2", 0.0, True, False), poly("mp-1", 0.02, False, True)])
    assert g.ground_state_mp == "mp-2" and g.ground_state_is_theoretical is True
    assert g.lowest_observed_mp == "mp-1"
    assert build_group("XO2", []).ground_state_mp is None


def test_hazard_attaches_without_interpretation(transport: HttpxTransport, cassette) -> None:  # type: ignore[no-untyped-def]
    with cassette("pubchem", "HfO2"):
        by_name = transport.get(pubchem.plan_cids_by_name("hafnium dioxide"))
        by_formula = transport.get(pubchem.plan_cids_by_formula("HfO2"))
        ghs = transport.get(pubchem.plan_ghs(292779))
        syn = transport.get(pubchem.plan_synonyms(292779))
    h = pubchem.hazard("HfO2", by_name=by_name, by_formula=by_formula, ghs=ghs, syn=syn)
    g = build_group("HfO2", [], hazard=h)
    assert g.hazard is not None and g.hazard.notifications_total == 344 and g.hazard.h_codes == []
