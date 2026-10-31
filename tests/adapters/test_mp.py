import json
from pathlib import Path

import pytest

from materials_triage.adapters import mp
from materials_triage.adapters.base import Call, RawResponse, Source
from materials_triage.adapters.transport import HttpxTransport
from materials_triage.records import MissingReason
from tests.adapters.conftest import ROOT, synthetic_raw


def _summary(transport: HttpxTransport, cassette, formula: str):  # type: ignore[no-untyped-def]
    with cassette("mp", f"summary_{formula}"):
        return transport.get(mp.plan_summary_by_formula(formula))


def test_every_planned_url_is_allowlisted() -> None:
    calls = [
        mp.plan_heartbeat(),
        mp.plan_summary_by_formula("HfO2"),
        *mp.plan_thermo(["mp-1"]),
        *mp.plan_dielectric(["mp-1"]),
        mp.plan_discovery_page(mp.DiscoveryFilter(), 0),
        *mp.plan_summary_by_ids(["mp-1"]),
    ]
    assert all(c.url in mp.ALLOWED_URLS for c in calls)
    assert all(c.auth.value == "mp_header" for c in calls)


def test_heartbeat_gives_database_version(transport: HttpxTransport, cassette) -> None:  # type: ignore[no-untyped-def]
    with cassette("mp", "heartbeat"):
        version = mp.parse_heartbeat(transport.get(mp.plan_heartbeat()))
    assert version.count(".") == 2 and version.startswith("20")


def test_tho2_summary_two_polymorphs_fluorite_stable_at_exactly_zero(
    transport: HttpxTransport, cassette
) -> None:  # type: ignore[no-untyped-def]
    raw = _summary(transport, cassette, "ThO2")
    assembly = mp.assemble(mp.summary_records(raw))
    by_id = {p.ids.mp: p for p in assembly.polymorphs}
    assert set(by_id) == {"mp-643", "mp-1102569"}
    fluorite = by_id["mp-643"]
    assert fluorite.spacegroup_symbol == "Fm-3m" and fluorite.spacegroup_number == 225
    hull = fluorite.hull_energy[mp.MIXED_HULL]
    assert hull.value == 0.0 and hull.value is not None and hull.missing_reason is None
    assert fluorite.is_stable[mp.MIXED_HULL] is True and fluorite.theoretical is False
    assert 61586 in fluorite.ids.icsd and fluorite.observed is True
    assert fluorite.ids.mp_raw is not None and fluorite.ids.mp_raw != "mp-643"
    assert all(p.provenance[0].raw_sha256 == raw.sha256 for p in assembly.polymorphs)


def test_license_values_seen_in_real_data_are_reported(transport: HttpxTransport, cassette) -> None:  # type: ignore[no-untyped-def]
    raw = _summary(transport, cassette, "HfO2")
    licenses = {r.license for r in mp.summary_records(raw)}
    assert mp.NON_COMMERCIAL_LICENSE not in licenses
    # Recorded for the findings note: what builder_meta.license the API reports for this account.
    Path(ROOT / "fixtures" / "adapters" / "mp" / "licenses_seen.json").write_text(
        json.dumps(sorted(str(x) for x in licenses)) + "\n"
    )


def test_thermo_for_explicit_ids_adds_per_functional_hull(
    transport: HttpxTransport, cassette
) -> None:  # type: ignore[no-untyped-def]
    summary = mp.summary_records(_summary(transport, cassette, "ThO2"))
    ids = [r.source_record_id for r in summary]
    with cassette("mp", "thermo_ThO2"):
        thermo = [
            rec for call in mp.plan_thermo(ids) for rec in mp.thermo_records(transport.get(call))
        ]
    polys = {p.ids.mp: p for p in mp.assemble(summary, thermo).polymorphs}
    assert set(polys["mp-643"].hull_energy) == {mp.MIXED_HULL, "GGA_GGA+U", "r2SCAN"}
    assert polys["mp-643"].hull_status_conflict is False
    assert all(v.value == 0.0 for v in polys["mp-643"].hull_energy.values())


def test_ta2o5_functionals_disagree_on_hull_status(transport: HttpxTransport, cassette) -> None:  # type: ignore[no-untyped-def]
    summary = mp.summary_records(_summary(transport, cassette, "Ta2O5"))
    with cassette("mp", "thermo_Ta2O5_probe"):
        thermo = [
            rec
            for call in mp.plan_thermo(["mp-1539317", "mp-10390"])
            for rec in mp.thermo_records(transport.get(call))
        ]
    polys = {p.ids.mp: p for p in mp.assemble(summary, thermo).polymorphs}
    assert polys["mp-1539317"].hull_status_conflict is True
    assert (
        polys["mp-1539317"].is_stable["GGA_GGA+U"] is True
        and polys["mp-1539317"].is_stable["r2SCAN"] is False
    )
    assert polys["mp-10390"].hull_status_conflict is True  # stable in r2SCAN, not in GGA_GGA+U


