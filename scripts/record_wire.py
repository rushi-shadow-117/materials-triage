"""Record live responses from every upstream source into vcrpy cassettes.

Usage:
    uv run python scripts/record_wire.py [--mode once|none|all] [--sources pubchem,cod,...]

Cassettes land in fixtures/wire/<source>/<formula>.yaml. Each source directory gets a
meta.json with the fetch timestamp, endpoints, and per-material status. Keys are filtered
out of cassettes; `--mode none` replays and fails on any request that was not recorded.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import vcr
from dotenv import load_dotenv
from pymatgen.core import Composition

ROOT = Path(__file__).resolve().parents[1]
WIRE = ROOT / "fixtures" / "wire"

# The Phase 0 material set. Later phases import this list; keep it one constant.
MATERIALS: list[str] = [
    "HfO2",
    "Al2O3",
    "ZrO2",
    "SiO2",
    "TiO2",
    "ThO2",
    "La2O3",
    "BaTiO3",
    "BeO",
    "Y2O3",
    "Ta2O5",
]

# Common names for PubChem name lookup. Public, conventional names only.
COMMON_NAMES: dict[str, str] = {
    "HfO2": "hafnium dioxide",
    "Al2O3": "aluminum oxide",
    "ZrO2": "zirconium dioxide",
    "SiO2": "silicon dioxide",
    "TiO2": "titanium dioxide",
    "ThO2": "thorium dioxide",
    "La2O3": "lanthanum oxide",
    "BaTiO3": "barium titanate",
    "BeO": "beryllium oxide",
    "Y2O3": "yttrium oxide",
    "Ta2O5": "tantalum pentoxide",
}

# One synonym per formula for the OpenAlex recording. This is a recording probe, not the
# synonym table (which is FDE-owned config from Phase 2).
OPENALEX_SYNONYM: dict[str, str] = {
    "HfO2": "hafnia",
    "Al2O3": "alumina",
    "ZrO2": "zirconia",
    "SiO2": "silica",
    "TiO2": "titania",
    "ThO2": "thoria",
    "La2O3": "lanthana",
    "BaTiO3": "barium titanate",
    "BeO": "beryllia",
    "Y2O3": "yttria",
    "Ta2O5": "tantalum pentoxide",
}

HTTP_TIMEOUT = httpx.Timeout(connect=15.0, read=120.0, write=30.0, pool=15.0)
PUBCHEM_PAUSE_S = 0.25  # PubChem asks for at most 5 requests per second.


def optimade_formula(formula: str) -> str:
    """OPTIMADE chemical_formula_reduced: reduced, elements alphabetical, no '1' counts."""
    comp = Composition(formula).reduced_composition
    parts = []
    for el in sorted(comp.elements, key=lambda e: e.symbol):
        n = int(round(comp[el]))
        parts.append(el.symbol if n == 1 else f"{el.symbol}{n}")
    return "".join(parts)


def make_vcr(mode: str) -> vcr.VCR:
    return vcr.VCR(
        record_mode=mode,
        filter_headers=["X-API-KEY", "x-api-key", "Authorization", "authorization"],
        filter_query_parameters=["api_key", "mailto"],
        match_on=["method", "scheme", "host", "port", "path", "query"],
        decode_compressed_response=True,
    )


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def get_json(client: httpx.Client, url: str, params: dict[str, Any] | None = None) -> Any:
    r = client.get(url, params=params)
    body: Any
    try:
        body = r.json()
    except ValueError:
        body = {"_non_json_body": r.text[:2000]}
    return {"status": r.status_code, "url": str(r.url), "body": body}


# ----------------------------------------------------------------------------- sources


def rec_pubchem(client: httpx.Client, formula: str) -> dict[str, Any]:
    base = "https://pubchem.ncbi.nlm.nih.gov/rest"
    out: dict[str, Any] = {}
    out["by_formula"] = get_json(client, f"{base}/pug/compound/fastformula/{formula}/cids/JSON")
    time.sleep(PUBCHEM_PAUSE_S)
    name = COMMON_NAMES[formula]
    out["by_name"] = get_json(client, f"{base}/pug/compound/name/{name}/cids/JSON")
    time.sleep(PUBCHEM_PAUSE_S)

    def cids(resp: dict[str, Any]) -> list[int]:
        body = resp["body"]
        if isinstance(body, dict):
            lst = body.get("IdentifierList", {}).get("CID", [])
            return sorted(int(c) for c in lst)
        return []

    name_cids = cids(out["by_name"])
    formula_cids = cids(out["by_formula"])
    chosen = (name_cids or formula_cids or [None])[0]
    out["chosen_cid"] = chosen
    out["chosen_rule"] = "min CID from name lookup, else min CID from formula lookup"
    out["by_formula"] = {"status": out["by_formula"]["status"], "cids": formula_cids}
    out["by_name"] = {"status": out["by_name"]["status"], "cids": name_cids}
    if chosen is not None:
        ghs = get_json(
            client,
            f"{base}/pug_view/data/compound/{chosen}/JSON",
            params={"heading": "GHS Classification"},
        )
        out["ghs"] = {"status": ghs["status"], "summary": summarize_ghs(ghs["body"])}
        time.sleep(PUBCHEM_PAUSE_S)
        syn = get_json(client, f"{base}/pug/compound/cid/{chosen}/synonyms/JSON")
        names: list[str] = []
        body = syn["body"]
        if isinstance(body, dict):
            infos = body.get("InformationList", {}).get("Information", [])
            names = [str(n) for info in infos for n in info.get("Synonym", [])]
        out["synonyms"] = {"status": syn["status"], "count": len(names), "first": names[:8]}
        time.sleep(PUBCHEM_PAUSE_S)
    return {"records": 1 if chosen is not None else 0, "detail": out}


def summarize_ghs(body: Any) -> dict[str, Any]:
    """Pull pictogram and hazard-statement counts out of a PUG-View GHS response."""
    if not isinstance(body, dict) or "Record" not in body:
        return {"present": False, "top_keys": sorted(body) if isinstance(body, dict) else None}
    text: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "String" and isinstance(v, str):
                    text.append(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for x in node:
                walk(x)

    walk(body["Record"])
    h_codes = sorted({m.group(0) for t in text for m in [re.match(r"^H\d{3}[a-z]*", t)] if m})
    return {"present": True, "strings": len(text), "h_codes": h_codes}


def _optimade(client: httpx.Client, base: str, formula: str) -> dict[str, Any]:
    f = optimade_formula(formula)
    resp = get_json(
        client,
        f"{base}/structures",
        params={"filter": f'chemical_formula_reduced="{f}"', "page_limit": 10},
    )
    body = resp["body"]
    n = len(body.get("data", [])) if isinstance(body, dict) else 0
    meta = body.get("meta", {}) if isinstance(body, dict) else {}
    return {
        "records": n,
        "detail": {
            "optimade_formula": f,
            "status": resp["status"],
            "data_returned": meta.get("data_returned"),
            "more_data_available": meta.get("more_data_available"),
            "api_version": meta.get("api_version"),
        },
    }


COD_BASE = "https://www.crystallography.net/cod/optimade/v1"
OQMD_BASE = "https://oqmd.org/optimade/v1"


def rec_cod(client: httpx.Client, formula: str) -> dict[str, Any]:
    return _optimade(client, COD_BASE, formula)


def rec_oqmd(client: httpx.Client, formula: str) -> dict[str, Any]:
    return _optimade(client, OQMD_BASE, formula)


def rec_optimade_info(client: httpx.Client, base: str) -> dict[str, Any]:
    info = get_json(client, f"{base}/info")
    sinfo = get_json(client, f"{base}/info/structures")
    props = {}
    body = sinfo["body"]
    if isinstance(body, dict):
        props = body.get("data", {}).get("properties", {})
    return {
        "records": len(props),
        "detail": {"info_status": info["status"], "properties": sorted(props)},
    }


def rec_openalex(client: httpx.Client, formula: str) -> dict[str, Any]:
    key = os.environ.get("OPENALEX_API_KEY")
    if not key:
        raise SkipSourceError("OPENALEX_API_KEY not set")
    base = "https://api.openalex.org"
    common = {
        "per-page": 5,
        "select": "id,doi,title,publication_year,abstract_inverted_index,primary_location",
        "api_key": key,
    }
    mailto = os.environ.get("OPENALEX_MAILTO")
    if mailto:
        common["mailto"] = mailto
    out: dict[str, Any] = {}
    for label, q in (
        ("formula", f"{formula} dielectric thin film"),
        ("synonym", f"{OPENALEX_SYNONYM[formula]} dielectric thin film"),
    ):
        resp = get_json(
            client, f"{base}/works", params={**common, "search": q, "filter": "has_abstract:true"}
        )
        body = resp["body"]
        results = body.get("results", []) if isinstance(body, dict) else []
        out[label] = {
            "status": resp["status"],
            "count": body.get("meta", {}).get("count") if isinstance(body, dict) else None,
            "returned": len(results),
            "with_abstract": sum(1 for w in results if w.get("abstract_inverted_index")),
        }
    return {"records": out["formula"]["returned"] + out["synonym"]["returned"], "detail": out}


class SkipSourceError(Exception):
    pass


MP_FIELDS = [
    "material_id",
    "formula_pretty",
    "composition_reduced",
    "nelements",
    "energy_above_hull",
    "is_stable",
    "band_gap",
    "theoretical",
    "deprecated",
    "symmetry",
    "database_IDs",
    "last_updated",
]


def _mprester() -> Any:
    key = os.environ.get("MP_API_KEY")
    if not key:
        raise SkipSourceError("MP_API_KEY not set")
    from mp_api.client import MPRester

    return MPRester(key)


def rec_mp(client: httpx.Client, formula: str) -> dict[str, Any]:
    with _mprester() as mpr:
        version = mpr.db_version
        docs = mpr.materials.summary.search(formula=formula, fields=MP_FIELDS)
        ids = [str(d.material_id) for d in docs]
        diel = mpr.materials.dielectric.search(material_ids=ids) if ids else []
        # Thermo docs carry the functional (thermo_type) behind the hull energy. Record them
        # for the lowest-hull entry and the first theoretical entry only, to keep cassettes small.
        probe = (
            sorted(
                (d for d in docs if d.energy_above_hull is not None),
                key=lambda d: d.energy_above_hull,
            )[:1]
            + [d for d in docs if d.theoretical][:1]
        )
        probe_ids = sorted({str(d.material_id) for d in probe})
        thermo = (
            mpr.materials.thermo.search(
                material_ids=probe_ids,
                fields=["material_id", "thermo_type", "energy_above_hull", "is_stable"],
            )
            if probe_ids
            else []
        )
    rows = []
    for d in docs:
        rows.append(
            {
                "material_id": str(d.material_id),
                "theoretical": d.theoretical,
                "deprecated": d.deprecated,
                "energy_above_hull": d.energy_above_hull,
                "band_gap": d.band_gap,
                "spacegroup": getattr(d.symmetry, "symbol", None) if d.symmetry else None,
            }
        )
    return {
        "records": len(docs),
        "detail": {
            "db_version": version,
            "n_dielectric": len(diel),
            "dielectric_ids": sorted(str(x.material_id) for x in diel),
            "thermo_probe": [
                {
                    "material_id": str(t.material_id),
                    "thermo_type": str(t.thermo_type),
                    "energy_above_hull": t.energy_above_hull,
                    "is_stable": t.is_stable,
                }
                for t in thermo
            ],
            "rows": rows,
        },
    }


def rec_mp_discovery(client: httpx.Client) -> dict[str, Any]:
    t0 = time.monotonic()
    with _mprester() as mpr:
        version = mpr.db_version
        docs = mpr.materials.summary.search(
            elements=["O"],
            num_elements=(2, 3),
            band_gap=(3.0, None),
            energy_above_hull=(0.0, 0.05),
            fields=[
                "material_id",
                "formula_pretty",
                "nelements",
                "energy_above_hull",
                "band_gap",
                "theoretical",
            ],
            num_chunks=2,
            chunk_size=100,
        )
    return {
        "records": len(docs),
        "detail": {
            "db_version": version,
            "elapsed_s": round(time.monotonic() - t0, 2),
            "num_chunks": 2,
            "chunk_size": 100,
        },
    }


def rec_mp_deprecated_probe(client: httpx.Client) -> dict[str, Any]:
    """Can deprecated entries be fetched at all? Unverified before this recording."""
    with _mprester() as mpr:
        try:
            docs = mpr.materials.summary.search(
                formula="HfO2",
                deprecated=True,
                fields=["material_id", "deprecated", "formula_pretty"],
            )
            outcome = {
                "supported": True,
                "n": len(docs),
                "ids": sorted(str(d.material_id) for d in docs)[:5],
            }
        except Exception as e:  # noqa: BLE001 - the outcome is the finding
            outcome = {"supported": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
    return {"records": outcome.get("n", 0), "detail": outcome}


# ----------------------------------------------------------------------------- driver

PerMaterial = Callable[[httpx.Client, str], dict[str, Any]]
Single = Callable[[httpx.Client], dict[str, Any]]

PER_MATERIAL: dict[str, PerMaterial] = {
    "pubchem": rec_pubchem,
    "cod": rec_cod,
    "oqmd": rec_oqmd,
    "openalex": rec_openalex,
    "mp": rec_mp,
}
SINGLE: dict[str, list[tuple[str, Single]]] = {
    "cod": [("_info", lambda c: rec_optimade_info(c, COD_BASE))],
    "oqmd": [("_info", lambda c: rec_optimade_info(c, OQMD_BASE))],
    "mp": [("_discovery", rec_mp_discovery), ("_deprecated_probe", rec_mp_deprecated_probe)],
}


def run_source(name: str, mode: str) -> dict[str, Any]:
    my_vcr = make_vcr(mode)
    src_dir = WIRE / name
    src_dir.mkdir(parents=True, exist_ok=True)
    meta: dict[str, Any] = {"source": name, "recorded_at": now(), "mode": mode, "materials": {}}
    headers = {"User-Agent": "materials-triage/0.0.1 (phase-0 wire recording)"}

    def one(label: str, fn: Callable[[httpx.Client], dict[str, Any]]) -> None:
        cassette = src_dir / f"{label}.yaml"
        try:
            with (
                my_vcr.use_cassette(str(cassette)),
                httpx.Client(timeout=HTTP_TIMEOUT, headers=headers) as client,
            ):
                result = fn(client)
            meta["materials"][label] = {"status": "ok", **result}
            print(f"  {name:9s} {label:12s} ok  records={result['records']}")
        except SkipSourceError as e:
            meta["materials"][label] = {"status": "skipped", "reason": str(e)}
            print(f"  {name:9s} {label:12s} SKIPPED ({e})")
        except Exception as e:  # noqa: BLE001 - record every failure in meta, keep going
            meta["materials"][label] = {"status": "error", "error": f"{type(e).__name__}: {e}"}
            print(f"  {name:9s} {label:12s} ERROR {type(e).__name__}: {e}")
            traceback.print_exc(limit=2)

    for label, fn in SINGLE.get(name, []):
        one(label, fn)
    for formula in MATERIALS:
        one(formula, lambda c, f=formula: PER_MATERIAL[name](c, f))

    (src_dir / "meta.json").write_text(json.dumps(meta, indent=2, default=str) + "\n")
    return meta


def main() -> int:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="once", choices=["once", "none", "all", "new_episodes"])
    ap.add_argument("--sources", default=",".join(PER_MATERIAL))
    args = ap.parse_args()
    for src in args.sources.split(","):
        src = src.strip()
        if src not in PER_MATERIAL:
            print(f"unknown source {src}", file=sys.stderr)
            return 2
        print(f"[{src}] mode={args.mode}")
        run_source(src, args.mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
