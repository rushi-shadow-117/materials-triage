"""Materials Project over REST.

Endpoints, as recorded in Phase 0 and allowlisted: /materials/summary/, /materials/thermo/,
/materials/dielectric/, /heartbeat. Raw ids are AlphaIDs; the client form is derived with
`mpid.to_legacy`. The summary hull energy is the mixed GGA_GGA+U_R2SCAN value; per-functional
values come from thermo documents for an explicit id list. GNoME-derived documents carry
builder_meta.license "BY-NC" and are excluded with the rule recorded.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from materials_triage.adapters.base import Auth, Call, RawResponse, Source
from materials_triage.adapters.common import (
    int_or_none,
    provenance,
    reduced_formula,
    value_from,
)
from materials_triage.adapters.mpid import to_legacy
from materials_triage.records import (
    Ids,
    MissingReason,
    ObservationEvidence,
    Polymorph,
    Provenance,
    SourceRecord,
    Value,
)

BASE = "https://api.materialsproject.org"
PATHS = {
    "summary": f"{BASE}/materials/summary/",
    "thermo": f"{BASE}/materials/thermo/",
    "dielectric": f"{BASE}/materials/dielectric/",
    "heartbeat": f"{BASE}/heartbeat",
}
ALLOWED_URLS = frozenset(PATHS.values())

SUMMARY_FIELDS = (
    "material_id,formula_pretty,composition_reduced,nelements,energy_above_hull,is_stable,"
    "band_gap,theoretical,deprecated,symmetry,database_IDs,last_updated,builder_meta"
)
THERMO_FIELDS = "material_id,thermo_type,energy_above_hull,is_stable"
# Discovery pages carry the fields the first-pass filter needs plus the license; full
# summaries are fetched later for the compositions that survive.
DISCOVERY_FIELDS = (
    "material_id,formula_pretty,nelements,energy_above_hull,is_stable,band_gap,theoretical,"
    "deprecated,builder_meta"
)
DIELECTRIC_FIELDS = (
    "material_id,formula_pretty,e_total,e_ionic,e_electronic,n,deprecated,builder_meta"
)
PAGE = 1000
ID_CHUNK = 200
DISCOVERY_CEILING = 10_000
MIXED_HULL = "GGA_GGA+U_R2SCAN"  # what the summary endpoint reports (wire-findings.md)
NON_COMMERCIAL_LICENSE = "BY-NC"


# ----------------------------------------------------------------------------- planning


def _call(endpoint: str, params: dict[str, str]) -> Call:
    return Call(
        source=Source.MP,
        endpoint=f"materials/{endpoint}" if endpoint != "heartbeat" else "heartbeat",
        url=PATHS[endpoint],
        params=params,
        auth=Auth.MP_HEADER,
    )


def plan_heartbeat() -> Call:
    return _call("heartbeat", {})


def plan_summary_by_formula(formula: str) -> Call:
    return _call("summary", {"formula": formula, "_fields": SUMMARY_FIELDS, "_limit": str(PAGE)})


def _chunks(ids: list[str]) -> list[list[str]]:
    ordered = sorted(set(ids))
    return [ordered[i : i + ID_CHUNK] for i in range(0, len(ordered), ID_CHUNK)]


def plan_summary_by_ids(ids: list[str]) -> list[Call]:
    return [
        _call(
            "summary", {"material_ids": ",".join(c), "_fields": SUMMARY_FIELDS, "_limit": str(PAGE)}
        )
        for c in _chunks(ids)
    ]


def plan_thermo(ids: list[str]) -> list[Call]:
    """Per-functional hull data for an explicit id list only (owner decision 5)."""
    return [
        _call(
            "thermo", {"material_ids": ",".join(c), "_fields": THERMO_FIELDS, "_limit": str(PAGE)}
        )
        for c in _chunks(ids)
    ]


def plan_dielectric(ids: list[str]) -> list[Call]:
    return [
        _call(
            "dielectric",
            {"material_ids": ",".join(c), "_fields": DIELECTRIC_FIELDS, "_limit": str(PAGE)},
        )
        for c in _chunks(ids)
    ]


@dataclass(frozen=True)
class DiscoveryFilter:
    elements: tuple[str, ...] = ("O",)
    nelements_min: int = 2
    nelements_max: int = 3
    band_gap_min: float | None = None
    energy_above_hull_max: float | None = None

    def params(self) -> dict[str, str]:
        p = {
            "elements": ",".join(self.elements),
            "nelements_min": str(self.nelements_min),
            "nelements_max": str(self.nelements_max),
        }
        if self.band_gap_min is not None:
            p["band_gap_min"] = str(self.band_gap_min)
        if self.energy_above_hull_max is not None:
            p["energy_above_hull_min"] = "0.0"
            p["energy_above_hull_max"] = str(self.energy_above_hull_max)
        return p


def plan_discovery_page(f: DiscoveryFilter, skip: int) -> Call:
    params = {**f.params(), "_fields": DISCOVERY_FIELDS, "_limit": str(PAGE)}
    if skip:
        params["_skip"] = str(skip)
    return _call("summary", params)


# ----------------------------------------------------------------------------- parsing


def _body(raw: RawResponse) -> dict[str, Any]:
    body = json.loads(raw.body)
    if not isinstance(body, dict) or "data" not in body:
        raise ValueError(f"unexpected Materials Project body for {raw.call.endpoint}")
    return body


def parse_heartbeat(raw: RawResponse) -> str:
    body = json.loads(raw.body)
    version = body.get("db_version")
    if not isinstance(version, str):
        raise ValueError("heartbeat has no db_version")
    return version


def total_doc(raw: RawResponse) -> int | None:
    return int_or_none(_body(raw).get("meta", {}).get("total_doc"))


def docs(raw: RawResponse) -> list[dict[str, Any]]:
    return list(_body(raw)["data"])


def _icsd_ids(doc: dict[str, Any]) -> list[int]:
    db_ids = doc.get("database_IDs") or {}
    out: list[int] = []
    for tag in db_ids.get("icsd", []) or []:
        n = int_or_none(str(tag).replace("icsd-", ""))
        if n is not None:
            out.append(n)
    return sorted(set(out))


def _license(doc: dict[str, Any]) -> str | None:
    meta = doc.get("builder_meta") or {}
    lic = meta.get("license")
    return str(lic) if lic else None


def summary_records(raw: RawResponse) -> list[SourceRecord]:
    """One record per summary document, in client id form, with raw id kept."""
    out = []
    for doc in docs(raw):
        raw_id = str(doc["material_id"])
        mp_id = to_legacy(raw_id)
        out.append(
            SourceRecord(
                kind="mp_summary",
                source_record_id=mp_id,
                composition=reduced_formula(doc["formula_pretty"])
                if doc.get("formula_pretty")
                else None,
                payload={**doc, "material_id": mp_id, "material_id_raw": raw_id},
                provenance=provenance(
                    raw,
                    source_record_id=mp_id,
                    url=f"https://next-gen.materialsproject.org/materials/{mp_id}",
                    license=_license(doc),
                ),
                license=_license(doc),
            )
        )
    return out


def thermo_records(raw: RawResponse) -> list[SourceRecord]:
    out = []
    for doc in docs(raw):
        mp_id = to_legacy(str(doc["material_id"]))
        ttype = str(doc["thermo_type"])
        out.append(
            SourceRecord(
                kind="mp_thermo",
                source_record_id=f"{mp_id}:{ttype}",
                composition=None,
                payload={**doc, "material_id": mp_id},
                provenance=provenance(raw, source_record_id=mp_id),
            )
        )
    return out


def dielectric_records(raw: RawResponse) -> list[SourceRecord]:
    out = []
    for doc in docs(raw):
        mp_id = to_legacy(str(doc["material_id"]))
        out.append(
            SourceRecord(
                kind="mp_dielectric",
                source_record_id=mp_id,
                composition=None,
                payload={**doc, "material_id": mp_id},
                provenance=provenance(raw, source_record_id=mp_id, license=_license(doc)),
                license=_license(doc),
            )
        )
    return out


# ----------------------------------------------------------------------------- assembly


@dataclass
class Exclusion:
    mp_id: str
    rule: str
    detail: str


@dataclass
class Assembly:
    polymorphs: list[Polymorph]
    excluded: list[Exclusion] = field(default_factory=list)


def _val(x: Any, unit: str, method: str, prov: Provenance) -> Value[float]:
    return value_from(x, unit=unit, method=method, prov=prov)


def assemble(
    summary: list[SourceRecord],
    thermo: list[SourceRecord] | None = None,
    dielectric: list[SourceRecord] | None = None,
) -> Assembly:
    """Join summary, thermo, and dielectric records into Polymorphs. Pure."""
    thermo = thermo or []
    dielectric = dielectric or []
    thermo_by_id: dict[str, list[SourceRecord]] = {}
    for t in thermo:
        thermo_by_id.setdefault(t.payload["material_id"], []).append(t)
    diel_by_id = {d.payload["material_id"]: d for d in dielectric}
    polys: list[Polymorph] = []
    excluded: list[Exclusion] = []
    for s in summary:
        doc = s.payload
        mp_id = doc["material_id"]
        lic = s.license
        if lic == NON_COMMERCIAL_LICENSE:
            excluded.append(Exclusion(mp_id, "license", f"builder_meta.license={lic}"))
            continue
        if doc.get("deprecated") is True:
            excluded.append(Exclusion(mp_id, "deprecated", "summary.deprecated=true"))
            continue
        prov = s.provenance
        hull: dict[str, Value[float]] = {
            MIXED_HULL: _val(doc.get("energy_above_hull"), "eV/atom", MIXED_HULL, prov)
        }
        stable: dict[str, bool] = {}
        if isinstance(doc.get("is_stable"), bool):
            stable[MIXED_HULL] = doc["is_stable"]
        for t in thermo_by_id.get(mp_id, []):
            ttype = str(t.payload["thermo_type"])
            hull[ttype] = _val(t.payload.get("energy_above_hull"), "eV/atom", ttype, t.provenance)
            if isinstance(t.payload.get("is_stable"), bool):
                stable[ttype] = t.payload["is_stable"]
        conflict = len(set(stable.values())) > 1
        gap = {"mp_summary": _val(doc.get("band_gap"), "eV", "mp_summary", prov)}
        diel: dict[str, Value[float]] = {}
        d = diel_by_id.get(mp_id)
        if d is not None:
            for key in ("e_total", "e_ionic", "e_electronic"):
                diel[key] = _val(d.payload.get(key), "1", "mp_dfpt", d.provenance)
        else:
            diel["e_total"] = Value[float](
                value=None,
                unit="1",
                method="mp_dfpt",
                missing_reason=MissingReason.NOT_COMPUTED,
                provenance=prov,
            )
        icsd = _icsd_ids(doc)
        evidence: list[ObservationEvidence] = []
        if doc.get("theoretical") is False:
            evidence.append(ObservationEvidence.MP_NOT_THEORETICAL)
        if icsd:
            evidence.append(ObservationEvidence.MP_ICSD_IDS)
        sym = doc.get("symmetry") or {}
        polys.append(
            Polymorph(
                composition=s.composition or reduced_formula(doc["formula_pretty"]),
                spacegroup_number=int_or_none(sym.get("number")),
                spacegroup_symbol=sym.get("symbol"),
                ids=Ids(mp=mp_id, mp_raw=doc.get("material_id_raw"), icsd=icsd),
                observed=(
                    True if evidence else (False if doc.get("theoretical") is True else None)
                ),
                observation_evidence=evidence,
                hull_energy=hull,
                is_stable=stable,
                hull_status_conflict=conflict,
                band_gap=gap,
                dielectric=diel,
                theoretical=doc.get("theoretical"),
                deprecated=bool(doc.get("deprecated", False)),
                license=lic,
                provenance=[prov],
            )
        )
    return Assembly(polymorphs=polys, excluded=excluded)


# ----------------------------------------------------------------------------- discovery


@dataclass
class DiscoveryResult:
    total_available: int
    returned: int
    refused: bool
    ceiling: int
    records: list[SourceRecord]


class DiscoveryTooLargeError(RuntimeError):
    def __init__(self, total: int, ceiling: int) -> None:
        super().__init__(
            f"discovery matched {total} documents, above the ceiling of {ceiling}; narrow the query"
        )
        self.total = total
        self.ceiling = ceiling


def run_discovery(
    fetch: Callable[[Call], RawResponse], f: DiscoveryFilter, *, ceiling: int = DISCOVERY_CEILING
) -> DiscoveryResult:
    """Page every match (no truncation) or refuse above the ceiling. `fetch` is injected so
    the runner can serve pages from the store."""
    first = fetch(plan_discovery_page(f, 0))
    total = total_doc(first)
    if total is None:
        raise ValueError("discovery response has no meta.total_doc")
    if total > ceiling:
        return DiscoveryResult(
            total_available=total, returned=0, refused=True, ceiling=ceiling, records=[]
        )
    records = summary_records(first)
    skip = PAGE
    while skip < total:
        records.extend(summary_records(fetch(plan_discovery_page(f, skip))))
        skip += PAGE
    return DiscoveryResult(
        total_available=total,
        returned=len(records),
        refused=False,
        ceiling=ceiling,
        records=records,
    )
