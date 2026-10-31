import json
from datetime import UTC, datetime

from materials_triage.adapters import expt_gap
from materials_triage.adapters.base import Call, RawResponse, Source
from tests.adapters.conftest import SNAPSHOTS


def _load(manifest, table: str):  # type: ignore[no-untyped-def]
    return expt_gap.load_slice(
        SNAPSHOTS / f"{table}.slice.json", table=table, file_sha256=manifest[table]["sha256"]
    )


def test_compendium_aggregates(manifest) -> None:  # type: ignore[no-untyped-def]
    recs, excluded = expt_gap.records(_load(manifest, "expt_gap"))
    assert excluded == []
    agg = expt_gap.aggregates(recs)
    tho2 = agg["ThO2"]
    assert (tho2.n, tho2.min, tho2.median, tho2.max) == (2, 3.3, 3.4, 3.5)
    assert agg["BaTiO3"].n == 5
    assert "Al2O3" not in agg and "SiO2" not in agg


def test_matbench_rows_are_validation_only(manifest) -> None:  # type: ignore[no-untyped-def]
    recs, _ = expt_gap.records(_load(manifest, "matbench_expt_gap"))
    assert recs and all(r.payload["role"] == "validation" for r in recs)
    assert expt_gap.aggregates(recs) == {}


def test_zero_rows_are_excluded_with_reason() -> None:
    body = json.dumps(
        [
            {"formula": "Cu", "gap expt": 0},
            {"formula": "HfO2", "gap expt": 5.55},
            {"formula": "??", "gap expt": 1.0},
        ]
    ).encode()
    raw = RawResponse(
        call=Call(source=Source.EXPT_GAP, endpoint="expt_gap", url="file://inline", params={}),
        status=200,
        body=body,
        content_type=None,
        fetched_at=datetime.now(UTC),
        source_version="inline",
    )
    recs, excluded = expt_gap.records(raw)
    assert [r.composition for r in recs] == ["HfO2"]
    assert {e["rule"] for e in excluded} == {
        "zero_gap_is_mp_metal_not_measurement",
        "unparsable_formula",
    }
