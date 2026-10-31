from datetime import UTC, datetime

import pytest
import yaml

from materials_triage.adapters import optimade
from materials_triage.adapters.base import RawResponse
from tests.adapters.conftest import ROOT


def test_alphabetical_formulas() -> None:
    assert optimade.optimade_formula("TiO2") == "O2Ti"
    assert optimade.optimade_formula("BaTiO3") == "BaO3Ti"
    assert optimade.optimade_formula("HfO2") == "HfO2"
    assert optimade.optimade_formula("Y2O3") == "O3Y2"


def test_only_cod_is_wired() -> None:
    assert optimade.WIRED == ["cod"]
    assert optimade.plan_structures("cod", "ThO2").url.startswith(
        "https://www.crystallography.net/cod/optimade/v1/"
    )


def test_oqmd_phase0_recording_parses_as_provider_agnostic_fixture() -> None:
    """OQMD is cut as a source; its Phase 0 cassette stays as a fixture for the shared parser.
    (A live re-recording on 2026-10-31 met HTTP 502 from OQMD; see wire-findings.)"""
    cassette = yaml.safe_load((ROOT / "fixtures" / "wire" / "oqmd" / "HfO2.yaml").read_text())
    interaction = next(i for i in cassette["interactions"] if "/structures" in i["request"]["uri"])
    call = optimade.plan_structures("oqmd", "HfO2", page_limit=10)
    raw = RawResponse(
        call=call,
        status=int(interaction["response"]["status"]["code"]),
        body=interaction["response"]["body"]["string"].encode(),
        content_type="application/json",
        fetched_at=datetime.now(UTC),
    )
    returned, more, next_url = optimade.page_info(raw)
    assert returned == 24 and more is True and next_url
    recs = optimade.records(raw, "oqmd")
    assert len(recs) == 10 and all(r.composition == "HfO2" for r in recs)
    assert all(isinstance(r.payload["space_group_it_number"], int) for r in recs)
    assert all(r.provenance.raw_sha256 == raw.sha256 for r in recs)


def test_non_200_body_is_an_error_not_a_parse() -> None:
    call = optimade.plan_structures("oqmd", "HfO2")
    raw = RawResponse(
        call=call,
        status=502,
        body=b"<html>Bad Gateway</html>",
        content_type="text/html",
        fetched_at=datetime.now(UTC),
    )
    with pytest.raises(ValueError, match="HTTP 502"):
        optimade.records(raw, "oqmd")


def test_cod_plan_shapes() -> None:
    call = optimade.plan_structures("cod", "TiO2")
    assert call.params["filter"] == 'elements HAS ALL "O","Ti" AND nelements=2'
    assert (
        optimade.plan_structures("oqmd", "TiO2").params["filter"]
        == 'chemical_formula_reduced="O2Ti"'
    )
    assert optimade.plan_info("cod").url.endswith("/info/structures")
    # COD was unreachable throughout Phase 0; a live failure is a TransportFailedError that the
    # runner records as an availability event (tests/adapters/test_runner.py).
