"""PubChem: CID lookup by common name (formula fallback), GHS classification through PUG-View,
and the synonym list. GHS is an aggregate of notifications that disagree; counts are kept and
never collapsed to a verdict. ECHA-derived content is flagged for attribution."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote

from materials_triage.adapters.base import Call, RawResponse, Source
from materials_triage.adapters.common import provenance
from materials_triage.records import HazardRecord

BASE = "https://pubchem.ncbi.nlm.nih.gov/rest"
H_CODE = re.compile(r"^H\d{3}[a-z]*")
COUNT_RE = re.compile(r"(\d+)\s+of\s+(\d+)\s+(?:reports|companies)")
PROVIDED_PER_RE = re.compile(r"provided per\s+(\d+)\s+reports? by compan", re.I)
NOT_CLASSIFIED_RE = re.compile(
    r"not meeting GHS hazard criteria (?:by|per)\s+(\d+)\s+of\s+(\d+)", re.I
)
ECHA_MARKERS = ("ECHA", "European Chemicals Agency")
# Same characters httpx leaves unencoded in a path, so planned URLs equal sent URLs.
PATH_SAFE = "/:@!$&'()*+,;=-._~"


def _call(endpoint: str, url: str, **params: str) -> Call:
    return Call(source=Source.PUBCHEM, endpoint=endpoint, url=url, params=params)


def plan_cids_by_name(name: str) -> Call:
    return _call(
        "cids_by_name", f"{BASE}/pug/compound/name/{quote(name, safe=PATH_SAFE)}/cids/JSON"
    )


def plan_cids_by_formula(formula: str) -> Call:
    return _call(
        "cids_by_formula",
        f"{BASE}/pug/compound/fastformula/{quote(formula, safe=PATH_SAFE)}/cids/JSON",
    )


def plan_ghs(cid: int) -> Call:
    return _call("ghs", f"{BASE}/pug_view/data/compound/{cid}/JSON", heading="GHS Classification")


def plan_synonyms(cid: int) -> Call:
    return _call("synonyms", f"{BASE}/pug/compound/cid/{cid}/synonyms/JSON")


def cids(raw: RawResponse) -> list[int]:
    if raw.status != 200:
        return []
    body = json.loads(raw.body)
    return sorted(int(c) for c in body.get("IdentifierList", {}).get("CID", []))


def choose_cid(by_name: list[int], by_formula: list[int]) -> tuple[int | None, str]:
    """Deterministic: the CID from the name lookup, else the smallest from the formula lookup."""
    if by_name:
        return min(by_name), "min CID from name lookup"
    if by_formula:
        return min(by_formula), "min CID from formula lookup"
    return None, "no CID found"


def _strings(node: Any, out: list[str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "String" and isinstance(v, str):
                out.append(v)
            else:
                _strings(v, out)
    elif isinstance(node, list):
        for x in node:
            _strings(x, out)


def parse_ghs(raw: RawResponse) -> dict[str, Any]:
    """Codes, notifier counts, raw strings, and reference source names. No verdict."""
    if raw.status != 200:
        return {
            "present": False,
            "h_codes": [],
            "raw_strings": [],
            "references": [],
            "notifications_total": None,
            "notifications_not_classified": None,
        }
    body = json.loads(raw.body)
    record = body.get("Record", {})
    strings: list[str] = []
    _strings(record.get("Section", []), strings)
    codes = sorted({m.group(0) for s in strings for m in [H_CODE.match(s.strip())] if m})
    total = not_classified = None
    for s in strings:
        m = NOT_CLASSIFIED_RE.search(s)
        if m:
            not_classified, total = int(m.group(1)), int(m.group(2))
            break
    if total is None:
        for s in strings:
            m = COUNT_RE.search(s) or PROVIDED_PER_RE.search(s)
            if m:
                total = int(m.group(m.lastindex or 1))
                break
    refs = [
        str(r.get("SourceName", "")) for r in record.get("Reference", []) if isinstance(r, dict)
    ]
    return {
        "present": bool(strings),
        "h_codes": codes,
        "raw_strings": strings,
        "references": refs,
        "notifications_total": total,
        "notifications_not_classified": not_classified,
    }


def synonyms(raw: RawResponse) -> list[str]:
    if raw.status != 200:
        return []
    body = json.loads(raw.body)
    infos = body.get("InformationList", {}).get("Information", [])
    return [str(n) for info in infos for n in info.get("Synonym", [])]


def hazard(
    composition: str,
    *,
    by_name: RawResponse,
    by_formula: RawResponse,
    ghs: RawResponse | None,
    syn: RawResponse | None,
) -> HazardRecord:
    name_cids, formula_cids = cids(by_name), cids(by_formula)
    cid, rule = choose_cid(name_cids, formula_cids)
    parsed = (
        parse_ghs(ghs)
        if ghs is not None
        else parse_ghs(
            RawResponse(
                call=by_name.call,
                status=404,
                body=b"",
                content_type=None,
                fetched_at=by_name.fetched_at,
            )
        )
    )
    anchor = ghs or by_name
    return HazardRecord(
        composition=composition,
        cid=cid,
        cids_by_name=name_cids,
        cids_by_formula=formula_cids,
        chosen_rule=rule,
        notifications_total=parsed["notifications_total"],
        notifications_not_classified=parsed["notifications_not_classified"],
        h_codes=parsed["h_codes"],
        raw_strings=parsed["raw_strings"],
        references=parsed["references"],
        echa_attribution_required=any(
            any(mark in ref for mark in ECHA_MARKERS) for ref in parsed["references"]
        ),
        synonyms=synonyms(syn) if syn is not None else [],
        provenance=provenance(
            anchor,
            source_record_id=f"CID:{cid}" if cid else "CID:none",
            url=f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}" if cid else None,
        ),
    )
