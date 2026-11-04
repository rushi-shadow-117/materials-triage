"""Recorded groups and entered config shared by the scoring tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from scripts.build_scored_bundle import assemble_groups

from materials_triage.config import schema as cs
from materials_triage.config.schema import CoreConfig, QuerySettings, resolve
from materials_triage.records import CompositionGroup
from materials_triage.scoring.profile import (
    HazardPolicy,
    LoadedProfile,
    LoadedReferenceValues,
    echa_attribution,
    load_hazard_policy,
    load_reference_values,
    load_scoring_profile,
    load_site_profile,
)
from materials_triage.scoring.scorer import ScoringInputs, ScoringResult, score_run

ROOT = Path(__file__).resolve().parents[2]
PATHS = cs.default_paths()
PROFILES = cs.CONFIG_DIR / "scoring_profiles"
BASELINE = yaml.safe_load((ROOT / "fixtures" / "compositions.yaml").read_text())["groups"][
    "baseline_oxides"
]


@pytest.fixture(scope="session")
def baseline_groups() -> dict[str, CompositionGroup]:
    return assemble_groups(BASELINE)


@pytest.fixture(scope="session")
def dielectric_profile() -> LoadedProfile:
    return load_scoring_profile(PROFILES / "oxide_dielectric_thin_film.yaml")


@pytest.fixture(scope="session")
def photocatalyst_profile() -> LoadedProfile:
    return load_scoring_profile(PROFILES / "oxide_photocatalyst.yaml")


@pytest.fixture(scope="session")
def site() -> cs.SiteProfile:
    return load_site_profile(PATHS["site_profile"])


@pytest.fixture(scope="session")
def policy() -> HazardPolicy:
    return load_hazard_policy(PATHS["hazard_policy"])


@pytest.fixture(scope="session")
def references() -> LoadedReferenceValues:
    return load_reference_values(PATHS["reference_values"])


@pytest.fixture(scope="session")
def echa() -> tuple[str, str] | None:
    return echa_attribution(PATHS["site_profile"])


def run(
    groups: dict[str, CompositionGroup],
    loaded: LoadedProfile,
    site: cs.SiteProfile,
    policy: HazardPolicy,
    references: LoadedReferenceValues,
    echa: tuple[str, str] | None,
    *,
    query: QuerySettings | None = None,
    requested: dict[str, str] | None = None,
) -> ScoringResult:
    q = query or QuerySettings(
        profile=loaded.profile.name, mode="candidate_list", candidate_list=list(groups)
    )
    effective, _ = resolve(CoreConfig(), site, loaded.profile, q)
    return score_run(
        ScoringInputs(
            groups=list(groups.values()),
            requested_polymorphs=requested or {},
            reference_values=references.entered,
            pending_reference_values=references.pending,
        ),
        effective=effective,
        loaded=loaded,
        hazard_policy=policy,
        site=site,
        echa=echa,
    )


def with_overrides(loaded: LoadedProfile, **changes: object) -> LoadedProfile:
    """A copy of a loaded profile with nested settings replaced, for test configs
    (for example a conflict tolerance or a dielectric target band)."""
    profile = loaded.profile
    for path, value in changes.items():
        head, _, tail = path.partition("__")
        if tail:
            sub = getattr(profile, head).model_copy(update={tail: value})
            profile = profile.model_copy(update={head: sub})
        else:
            profile = profile.model_copy(update={head: value})
    return LoadedProfile(
        profile=profile,
        evidence_tiers=dict(loaded.evidence_tiers),
        notes=list(loaded.notes),
        source_refs=dict(loaded.source_refs),
        standing_caveats=dict(loaded.standing_caveats),
        cannot_tell_you=list(loaded.cannot_tell_you),
        cannot_tell_you_ref=loaded.cannot_tell_you_ref,
    )
