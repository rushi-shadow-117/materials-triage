"""Record adapter cassettes for the Track 0 composition set.

Usage:
    uv run python scripts/record_adapters.py [--only mp,openalex,pubchem,discovery] [--limit N]

Reads fixtures/compositions.yaml, calls each adapter through HttpxTransport under vcr in
new_episodes mode (existing interactions are kept, missing ones recorded), and writes
fixtures/adapters/recording_manifest.json with what was recorded per composition.
Needs MP_API_KEY and OPENALEX_API_KEY in .env.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from datetime import UTC, datetime
from typing import Any

import httpx
import yaml

from materials_triage.adapters import mp, openalex, pubchem
from materials_triage.adapters.common import reduced_formula
from materials_triage.adapters.recording import ADAPTER_CASSETTES, ROOT, cassette_path, make_vcr
from materials_triage.adapters.transport import TIMEOUT, USER_AGENT, HttpxTransport
from materials_triage.settings import Settings

VCR = make_vcr("new_episodes")


def load_compositions() -> dict[str, Any]:
    return yaml.safe_load((ROOT / "fixtures" / "compositions.yaml").read_text())


def composition_list(spec: dict[str, Any]) -> list[tuple[str, str]]:
    """(display formula, reduced formula) pairs, deduplicated by reduced formula."""
    seen: dict[str, str] = {}
    for members in spec["groups"].values():
        formulas = members["formulas"] if isinstance(members, dict) else members
        for f in formulas:
            key = reduced_formula(f)
            seen.setdefault(key, f)
    return [(display, key) for key, display in seen.items()]


def record_mp(transport: HttpxTransport, display: str, key: str, manifest: dict[str, Any]) -> None:
    entry = manifest.setdefault(key, {"display": display, "reduced": key})
    with VCR.use_cassette(str(cassette_path("mp", f"summary_{key}"))):
        summary = mp.summary_records(transport.get(mp.plan_summary_by_formula(key)))
    ids = sorted({r.source_record_id for r in summary})
    entry["mp_summary_docs"] = len(summary)
    entry["mp_ids"] = ids
    entry["mp_licenses"] = sorted({str(r.license) for r in summary})
    if not ids:
        entry["mp_note"] = "no summary documents for this formula"
        return
    with VCR.use_cassette(str(cassette_path("mp", f"thermo_{key}"))):
        thermo = [
            rec for call in mp.plan_thermo(ids) for rec in mp.thermo_records(transport.get(call))
        ]
    with VCR.use_cassette(str(cassette_path("mp", f"dielectric_{key}"))):
        diel = [
            rec
            for call in mp.plan_dielectric(ids)
            for rec in mp.dielectric_records(transport.get(call))
        ]
    entry["mp_thermo_docs"] = len(thermo)
    entry["mp_dielectric_docs"] = len(diel)
    assembly = mp.assemble(summary, thermo, diel)
    entry["mp_polymorphs"] = len(assembly.polymorphs)
    entry["mp_excluded"] = [(e.mp_id, e.rule) for e in assembly.excluded]
    entry["mp_hull_conflicts"] = [p.ids.mp for p in assembly.polymorphs if p.hull_status_conflict]


def record_openalex(
    transport: HttpxTransport,
    display: str,
    key: str,
    synonyms: dict[str, str],
    manifest: dict[str, Any],
) -> None:
    entry = manifest.setdefault(key, {"display": display, "reduced": key})
    queries = [f"{display} thin film"]
    if display in synonyms and synonyms[display].lower() not in display.lower():
        queries.append(f"{synonyms[display]} thin film")
    results = {}
    with VCR.use_cassette(str(cassette_path("openalex", key))):
        for q in queries:
            search = transport.get(openalex.plan_search(q))
            count = transport.get(openalex.plan_count(q))
            res = openalex.result(
                search, count, composition=key, query=q, scope="title_and_abstract"
            )
            results[q] = {
                "matched_total": res.matched_total,
                "matched_with_abstract": res.matched_with_abstract,
                "hits": len(res.hits),
            }
    entry["openalex"] = results


def record_pubchem(
    transport: HttpxTransport, display: str, key: str, name: str, manifest: dict[str, Any]
) -> None:
    entry = manifest.setdefault(key, {"display": display, "reduced": key})
    with VCR.use_cassette(str(cassette_path("pubchem", display))):
        by_name = transport.get(pubchem.plan_cids_by_name(name))
        by_formula = transport.get(pubchem.plan_cids_by_formula(display))
        cid, rule = pubchem.choose_cid(pubchem.cids(by_name), pubchem.cids(by_formula))
        ghs = transport.get(pubchem.plan_ghs(cid)) if cid else None
        syn = transport.get(pubchem.plan_synonyms(cid)) if cid else None
    h = pubchem.hazard(key, by_name=by_name, by_formula=by_formula, ghs=ghs, syn=syn)
    entry["pubchem"] = {
        "cid": h.cid,
        "rule": rule,
        "h_codes": h.h_codes,
        "notifications_total": h.notifications_total,
        "echa": h.echa_attribution_required,
        "synonyms": len(h.synonyms),
    }


def record_discovery(
    transport: HttpxTransport, name: str, spec: dict[str, Any], manifest: dict[str, Any]
) -> None:
    f = mp.DiscoveryFilter(
        elements=tuple(spec["elements"]),
        nelements_min=spec["nelements"][0],
        nelements_max=spec["nelements"][1],
        band_gap_min=spec.get("band_gap_min"),
        band_gap_max=spec.get("band_gap_max"),
        energy_above_hull_max=spec.get("energy_above_hull_max"),
        exclude_elements=tuple(spec.get("exclude_elements", [])),
    )
    cassette = "discovery_oxides_full" if name == "oxides_gap_3_plus" else f"discovery_{name}"
    t0 = time.monotonic()
    with VCR.use_cassette(str(cassette_path("mp", cassette))):
        result = mp.run_discovery(transport.get, f)
    manifest.setdefault("_discovery", {})[name] = {
        "cassette": f"mp/{cassette}.yaml",
        "filter": f.params(),
        "total_available": result.total_available,
        "returned": result.returned,
        "refused": result.refused,
        "elapsed_s": round(time.monotonic() - t0, 1),
        "licenses": sorted({str(r.license) for r in result.records}),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="mp,openalex,pubchem,discovery")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    only = set(args.only.split(","))
    spec = load_compositions()
    comps = composition_list(spec)
    if args.limit:
        comps = comps[: args.limit]
    settings = Settings()
    transport = HttpxTransport(
        settings, client=httpx.Client(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
    )
    manifest_path = ADAPTER_CASSETTES / "recording_manifest.json"
    manifest: dict[str, Any] = (
        json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    )
    manifest["_recorded_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    failures: list[dict[str, str]] = []

    def attempt(label: str, fn: Any) -> None:
        try:
            fn()
            print(f"ok    {label}", flush=True)
        except Exception as e:  # noqa: BLE001 - record and continue; the manifest is the report
            failures.append({"step": label, "error": f"{type(e).__name__}: {str(e)[:200]}"})
            print(f"FAIL  {label}: {type(e).__name__}: {str(e)[:120]}", flush=True)
            traceback.print_exc(limit=1)

    pubchem_targets = {
        **{
            f: spec["common_names"][f]
            for f in spec["groups"]["baseline_oxides"]
            if f in spec["common_names"]
        },
        **spec["hazard_probes"],
    }
    for display, key in comps:
        if "mp" in only:
            attempt(f"mp {display}", lambda d=display, k=key: record_mp(transport, d, k, manifest))
        if "openalex" in only:
            attempt(
                f"openalex {display}",
                lambda d=display, k=key: record_openalex(
                    transport, d, k, spec["synonyms"], manifest
                ),
            )
    if "pubchem" in only:
        for display, name in pubchem_targets.items():
            attempt(
                f"pubchem {display}",
                lambda d=display, n=name: record_pubchem(
                    transport, d, reduced_formula(d), n, manifest
                ),
            )
    if "discovery" in only:
        for name, dspec in spec["discovery"].items():
            attempt(
                f"discovery {name}",
                lambda n=name, s=dspec: record_discovery(transport, n, s, manifest),
            )
    manifest["_failures"] = failures
    manifest["_compositions"] = len(comps)
    manifest_path.write_text(json.dumps(manifest, indent=1, default=str) + "\n")
    print(f"done: {len(comps)} compositions, {len(failures)} failures -> {manifest_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
