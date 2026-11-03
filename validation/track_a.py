"""Score validation groups with Track A's scorer (`materials_triage.scoring.scorer.score_run`).

The bundle assembly mirrors scripts/build_scored_bundle.py (Track A), with a fixed run id and
time so results are byte-stable.

Two configurations score the Yim set:

- default: the profile file as loaded by Track A's strict loader, no query overrides.
- Yim-like: the same profile file, with query-level weight overrides (stability, band gap and
  dielectric constant at 1; hazard, simplicity, evidence, deposition method and cost at 0) and
  the file's dielectric target band taken as written. The strict loader drops that band while
  its status is not `entered`, so the Yim-like run reports the status beside its result. The
  profile file is not changed; exclusion rules still apply at weight 0.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from materials_triage.config import schema as cs
from materials_triage.config.schema import CoreConfig, QuerySettings, default_paths, resolve
from materials_triage.records.bundle import (
    ConfirmedCriteria,
    DecisionLogEntry,
    FetchMode,
    ProvenanceBundle,
    RunMetadata,
)
from materials_triage.scoring.profile import (
    echa_attribution,
    load_hazard_policy,
    load_reference_values,
    load_scoring_profile,
    load_site_profile,
)
from materials_triage.scoring.scorer import ScoringInputs, score_run
from validation.groups import LoadedGroup, load_snapshots

VALIDATION_RUN_ID = UUID("00000000-0000-4000-8000-00000000000a")
YIM_LIKE_RUN_ID = UUID("00000000-0000-4000-8000-00000000000b")
FIXED_TIME = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)

YIM_LIKE_WEIGHTS: dict[str, float] = {
    "stability": 1.0,
    "band_gap": 1.0,
    "dielectric_constant": 1.0,
    "hazard": 0.1,  # the site floor (owner decision 2026-11-03); 0 is no longer admissible
    "simplicity": 0.0,
    "evidence": 0.0,
    "deposition_method": 0.0,
    "cost": 0.0,
}
YIM_LIKE_LABEL = (
    "Yim-like configuration: stability, band gap and dielectric constant at weight 1; hazard at "
    "the site floor of 0.1; simplicity, evidence, deposition method and cost at weight 0. "
    "Weights are query-level overrides within site bounds; the default profile file is "
    "unchanged. Exclusion rules "
    "(hazard, stability cutoff, anion policy) still apply at weight 0."
)


def yim_like_target_band() -> tuple[tuple[float, float] | None, str | None]:
    """The dielectric target band as entered in the default profile file, with its status."""
    data = cs.load_yaml(default_paths()["scoring_profile"])
    diel = (data.get("criteria") or {}).get("dielectric_constant") or {}
    band = diel.get("target_band")
    status = diel.get("status")
    if band is None:
        return None, None if status is None else str(status)
    return (float(band[0]), float(band[1])), None if status is None else str(status)


def yim_like_description() -> dict[str, Any]:
    band, status = yim_like_target_band()
    return {
        "label": YIM_LIKE_LABEL,
        "weights": dict(YIM_LIKE_WEIGHTS),
        "dielectric_target_band": None if band is None else list(band),
        "dielectric_target_band_status": status,
    }


def score_with_track_a(
    groups: dict[str, LoadedGroup],
    *,
    request_text: str = "validation run",
    yim_like: bool = False,
) -> ProvenanceBundle:
    paths = default_paths()
    loaded = load_scoring_profile(paths["scoring_profile"])
    site = load_site_profile(paths["site_profile"])
    policy = load_hazard_policy(paths["hazard_policy"])
    refs = load_reference_values(paths["reference_values"])
    keys = sorted(groups)
    query_weights: dict[str, float] = {}
    note_prefix = "VALIDATION RUN: recorded data scored by the Track A scorer under the entered "
    run_id = VALIDATION_RUN_ID
    if yim_like:
        band, status = yim_like_target_band()
        query_weights = dict(YIM_LIKE_WEIGHTS)
        run_id = YIM_LIKE_RUN_ID
        note_prefix = (
            "VALIDATION RUN (YIM-LIKE): recorded data scored by the Track A scorer with "
            f"query weight overrides {YIM_LIKE_WEIGHTS} and the profile file's dielectric "
            f"target band {band} (status {status}) taken as written; the profile file is "
            "unchanged. Scored under the entered "
        )
        if band is not None:
            loaded = replace(
                loaded,
                profile=loaded.profile.model_copy(
                    update={
                        "dielectric_constant": cs.DielectricSettings(weight=1.0, target_band=band)
                    }
                ),
                notes=[
                    *loaded.notes,
                    f"Yim-like run: dielectric target band {list(band)} (status {status}) "
                    "used for the validation comparison only",
                ],
            )
    query = QuerySettings(
        profile=loaded.profile.name,
        mode="candidate_list",
        candidate_list=keys,
        top_n=50,
        weights=query_weights,
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
            run_id=run_id,
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
            note=note_prefix + "config; no LLM step. Profile notes: " + "; ".join(loaded.notes),
        ),
        criteria=ConfirmedCriteria(
            request_text=request_text,
            parsed_by="criteria_file",
            confirmed_at=FIXED_TIME,
            mode="candidate_list",
            candidate_list=keys,
            effective_settings={
                **query.model_dump(mode="json"),
                "effective_weights": dict(effective.weights),
            },
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
                summary=(
                    "validation groups scored from recorded cassettes by the Track A scorer"
                    + (" (Yim-like weight overrides)" if yim_like else "")
                ),
            ),
            *result.decision_log,
        ],
    )


def score_with_track_a_yim_like(
    groups: dict[str, LoadedGroup], *, request_text: str = "validation run (Yim-like)"
) -> ProvenanceBundle:
    return score_with_track_a(groups, request_text=request_text, yim_like=True)
