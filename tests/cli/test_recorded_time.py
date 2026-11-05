"""A replay shows when a response was recorded, never the replay time (review F15)."""

from __future__ import annotations

from datetime import UTC, datetime

from materials_triage.adapters.common import provenance
from materials_triage.cli import wiring
from materials_triage.render.views import ProvenanceView


def _raw(name: str, source_dir: str):  # type: ignore[no-untyped-def]
    path = wiring.ADAPTER_CASSETTES / source_dir / name
    return [raw for p, raw in wiring.iter_cassette_raws(path.parent) if p == path]


def test_a_vcr_cassette_uses_the_response_date_header() -> None:
    # fixtures/adapters/openalex/NaTaO3.yaml has no recorded_at; the server's Date header is
    # "Mon, 02 Nov 2026 15:27:44 GMT"
    raws = _raw("NaTaO3.yaml", "openalex")
    assert raws and all(r.recorded for r in raws)
    assert raws[0].fetched_at == datetime(2026, 11, 2, 15, 27, 44, tzinfo=UTC)


def test_a_cassette_recorded_at_is_the_time_shown() -> None:
    raws = _raw("run_A1.yaml", "mp")
    assert raws[0].recorded and raws[0].fetched_at == datetime(2026, 11, 4, 0, 0, 13, tzinfo=UTC)


def test_two_replays_show_the_same_recorded_time_labelled_recorded() -> None:
    first = _raw("NaTaO3.yaml", "openalex")[0]
    second = _raw("NaTaO3.yaml", "openalex")[0]
    assert first.fetched_at == second.fetched_at
    prov = provenance(first, source_record_id="W1")
    assert prov.recorded is True
    view = ProvenanceView.build(prov)
    assert view.fetch_label == "recorded" and view.fetched_at == "2026-11-02T15:27:44+00:00"


def test_with_no_time_in_the_cassette_the_manifest_time_is_used() -> None:
    when = wiring.recorded_time({"response": {"headers": {}}})
    assert when == datetime(2026, 11, 4, 1, 27, 25, tzinfo=UTC)
