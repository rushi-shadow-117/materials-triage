"""Executors turn a Case into an Observation.

SampleBundleExecutor: no pipeline yet. Normal cases observe fixtures/bundles/sample_bundle.json
(real recorded data, illustrative scores); adversarial cases get a transcript from the fake
LLM. Configuration is hashed before and after every run from the effective config and the
files under config/, so config_unchanged has something real to compare.

PipelineExecutor: wired to Track B's entry point after it merges (replay mode against the
seeded store, fake LLM in CI, live LLM when a key is set). Until then it raises.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Protocol

from evals.fake_llm import FakeLLM
from evals.schema import Case, Message, Observation
from materials_triage.config.schema import (
    CONFIG_DIR,
    CoreConfig,
    QuerySettings,
    default_paths,
    resolve,
    scoring_profile_from_yaml,
    site_profile_from_yaml,
)
from materials_triage.records.bundle import ProvenanceBundle

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_BUNDLE = ROOT / "fixtures" / "bundles" / "sample_bundle.json"


class Executor(Protocol):
    name: str

    def run(self, case: Case, repeat: int) -> Observation: ...


def config_files_sha(config_dir: Path = CONFIG_DIR) -> dict[str, str]:
    return {
        str(p.relative_to(config_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(config_dir.rglob("*.yaml"))
    }


def effective_config_sha(case: Case | None = None) -> str:
    paths = default_paths()
    profile, _ = scoring_profile_from_yaml(paths["scoring_profile"])
    site = site_profile_from_yaml(paths["site_profile"])
    settings = {} if case is None else dict(case.settings)
    query = QuerySettings(profile=profile.name, **settings)
    effective, _ = resolve(CoreConfig(), site, profile, query)
    return effective.config_sha


def _sample_bundle() -> ProvenanceBundle:
    return ProvenanceBundle.model_validate_json(SAMPLE_BUNDLE.read_text())


class SampleBundleExecutor:
    name = "sample_bundle"

    def __init__(self, llm: FakeLLM | None = None) -> None:
        self.llm = llm or FakeLLM()

    def run(self, case: Case, repeat: int) -> Observation:
        before_sha, before_files = effective_config_sha(case), config_files_sha()
        transcript = [Message(role="user", content=case.request)]
        log: list[str] = []
        bundle: ProvenanceBundle | None = None
        reply = self.llm.respond(case.request)
        transcript.append(Message(role="assistant", content=reply))
        log.extend(self.llm.log[-1:])
        refused = self.llm.refusal_for(case.request) is not None
        if not refused:
            bundle = _sample_bundle()
            log.append(f"pipeline: sample bundle {bundle.run.run_id} served for {case.id}")
        else:
            log.append(f"refusal: {case.id} redirected by core policy; no run started")
        run_id = str(bundle.run.run_id) if bundle is not None else f"refused-{case.id}-{repeat}"
        after_sha, after_files = effective_config_sha(case), config_files_sha()
        return Observation(
            case_id=case.id,
            repeat=repeat,
            run_id=run_id,
            executor=self.name,
            bundle=bundle,
            transcript=transcript,
            rendered={},
            config_sha_before=before_sha,
            config_sha_after=after_sha,
            config_files_before=before_files,
            config_files_after=after_files,
            log_entries=log,
            llm_calls=1,
        )


class PipelineExecutor:
    """Placeholder until Track B's agent and renderers merge (Track E step 12)."""

    name = "pipeline"

    def run(self, case: Case, repeat: int) -> Observation:
        raise NotImplementedError("PipelineExecutor is wired after Track B merges")


def observation_to_json(obs: Observation) -> str:
    return json.dumps(obs.model_dump(mode="json"), sort_keys=True)
