"""Experimental band gap tables (Zhuo et al. 2018 via matminer): the full compendium for the
product and the deduplicated matbench table for validation only. Composition-level values;
zero rows are MP metals and are excluded with the reason recorded."""

from __future__ import annotations

import json
import statistics
from datetime import UTC, datetime
from pathlib import Path

from materials_triage.adapters.base import Call, RawResponse, Source
from materials_triage.adapters.common import provenance, try_reduced_formula, value_from
from materials_triage.records import ExperimentalGap, ExperimentalGapAggregate, SourceRecord

ROLES = {"expt_gap": "product", "matbench_expt_gap": "validation"}


def load_slice(
    slice_path: Path, *, table: str, file_sha256: str, fetched_at: datetime | None = None
) -> RawResponse:
    if table not in ROLES:
        raise ValueError(f"unknown gap table {table}")
    call = Call(source=Source.EXPT_GAP, endpoint=table, url=f"file://{slice_path.name}", params={})
    return RawResponse(
        call=call,
        status=200,
        body=slice_path.read_bytes(),
        content_type="application/json",
        fetched_at=fetched_at or datetime.now(UTC),
        source_version=file_sha256,
    )


def records(raw: RawResponse) -> tuple[list[SourceRecord], list[dict[str, str]]]:
    """Returns (records, exclusions). Zero-gap rows are excluded, never scored."""
    table = raw.call.endpoint
    rows = json.loads(raw.body)
    comp_col = "composition" if rows and "composition" in rows[0] else "formula"
    out: list[SourceRecord] = []
    excluded: list[dict[str, str]] = []
    for i, row in enumerate(rows):
        formula = str(row[comp_col])
        comp = try_reduced_formula(formula)
        gap = row.get("gap expt")
        rid = f"{table}:{i}:{formula}"
        if comp is None:
            excluded.append({"row": rid, "rule": "unparsable_formula"})
            continue
        if gap == 0:
            excluded.append({"row": rid, "rule": "zero_gap_is_mp_metal_not_measurement"})
            continue
        prov = provenance(raw, source_record_id=rid)
        eg = ExperimentalGap(
            composition=comp,
            value_ev=value_from(gap, unit="eV", method=table, prov=prov),
            table=table,
            role=ROLES[table],
            source_formula=formula,
        )
        out.append(
            SourceRecord(
                kind="experimental_gap",
                source_record_id=rid,
                composition=comp,
                payload=eg.model_dump(mode="json"),
                provenance=prov,
            )
        )
    return out, excluded


def aggregates(records_: list[SourceRecord]) -> dict[str, ExperimentalGapAggregate]:
    """Per-composition count, min, median, max over present values. Product role only."""
    by_comp: dict[str, list[ExperimentalGap]] = {}
    for r in records_:
        eg = ExperimentalGap.model_validate(r.payload)
        if eg.role != "product" or eg.value_ev.value is None:
            continue
        by_comp.setdefault(eg.composition, []).append(eg)
    out = {}
    for comp, items in by_comp.items():
        vals = sorted(float(e.value_ev.value) for e in items if e.value_ev.value is not None)
        out[comp] = ExperimentalGapAggregate(
            composition=comp,
            n=len(vals),
            min=vals[0],
            median=float(statistics.median(vals)),
            max=vals[-1],
            values=items,
        )
    return out
