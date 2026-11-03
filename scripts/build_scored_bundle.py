"""Build fixtures/bundles/scored_bundle.json from recorded data with the Track A scorer.

Groups, provenance, hazards, gaps, and literature replay from cassettes with no network; the
scores are the real scorer's output under the entered config. No LLM step runs, so evidence
is unclassified and rationale slots are empty. `assemble_groups` is shared with the scoring
tests so the golden fixture and the tests read the same data.

Usage: uv run python scripts/build_scored_bundle.py
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID

import httpx
import yaml

from materials_triage.adapters import expt_gap, jarvis, mp, openalex, pubchem
from materials_triage.adapters.base import Call, RawResponse
from materials_triage.adapters.common import reduced_formula
from materials_triage.adapters.recording import ADAPTER_CASSETTES, ROOT, make_vcr
from materials_triage.adapters.transport import TIMEOUT, USER_AGENT, HttpxTransport
from materials_triage.config.schema import CoreConfig, QuerySettings, default_paths, resolve
from materials_triage.records import CompositionGroup
from materials_triage.records.bundle import (
    ConfirmedCriteria,
    DecisionLogEntry,
    FetchMode,
    ProvenanceBundle,
    RunMetadata,
)
from materials_triage.records.groups import build_group, merge_matches
from materials_triage.scoring.profile import (
    echa_attribution,
    load_hazard_policy,
    load_reference_values,
    load_scoring_profile,
    load_site_profile,
)
from materials_triage.scoring.scorer import ScoringInputs, score_run
from materials_triage.settings import Settings

OUT = ROOT / "fixtures" / "bundles" / "scored_bundle.json"
SNAPSHOTS = ROOT / "fixtures" / "snapshots"
VCR = make_vcr("none")
SCORED_RUN_ID = UUID("00000000-0000-4000-8000-000000000002")
FIXED_TIME = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


class FixedTimeTransport:
    """Replayed responses carry the fixture time, not the wall clock, so the golden bundle is
    byte-identical on every build. Live runs keep the transport's own timestamps."""

    def __init__(self, inner: HttpxTransport) -> None:
        self._inner = inner

    def get(self, call: Call) -> RawResponse:
        return self._inner.get(call).model_copy(update={"fetched_at": FIXED_TIME})


def _transport() -> FixedTimeTransport:
    settings = Settings(_env_file=None, mp_api_key="recorded", openalex_api_key="recorded")  # type: ignore[call-arg]
    return FixedTimeTransport(
        HttpxTransport(
            settings,
            client=httpx.Client(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}),
            sleep=lambda _s: None,
        )
    )


def cassette(source: str, name: str):  # type: ignore[no-untyped-def]
    return VCR.use_cassette(str(ADAPTER_CASSETTES / source / f"{name}.yaml"))


def assemble_groups(
    displays: Iterable[str], *, with_enrichment: bool = True
) -> dict[str, CompositionGroup]:
    """Replay every recorded source for the given formulas (as written in
    fixtures/compositions.yaml) into CompositionGroups. `with_enrichment=False` keeps only the
    MP summary documents, the shape discovery sees before enrichment."""
    spec = yaml.safe_load((ROOT / "fixtures" / "compositions.yaml").read_text())
    manifest = json.loads((SNAPSHOTS / "MANIFEST.json").read_text())["snapshots"]
    transport = _transport()
    jv_polys = jarvis.polymorphs(
        jarvis.records(
            jarvis.load_slice(
                SNAPSHOTS / "jarvis_dft_3d.slice.json",
                full_file_sha256=manifest["jarvis_dft_3d"]["sha256"],
                fetched_at=FIXED_TIME,
            )
        )
    )
    gap_aggs = expt_gap.aggregates(
        expt_gap.records(
            expt_gap.load_slice(
                SNAPSHOTS / "expt_gap.slice.json",
                table="expt_gap",
                file_sha256=manifest["expt_gap"]["sha256"],
                fetched_at=FIXED_TIME,
            )
        )[0]
    )
    groups: dict[str, CompositionGroup] = {}
    for display in displays:
        key = reduced_formula(display)
        with cassette("mp", f"summary_{key}"):
            summary = mp.summary_records(transport.get(mp.plan_summary_by_formula(key)))
        if not with_enrichment:
            groups[key] = build_group(
                key, mp.assemble(summary).polymorphs, experimental_gaps=gap_aggs.get(key)
            )
            continue
        ids = [s.source_record_id for s in summary]
        with cassette("mp", f"thermo_{key}"):
            thermo = [r for c in mp.plan_thermo(ids) for r in mp.thermo_records(transport.get(c))]
        with cassette("mp", f"dielectric_{key}"):
            diel = [
                r for c in mp.plan_dielectric(ids) for r in mp.dielectric_records(transport.get(c))
            ]
        merged = merge_matches(
            mp.assemble(summary, thermo, diel).polymorphs,
            [p for p in jv_polys if p.composition == key],
        )
        hazard = None
        name = spec["common_names"].get(display)
        if name is not None and (ADAPTER_CASSETTES / "pubchem" / f"{display}.yaml").exists():
            with cassette("pubchem", display):
                by_name = transport.get(pubchem.plan_cids_by_name(name))
                by_formula = transport.get(pubchem.plan_cids_by_formula(display))
                cid, _ = pubchem.choose_cid(pubchem.cids(by_name), pubchem.cids(by_formula))
                ghs = transport.get(pubchem.plan_ghs(cid)) if cid else None
                syn = transport.get(pubchem.plan_synonyms(cid)) if cid else None
            hazard = pubchem.hazard(key, by_name=by_name, by_formula=by_formula, ghs=ghs, syn=syn)
        literature = None
        if (ADAPTER_CASSETTES / "openalex" / f"{key}.yaml").exists():
            q = f"{display} thin film"
            with cassette("openalex", key):
                literature = openalex.result(
                    transport.get(openalex.plan_search(q)),
                    transport.get(openalex.plan_count(q)),
                    composition=key,
                    query=q,
                    scope="title_and_abstract",
                )
        groups[key] = build_group(
            key, merged, experimental_gaps=gap_aggs.get(key), hazard=hazard, literature=literature
        )
    return groups


