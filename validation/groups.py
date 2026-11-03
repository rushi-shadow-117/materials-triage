"""Composition groups for the validation set, assembled from recorded cassettes only.

This is the same assembly as scripts/build_sample_bundle.py, generalized to any composition
list, and it never touches the network: vcr runs in record mode "none", so an unrecorded call
raises instead of fetching. Snapshot slices (JARVIS, expt_gap) cover the eleven baseline
oxides; every other composition has no TBmBJ or experimental gap and the group says so. PubChem
cassettes exist for the baseline oxides and the hazard probes only; elsewhere hazard is None,
which the hazard policy treats as unknown, never safe.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml
from pydantic import SecretStr

from materials_triage.adapters import expt_gap, jarvis, mp, openalex, pubchem
from materials_triage.adapters.common import reduced_formula
from materials_triage.adapters.recording import ADAPTER_CASSETTES, ROOT, make_vcr
from materials_triage.adapters.transport import TIMEOUT, USER_AGENT, HttpxTransport
from materials_triage.records import (
    CompositionGroup,
    ExperimentalGapAggregate,
    LiteratureSearchResult,
    Polymorph,
)
from materials_triage.records.groups import build_group, merge_matches
from materials_triage.settings import Settings

SNAPSHOTS = ROOT / "fixtures" / "snapshots"
COMPOSITIONS = ROOT / "fixtures" / "compositions.yaml"
FIXED_TIME = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def load_compositions() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(COMPOSITIONS.read_text())
    return data


def composition_list(spec: dict[str, Any]) -> list[tuple[str, str]]:
    """(display, reduced) pairs deduplicated by reduced formula, in fixture order. Mirrors
    scripts/record_adapters.py so cassette names resolve the same way; kept local so this
    package type-checks without importing the recording script."""
    seen: dict[str, str] = {}
    for members in spec["groups"].values():
        formulas = members["formulas"] if isinstance(members, dict) else members
        for f in formulas:
            seen.setdefault(reduced_formula(f), f)
    return [(display, key) for key, display in seen.items()]


@dataclass(frozen=True)
class LoadedGroup:
    display: str  # formula as the source prints it
    group: CompositionGroup
    hull_status_conflict: bool  # any polymorph's hull status differs by functional
    mp_excluded: tuple[tuple[str, str], ...]  # (mp id, rule) excluded by the adapter


@dataclass(frozen=True)
class Snapshots:
    jarvis_polymorphs: list[Polymorph]
    experimental_gaps: dict[str, ExperimentalGapAggregate]
    manifest: dict[str, Any]

    def shas(self) -> dict[str, str]:
        return {name: str(entry["sha256"]) for name, entry in self.manifest.items()}


def load_snapshots() -> Snapshots:
    manifest = json.loads((SNAPSHOTS / "MANIFEST.json").read_text())["snapshots"]
    jv_raw = jarvis.load_slice(
        SNAPSHOTS / "jarvis_dft_3d.slice.json",
        full_file_sha256=manifest["jarvis_dft_3d"]["sha256"],
        fetched_at=FIXED_TIME,
    )
    gap_raw = expt_gap.load_slice(
        SNAPSHOTS / "expt_gap.slice.json",
        table="expt_gap",
        file_sha256=manifest["expt_gap"]["sha256"],
        fetched_at=FIXED_TIME,
    )
    return Snapshots(
        jarvis_polymorphs=jarvis.polymorphs(jarvis.records(jv_raw)),
        experimental_gaps=expt_gap.aggregates(expt_gap.records(gap_raw)[0]),
        manifest=manifest,
    )


def _transport() -> HttpxTransport:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        mp_api_key=SecretStr("recorded"),
        openalex_api_key=SecretStr("recorded"),
    )
    return HttpxTransport(
        settings,
        client=httpx.Client(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}),
        sleep=lambda _s: None,
    )


def recorded_compositions() -> list[tuple[str, str]]:
    """(display, reduced) pairs for every composition Track 0 recorded, in fixture order."""
    return composition_list(load_compositions())


def load_groups(
    keys: Iterable[str] | None = None, *, snapshots: Snapshots | None = None
) -> dict[str, LoadedGroup]:
    """Assemble one CompositionGroup per reduced formula from cassettes. No network."""
    spec = load_compositions()
    pairs = composition_list(spec)
    wanted = None if keys is None else set(keys)
    snaps = snapshots or load_snapshots()
    vcr = make_vcr("none")
    transport = _transport()
    pubchem_names: dict[str, str] = {
        **{f: spec["common_names"][f] for f in spec["groups"]["baseline_oxides"]},
        **spec["hazard_probes"],
    }

    def cassette(source: str, name: str) -> Any:
        return vcr.use_cassette(str(ADAPTER_CASSETTES / source / f"{name}.yaml"))

    out: dict[str, LoadedGroup] = {}
    for display, key in pairs:
        if wanted is not None and key not in wanted:
            continue
        with cassette("mp", f"summary_{key}"):
            summary = mp.summary_records(transport.get(mp.plan_summary_by_formula(key)))
        ids = [s.source_record_id for s in summary]
        thermo = diel = []
        if ids:
            with cassette("mp", f"thermo_{key}"):
                thermo = [
                    r for c in mp.plan_thermo(ids) for r in mp.thermo_records(transport.get(c))
                ]
            with cassette("mp", f"dielectric_{key}"):
                diel = [
                    r
                    for c in mp.plan_dielectric(ids)
                    for r in mp.dielectric_records(transport.get(c))
                ]
        assembly = mp.assemble(summary, thermo, diel)
        merged = merge_matches(
            assembly.polymorphs, [p for p in snaps.jarvis_polymorphs if p.composition == key]
        )
        hazard = None
        pubchem_cassette = ADAPTER_CASSETTES / "pubchem" / f"{display}.yaml"
        if display in pubchem_names and pubchem_cassette.exists():
            with cassette("pubchem", display):
                by_name = transport.get(pubchem.plan_cids_by_name(pubchem_names[display]))
                by_formula = transport.get(pubchem.plan_cids_by_formula(display))
                cid, _ = pubchem.choose_cid(pubchem.cids(by_name), pubchem.cids(by_formula))
                ghs = transport.get(pubchem.plan_ghs(cid)) if cid else None
                syn = transport.get(pubchem.plan_synonyms(cid)) if cid else None
            hazard = pubchem.hazard(key, by_name=by_name, by_formula=by_formula, ghs=ghs, syn=syn)
        query = f"{display} thin film"
        with cassette("openalex", key):
            literature = openalex.result(
                transport.get(openalex.plan_search(query)),
                transport.get(openalex.plan_count(query)),
                composition=key,
                query=query,
                scope="title_and_abstract",
            )
        group = build_group(
            key,
            merged,
            experimental_gaps=snaps.experimental_gaps.get(key),
            hazard=hazard,
            literature=literature,
        )
        out[key] = LoadedGroup(
            display=display,
            group=group,
            hull_status_conflict=any(p.hull_status_conflict for p in merged),
            mp_excluded=tuple((e.mp_id, e.rule) for e in assembly.excluded),
        )
    missing = [] if wanted is None else sorted(wanted - set(out))
    if missing:
        raise KeyError(f"not in fixtures/compositions.yaml: {missing}")
    return out


def literature_state(lit: LiteratureSearchResult | None) -> str:
    """has_abstracts | no_abstract (works matched, none with an abstract) | no_match (no work
    matched the query at all). The last two are both evidence tier "no abstract", never
    "no support"; the sub-state is shown so the reader knows which."""
    if lit is None or (lit.matched_total or 0) == 0:
        return "no_match"
    if not lit.hits:
        return "no_abstract"
    return "has_abstracts"


def no_abstract_compositions(groups: dict[str, LoadedGroup]) -> dict[str, str]:
    """Composition -> sub-state for every group without a usable abstract."""
    return {
        k: literature_state(g.group.literature)
        for k, g in sorted(groups.items())
        if literature_state(g.group.literature) != "has_abstracts"
    }


def cassette_manifest_path() -> Path:
    return ADAPTER_CASSETTES / "recording_manifest.json"
