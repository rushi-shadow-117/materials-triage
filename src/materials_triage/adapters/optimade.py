"""OPTIMADE structures, provider-agnostic. COD is the only wired provider; OQMD stays in the
table as a documented extension and its recordings serve as parser fixtures. Formulas use the
OPTIMADE alphabetical reduced form (TiO2 is O2Ti)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pymatgen.core.composition import Composition

from materials_triage.adapters.base import Call, RawResponse, Source
from materials_triage.adapters.common import int_or_none, provenance, try_reduced_formula
from materials_triage.records import SourceRecord


@dataclass(frozen=True)
class Provider:
    source: Source
    base: str
    wired: bool
    stability_field: str | None = None
    band_gap_field: str | None = None
    icsd_field: str | None = None


PROVIDERS: dict[str, Provider] = {
    "cod": Provider(Source.COD, "https://www.crystallography.net/cod/optimade/v1", wired=True),
    "oqmd": Provider(
        Source.OQMD,
        "https://oqmd.org/optimade/v1",
        wired=False,
        stability_field="_oqmd_stability",
        band_gap_field="_oqmd_band_gap",
        icsd_field="_oqmd_icsd_id",
    ),
}
WIRED = [k for k, p in PROVIDERS.items() if p.wired]
PAGE_CAP = 5


def optimade_formula(formula: str) -> str:
    comp = Composition(formula).reduced_composition
    parts = []
    for el in sorted(comp.elements, key=lambda e: e.symbol):
        n = int(round(comp[el]))
        parts.append(el.symbol if n == 1 else f"{el.symbol}{n}")
    return "".join(parts)


def plan_structures(provider: str, formula: str, *, page_limit: int = 10) -> Call:
    p = PROVIDERS[provider]
    return Call(
        source=p.source,
        endpoint="structures",
        url=f"{p.base}/structures",
        params={
            "filter": f'chemical_formula_reduced="{optimade_formula(formula)}"',
            "page_limit": str(page_limit),
        },
    )


def plan_next(provider: str, next_url: str) -> Call:
    """Follow a links.next URL as given; params are already inside it."""
    return Call(
        source=PROVIDERS[provider].source, endpoint="structures_next", url=next_url, params={}
    )


def plan_info(provider: str) -> Call:
    p = PROVIDERS[provider]
    return Call(
        source=p.source, endpoint="info_structures", url=f"{p.base}/info/structures", params={}
    )


def _body(raw: RawResponse) -> dict[str, Any]:
    if raw.status != 200:
        raise ValueError(f"OPTIMADE {raw.call.endpoint} returned HTTP {raw.status}")
    body = json.loads(raw.body)
    if not isinstance(body, dict) or "data" not in body:
        raise ValueError("unexpected OPTIMADE body")
    return body


def page_info(raw: RawResponse) -> tuple[int | None, bool, str | None]:
    body = _body(raw)
    meta = body.get("meta", {})
    return (
        int_or_none(meta.get("data_returned")),
        bool(meta.get("more_data_available")),
        (body.get("links") or {}).get("next"),
    )


def records(raw: RawResponse, provider: str) -> list[SourceRecord]:
    p = PROVIDERS[provider]
    out = []
    for entry in _body(raw)["data"]:
        attrs = entry.get("attributes", {})
        sid = str(entry.get("id"))
        payload = {
            "id": sid,
            "chemical_formula_reduced": attrs.get("chemical_formula_reduced"),
            "space_group_it_number": int_or_none(attrs.get("space_group_it_number")),
            "nsites": int_or_none(attrs.get("nsites")),
            "last_modified": attrs.get("last_modified"),
            "stability": attrs.get(p.stability_field) if p.stability_field else None,
            "band_gap": attrs.get(p.band_gap_field) if p.band_gap_field else None,
            "icsd_id": attrs.get(p.icsd_field) if p.icsd_field else None,
        }
        out.append(
            SourceRecord(
                kind="optimade_structure",
                source_record_id=sid,
                composition=try_reduced_formula(str(attrs.get("chemical_formula_reduced", ""))),
                payload=payload,
                provenance=provenance(raw, source_record_id=sid, url=f"{p.base}/structures/{sid}"),
            )
        )
    return out
