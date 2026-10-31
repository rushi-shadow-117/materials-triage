"""OPTIMADE structures, provider-agnostic. COD is the only wired provider; OQMD stays in the
table as a documented extension and its recordings serve as parser fixtures.

OPTIMADE fixes the query grammar, not which fields a provider lets you filter on. COD answers
HTTP 501 to filters on chemical_formula_reduced (recorded 2026-10-31), so it is queried by
elements plus element count and the formula is matched client-side on the returned
chemical_formula_reduced attribute. Formulas use the OPTIMADE alphabetical reduced form
(TiO2 is O2Ti).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pymatgen.core.composition import Composition
from pymatgen.symmetry.groups import SpaceGroup

from materials_triage.adapters.base import Call, RawResponse, Source
from materials_triage.adapters.common import int_or_none, provenance, try_reduced_formula
from materials_triage.records import SourceRecord


@dataclass(frozen=True)
class Provider:
    source: Source
    base: str
    wired: bool
    filter_style: str = "formula"  # formula | elements
    spacegroup_field: str = "space_group_it_number"
    stability_field: str | None = None
    band_gap_field: str | None = None
    icsd_field: str | None = None


PROVIDERS: dict[str, Provider] = {
    "cod": Provider(
        Source.COD,
        "https://www.crystallography.net/cod/optimade/v1",
        wired=True,
        filter_style="elements",
        spacegroup_field="_cod_sgnumber",
    ),
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


def optimade_filter(provider: str, formula: str) -> str:
    p = PROVIDERS[provider]
    if p.filter_style == "formula":
        return f'chemical_formula_reduced="{optimade_formula(formula)}"'
    comp = Composition(formula)
    elements = ",".join(f'"{el.symbol}"' for el in sorted(comp.elements, key=lambda e: e.symbol))
    return f"elements HAS ALL {elements} AND nelements={len(comp.elements)}"


def plan_structures(provider: str, formula: str, *, page_limit: int = 10) -> Call:
    p = PROVIDERS[provider]
    return Call(
        source=p.source,
        endpoint="structures",
        url=f"{p.base}/structures",
        params={"filter": optimade_filter(provider, formula), "page_limit": str(page_limit)},
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


def spacegroup_number(attrs: dict[str, Any], p: Provider) -> tuple[int | None, str | None]:
    """Number from the provider's numeric field, else derived from a Hermann-Mauguin symbol
    (COD often fills `_cod_sg` but not `_cod_sgnumber`). Returns (number, source_field)."""
    n = int_or_none(attrs.get(p.spacegroup_field))
    if n is not None:
        return n, p.spacegroup_field
    symbol = attrs.get("_cod_sg") or attrs.get("space_group_symbol_hermann_mauguin")
    if isinstance(symbol, str) and symbol.strip():
        try:
            return int(SpaceGroup(symbol.replace(" ", "")).int_number), "derived_from_symbol"
        except Exception:  # noqa: BLE001 - an unrecognized symbol is missing data, not a crash
            return None, None
    return None, None


def records(raw: RawResponse, provider: str, *, formula: str | None = None) -> list[SourceRecord]:
    """Structures from one page. With `formula`, keep only entries whose reduced formula
    matches it (needed when the provider was queried by elements)."""
    p = PROVIDERS[provider]
    want = optimade_formula(formula) if formula else None
    out = []
    for entry in _body(raw)["data"]:
        attrs = entry.get("attributes", {})
        if want is not None and attrs.get("chemical_formula_reduced") != want:
            continue
        sid = str(entry.get("id"))
        payload = {
            "id": sid,
            "chemical_formula_reduced": attrs.get("chemical_formula_reduced"),
            "space_group_it_number": spacegroup_number(attrs, p)[0],
            "space_group_source": spacegroup_number(attrs, p)[1],
            "space_group_symbol": attrs.get("_cod_sg")
            or attrs.get("space_group_symbol_hermann_mauguin"),
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