def test_dielectric_present_for_ground_state_and_missing_elsewhere(
    transport: HttpxTransport, cassette
) -> None:  # type: ignore[no-untyped-def]
    summary = mp.summary_records(_summary(transport, cassette, "HfO2"))
    with cassette("mp", "dielectric_HfO2_probe"):
        diel = [
            rec
            for call in mp.plan_dielectric(["mp-352", "mp-775757"])
            for rec in mp.dielectric_records(transport.get(call))
        ]
    polys = {p.ids.mp: p for p in mp.assemble(summary, [], diel).polymorphs}
    assert polys["mp-352"].dielectric["e_total"].value == pytest.approx(18.7477708)
    assert polys["mp-775757"].dielectric["e_total"].value is None
    assert polys["mp-775757"].dielectric["e_total"].missing_reason == MissingReason.NOT_COMPUTED


def test_full_discovery_pages_everything_without_truncation(
    transport: HttpxTransport, cassette
) -> None:  # type: ignore[no-untyped-def]
    f = mp.DiscoveryFilter(
        elements=("O",),
        nelements_min=2,
        nelements_max=3,
        band_gap_min=3.0,
        energy_above_hull_max=0.05,
    )
    with cassette("mp", "discovery_oxides_full"):
        result = mp.run_discovery(transport.get, f)
    assert result.refused is False
    assert result.total_available == result.returned
    assert result.total_available > 3000
    assert len({r.source_record_id for r in result.records}) == result.returned


def test_discovery_refuses_above_ceiling() -> None:
    def fake_fetch(call: Call) -> RawResponse:
        body = {"data": [], "meta": {"total_doc": 10_001}}
        return RawResponse(
            call=call,
            status=200,
            body=json.dumps(body).encode(),
            content_type="application/json",
            fetched_at=RawResponse.now(),
        )

    result = mp.run_discovery(fake_fetch, mp.DiscoveryFilter())
    assert result.refused is True and result.total_available == 10_001 and result.returned == 0


def _synthetic_call() -> Call:
    return Call(
        source=Source.MP,
        endpoint="materials/summary",
        url=mp.PATHS["summary"],
        params={"synthetic": "true"},
    )


def test_synthetic_deprecated_entry_is_excluded_with_rule() -> None:
    raw = synthetic_raw("mp_deprecated_entry.json", _synthetic_call())
    assembly = mp.assemble(mp.summary_records(raw))
    assert assembly.polymorphs == []
    assert [(e.mp_id, e.rule) for e in assembly.excluded] == [("mp-1", "deprecated")]


def test_synthetic_gnome_entry_is_excluded_by_license() -> None:
    raw = synthetic_raw("mp_gnome_entry.json", _synthetic_call())
    assembly = mp.assemble(mp.summary_records(raw))
    assert assembly.polymorphs == []
    assert assembly.excluded[0].rule == "license" and "BY-NC" in assembly.excluded[0].detail


def test_absent_field_is_missing_not_zero() -> None:
    body = {
        "data": [
            {
                "material_id": "mp-aaaaaaab",
                "formula_pretty": "HfO2",
                "theoretical": False,
                "deprecated": False,
                "symmetry": {},
            }
        ],
        "meta": {},
    }
    raw = RawResponse(
        call=_synthetic_call(),
        status=200,
        body=json.dumps(body).encode(),
        content_type=None,
        fetched_at=RawResponse.now(),
    )
    p = mp.assemble(mp.summary_records(raw)).polymorphs[0]
    assert p.hull_energy[mp.MIXED_HULL].value is None
    assert p.hull_energy[mp.MIXED_HULL].missing_reason == MissingReason.ABSENT
    assert p.band_gap["mp_summary"].missing_reason == MissingReason.ABSENT


def test_no_synthetic_marker_under_recorded_fixtures() -> None:
    for folder in ("wire", "adapters"):
        for path in (ROOT / "fixtures" / folder).rglob("*"):
            if path.is_file() and path.suffix in {".yaml", ".json"}:
                assert '"_synthetic"' not in path.read_text(errors="ignore"), path