def main() -> int:
    spec = yaml.safe_load((ROOT / "fixtures" / "compositions.yaml").read_text())
    manifest = json.loads((SNAPSHOTS / "MANIFEST.json").read_text())["snapshots"]
    groups = assemble_groups(spec["groups"]["baseline_oxides"])
    paths = default_paths()
    loaded = load_scoring_profile(paths["scoring_profile"])
    site = load_site_profile(paths["site_profile"])
    policy = load_hazard_policy(paths["hazard_policy"])
    refs = load_reference_values(paths["reference_values"])
    query = QuerySettings(
        profile=loaded.profile.name, mode="candidate_list", candidate_list=list(groups), top_n=10
    )
    effective, clamps = resolve(CoreConfig(), site, loaded.profile, query)
    result = score_run(
        ScoringInputs(
            groups=list(groups.values()),
            reference_values=refs.entered,
            pending_reference_values=refs.pending,
        ),
        effective=effective,
        loaded=loaded,
        hazard_policy=policy,
        site=site,
        echa=echa_attribution(paths["site_profile"]),
        now=FIXED_TIME,
    )
    bundle = ProvenanceBundle(
        run=RunMetadata(
            run_id=SCORED_RUN_ID,
            started_at=FIXED_TIME,
            finished_at=FIXED_TIME,
            config_sha=effective.config_sha,
            profile_name=loaded.profile.name,
            profile_version=loaded.profile.version,
            policy_version=policy.version,
            prompt_hash=None,
            model_version=None,
            provider=None,
            source_versions={
                "materials_project": "2026.09.28",
                "jarvis_dft_3d": manifest["jarvis_dft_3d"]["sha256"][:12],
                "expt_gap": manifest["expt_gap"]["sha256"][:12],
            },
            fetch_mode=FetchMode.REPLAY,
            partial=False,
            note=(
                "SCORED BUNDLE: recorded data scored by the Track A scorer under the entered "
                "config; no LLM step, so evidence is unclassified and rationale is empty. "
                "Profile notes: " + "; ".join(loaded.notes)
            ),
        ),
        criteria=ConfirmedCriteria(
            request_text="Rank the eleven baseline oxides as thin-film dielectric candidates.",
            parsed_by="criteria_file",
            confirmed_at=FIXED_TIME,
            mode="candidate_list",
            candidate_list=list(groups),
            effective_settings=query.model_dump(mode="json"),
            clamps=[c.model_dump() for c in clamps],  # type: ignore[misc]
            defaults_applied=[f"verbosity={effective.verbosity}", f"view={effective.view}"],
        ),
        candidates=result.candidates,
        anchors=result.anchors,
        missing_properties=result.missing_properties,
        decision_log=[
            DecisionLogEntry(
                at=FIXED_TIME,
                actor="pipeline",
                step="build_scored",
                summary="scored bundle generated from recorded cassettes by the Track A scorer",
            ),
            *result.decision_log,
        ],
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(bundle.model_dump_json(indent=1) + "\n")
    for c in sorted(result.candidates, key=lambda c: (c.rank is None, c.rank or 0)):
        total = None if c.score is None else c.score.total
        print(c.rank, c.composition, total, c.excluded.rule if c.excluded else "", c.flags)
    for a in result.anchors:
        print("anchor", a.composition, a.would_rank, a.out_of)
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
