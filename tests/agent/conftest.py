"""Shared fixtures for the agent tests: sample bundle, config layers, synthetic abstracts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from materials_triage.adapters import openalex
from materials_triage.adapters.base import Call, RawResponse, Source
from materials_triage.config import schema as cs
from materials_triage.records import LiteratureHit
from materials_triage.records.bundle import ProvenanceBundle

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "fixtures" / "bundles" / "sample_bundle.json"
SYNTHETIC = ROOT / "fixtures" / "synthetic"


@pytest.fixture
def bundle() -> ProvenanceBundle:
    return ProvenanceBundle.model_validate_json(SAMPLE.read_text())


@pytest.fixture(scope="session")
def layers() -> tuple[cs.CoreConfig, cs.SiteProfile, cs.ScoringProfile]:
    paths = cs.default_paths()
    profile, _ = cs.scoring_profile_from_yaml(paths["scoring_profile"])
    site = cs.site_profile_from_yaml(paths["site_profile"])
    return cs.CoreConfig(), site, profile


@pytest.fixture(scope="session")
def effective(
    layers: tuple[cs.CoreConfig, cs.SiteProfile, cs.ScoringProfile],
) -> cs.EffectiveConfig:
    core, site, profile = layers
    eff, _ = cs.resolve(core, site, profile, cs.QuerySettings(profile=profile.name))
    return eff


def synthetic_hit(name: str, composition: str) -> LiteratureHit:
    """A LiteratureHit built from a synthetic OpenAlex document through the real adapter."""
    doc = json.loads((SYNTHETIC / name).read_text())
    assert doc.get("_synthetic") is True
    body = {k: v for k, v in doc.items() if not k.startswith("_")}
    call = Call(source=Source.OPENALEX, endpoint="works", url=openalex.BASE, params={"q": name})
    raw = RawResponse(
        call=call,
        status=200,
        body=json.dumps(body).encode(),
        content_type="application/json",
        fetched_at=datetime(2026, 11, 2, tzinfo=UTC),
        source_version="synthetic",
    )
    result = openalex.result(
        raw, None, composition=composition, query=name, scope="title_and_abstract"
    )
    return result.hits[0]


@pytest.fixture
def injection_hit() -> LiteratureHit:
    return synthetic_hit("openalex_injection.json", "HfO2")
