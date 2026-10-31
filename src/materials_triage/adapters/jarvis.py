"""JARVIS-DFT dft_3d snapshot adapter.

The snapshot is a file, not an HTTP response; the slice file is the raw body and the full
file's SHA-256 (from fixtures/snapshots/MANIFEST.json) is the source version. Missing values
are the string "na" and become None with a reason; zero stays zero. `icsd` is a
comma-separated string of ids. Property keys are stored under JARVIS's own field names so no
interpretation is added here.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from materials_triage.adapters.base import Call, RawResponse, Source
from materials_triage.adapters.common import (
    int_or_none,
    provenance,
    try_reduced_formula,
    value_from,
)
from materials_triage.records import Ids, ObservationEvidence, Polymorph, SourceRecord

GAP_FIELDS = {
    "optb88vdw_bandgap": "jarvis_optb88vdw",
    "mbj_bandgap": "jarvis_tbmbj",
    "hse_gap": "jarvis_hse",
}
HULL_FIELD = ("ehull", "jarvis_optb88vdw")
DIELECTRIC_FIELDS = (
    "epsx",
    "epsy",
    "epsz",
    "mepsx",
    "mepsy",
    "mepsz",
    "dfpt_piezo_max_dielectric",
    "dfpt_piezo_max_dielectric_electronic",
    "dfpt_piezo_max_dielectric_ionic",
)


def parse_icsd(value: Any) -> list[int]:
    """'60419,160901' -> [60419, 160901]; '' or non-string -> []. Non-numeric tokens dropped."""
    if not isinstance(value, str) or not value.strip():
        return []
    out = {int(tok) for tok in (t.strip() for t in value.split(",")) if tok.isdigit()}
    return sorted(out)


def load_slice(
    slice_path: Path, *, full_file_sha256: str, fetched_at: datetime | None = None
) -> RawResponse:
    """Wrap the slice file as a RawResponse so it flows through the same provenance path."""
    body = slice_path.read_bytes()
    call = Call(
        source=Source.JARVIS, endpoint="dft_3d_slice", url=f"file://{slice_path.name}", params={}
    )
    return RawResponse(
        call=call,
        status=200,
        body=body,
        content_type="application/json",
        fetched_at=fetched_at or datetime.now(UTC),
        source_version=full_file_sha256,
    )


def records(raw: RawResponse) -> list[SourceRecord]:
    data = json.loads(raw.body)
    out = []
    for d in data:
        jid = str(d["jid"])
        comp = try_reduced_formula(str(d.get("formula", "")))
        out.append(
            SourceRecord(
                kind="jarvis_entry",
                source_record_id=jid,
                composition=comp,
                payload=d,
                provenance=provenance(
                    raw,
                    source_record_id=jid,
                    url=f"https://www.ctcms.nist.gov/~knc6/static/JARVIS-DFT/{jid}.xml",
                ),
            )
        )
    return out


def polymorphs(records_: list[SourceRecord]) -> list[Polymorph]:
    out = []
    for r in records_:
        d = r.payload
        prov = r.provenance
        comp = r.composition
        if comp is None:
            continue
        icsd = parse_icsd(d.get("icsd"))
        hull = {
            HULL_FIELD[1]: value_from(
                d.get(HULL_FIELD[0]), unit="eV/atom", method=HULL_FIELD[1], prov=prov
            )
        }
        gaps = {
            method: value_from(d.get(field), unit="eV", method=method, prov=prov)
            for field, method in GAP_FIELDS.items()
        }
        diel = {
            f"jarvis_{f}": value_from(d.get(f), unit="1", method=f"jarvis_{f}", prov=prov)
            for f in DIELECTRIC_FIELDS
        }
        out.append(
            Polymorph(
                composition=comp,
                spacegroup_number=int_or_none(d.get("spg_number")),
                spacegroup_symbol=d.get("spg_symbol")
                if isinstance(d.get("spg_symbol"), str)
                else None,
                ids=Ids(jarvis_jid=r.source_record_id, icsd=icsd),
                observed=True if icsd else None,
                observation_evidence=[ObservationEvidence.JARVIS_ICSD_IDS] if icsd else [],
                hull_energy=hull,
                band_gap=gaps,
                dielectric=diel,
                provenance=[prov],
            )
        )
    return out
