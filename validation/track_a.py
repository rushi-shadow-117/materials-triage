"""Score validation groups with Track A's scorer (`materials_triage.scoring.scorer.score_run`).

Imported lazily so this package loads on a branch without the scorer; `available()` says
whether it is present. The bundle assembly mirrors scripts/build_scored_bundle.py (Track A),
with a fixed run id and time so results are byte-stable.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from uuid import UUID

from materials_triage.config.schema import CoreConfig, QuerySettings, default_paths, resolve
from materials_triage.records.bundle import (
    ConfirmedCriteria,
    DecisionLogEntry,
    FetchMode,
    ProvenanceBundle,
    RunMetadata,
)
from validation.groups import LoadedGroup, load_snapshots

VALIDATION_RUN_ID = UUID("00000000-0000-4000-8000-00000000000a")
FIXED_TIME = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def available() -> bool:
    return importlib.util.find_spec("materials_triage.scoring.scorer") is not None


def score_with_track_a(
    groups: dict[str, LoadedGroup], *, request_text: str = "validation run"
) -> ProvenanceBundle:
    from materials_triage.scoring.profile import (  # type: ignore[import-not-found,import-untyped,unused-ignore]
        echa_attribution,
        load_hazard_policy,
        load_reference_values,
        load_scoring_profile,
        load_site_profile,
    )
    from materials_triage.scoring.scorer import (  # type: ignore[import-not-found,import-untyped,unused-ignore]
        ScoringInputs,
        score_run,
    )

    paths = default_paths()
    loaded = load_scoring_profile(paths["scoring_profile"])
    site = load_site_profile(paths["site_profile"])
    policy = load_hazard_policy(paths["hazard_policy"])
    refs = load_reference_values(paths["reference_values"])
    keys = sorted(groups)
    query = QuerySettings(
        profile=loaded.profile.name, mode="candidate_list", candidate_list=keys, top_n=50
    )
    effective, clamps = resolve(CoreConfig(), site, loaded.profile, query)
    result = score_run(
        ScoringInputs(
            groups=[groups[k].group for k in keys],
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
    snapshots = load_snapshots()
    return ProvenanceBundle(
        run=RunMetadata(
            run_id=VALIDATION_RUN_ID,
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
                **{k: v[:12] for k, v in snapshots.shas().items()},
            },
            fetch_mode=FetchMode.REPLAY,
            partial=False,
            note=(
                "VALIDATION RUN: recorded data scored by the Track A scorer under the entered "
                "config; no LLM step. Profile notes: " + "; ".join(loaded.notes)
            ),
        ),
        criteria=ConfirmedCriteria(
            request_text=request_text,
            parsed_by="criteria_file",
            confirmed_at=FIXED_TIME,
            mode="candidate_list",
            candidate_list=keys,
            effective_settings=query.model_dump(mode="json"),
            clamps=[c.model_dump() for c in clamps],  # type: ignore[misc]
        ),
        candidates=result.candidates,
        anchors=result.anchors,
        missing_properties=result.missing_properties,
        decision_log=[
            DecisionLogEntry(
                at=FIXED_TIME,
                actor="pipeline",
                step="validation",
                summary="validation groups scored from recorded cassettes by the Track A scorer",
            ),
            *result.decision_log,
        ],
    )
