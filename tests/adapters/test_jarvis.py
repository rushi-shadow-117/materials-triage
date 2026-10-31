from materials_triage.adapters import jarvis, mp
from materials_triage.adapters.transport import HttpxTransport
from materials_triage.records import MissingReason
from materials_triage.records.matching import match_polymorphs
from tests.adapters.conftest import SNAPSHOTS


def _load(manifest):  # type: ignore[no-untyped-def]
    entry = manifest["jarvis_dft_3d"]
    return jarvis.load_slice(
        SNAPSHOTS / "jarvis_dft_3d.slice.json", full_file_sha256=entry["sha256"]
    )


def test_slice_loads_with_snapshot_provenance(manifest) -> None:  # type: ignore[no-untyped-def]
    raw = _load(manifest)
    recs = jarvis.records(raw)
    assert len(recs) == 205
    assert all(r.provenance.source_version == manifest["jarvis_dft_3d"]["sha256"] for r in recs)
    assert all(r.provenance.raw_sha256 == raw.sha256 for r in recs)


def test_na_sentinel_is_missing_and_zero_stays_zero(manifest) -> None:  # type: ignore[no-untyped-def]
    polys = {p.ids.jarvis_jid: p for p in jarvis.polymorphs(jarvis.records(_load(manifest)))}
    p = polys["JVASP-153820"]  # ThO2 Pnma: mbj_bandgap is "na" in the snapshot
    assert p.band_gap["jarvis_tbmbj"].value is None
    assert p.band_gap["jarvis_tbmbj"].missing_reason == MissingReason.NA_SENTINEL
    assert p.band_gap["jarvis_optb88vdw"].value is not None
    ground = polys["JVASP-1169"]
    assert ground.hull_energy["jarvis_optb88vdw"].value == 0.0
    assert ground.band_gap["jarvis_tbmbj"].value == 5.013
    assert isinstance(ground.spacegroup_number, int) and ground.spacegroup_number == 225


def test_icsd_parsing() -> None:
    assert jarvis.parse_icsd("") == [] and jarvis.parse_icsd(None) == []
    assert jarvis.parse_icsd("170516") == [170516]
    many = ",".join(str(i) for i in range(70))
    assert len(jarvis.parse_icsd(many)) == 70
    assert jarvis.parse_icsd("12, abc, 7") == [7, 12]


def test_icsd_first_match_to_materials_project(
    manifest, transport: HttpxTransport, cassette
) -> None:  # type: ignore[no-untyped-def]
    with cassette("mp", "summary_ThO2"):
        mp_polys = mp.assemble(
            mp.summary_records(transport.get(mp.plan_summary_by_formula("ThO2")))
        ).polymorphs
    jv = [p for p in jarvis.polymorphs(jarvis.records(_load(manifest))) if p.composition == "ThO2"]
    matches = {
        (m.left.ids.mp, m.right.ids.jarvis_jid): m.rule.value
        for m in match_polymorphs(mp_polys, jv)
    }
    assert matches[("mp-643", "JVASP-1169")] == "icsd_intersection"
    assert matches[("mp-1102569", "JVASP-153820")] == "composition_spacegroup"
