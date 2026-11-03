"""End to end over recorded cassettes with no network, no database, and the sample stand-in
scorer: the pipeline produces a valid bundle whose ranks match the sample."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.seed_store_from_cassettes import iter_raw

from materials_triage.adapters.base import Call, RawResponse
from materials_triage.agent import llm, parse, pipeline, scoring_port
from materials_triage.config import schema as cs
from materials_triage.records.bundle import EvidenceLabel, ProvenanceBundle
from materials_triage.render import markdown

ROOT = Path(__file__).resolve().parents[2]
ADAPTERS = ROOT / "fixtures" / "adapters"
Layers = tuple[cs.CoreConfig, cs.SiteProfile, cs.ScoringProfile]


class CassetteTransport:
    """Every recorded interaction keyed by the call's cache key; a miss is None, never a fetch."""

    def __init__(self) -> None:
        self.by_key: dict[str, RawResponse] = {}
        for path, raw in iter_raw(ADAPTERS):
            if "discovery" in path.name:
                continue
            self.by_key.setdefault(raw.call.cache_key, raw)
        self.misses: list[Call] = []

    def __call__(self, call: Call) -> RawResponse | None:
        raw = self.by_key.get(call.cache_key)
        if raw is None:
            self.misses.append(call)
        return raw


@pytest.fixture(scope="module")
def transport() -> CassetteTransport:
    return CassetteTransport()


@pytest.fixture(scope="module")
def sources() -> pipeline.Sources:
    return pipeline.Sources.load()


def _inputs(layers: Layers, tmp_path: Path, formulas: list[str]) -> pipeline.RunInputs:
    core, site, profile = layers
    path = tmp_path / "criteria.yaml"
    path.write_text("mode: candidate_list\ncandidate_list: [" + ", ".join(formulas) + "]\n")
    outcome = parse.parse_from_file(
        path, core=core, site=site, profile=profile, cli_profile=profile.name
    )
    hazard = cs.load_yaml(cs.default_paths()["hazard_policy"])
    return pipeline.RunInputs(
        request_text="Rank the baseline oxides",
        parse=outcome,
        core=core,
        site=site,
        profile=profile,
        hazard_policy=hazard,
    )


def test_candidate_list_run_matches_the_sample_bundle(
    layers: Layers, tmp_path: Path, transport: CassetteTransport, sources: pipeline.Sources
) -> None:
    sample = ProvenanceBundle.model_validate_json(scoring_port.SAMPLE_BUNDLE.read_text())
    formulas = [c.composition for c in sample.candidates]
    inputs = _inputs(layers, tmp_path, formulas)
    bundle = pipeline.run(
        inputs, fetch=transport, sources=sources, scorer=scoring_port.default_scorer()
    )
    assert transport.misses == []
    assert bundle.bundle_version == 2 and bundle.run.finished_at is not None
    assert [(c.rank, c.composition) for c in bundle.ranked()] == [
        (c.rank, c.composition) for c in sample.ranked()
    ]
    assert {c.composition for c in bundle.excluded()} == {"ThO2", "BeO"}
    assert [a.composition for a in bundle.anchors] == ["SiO2"] and bundle.anchors[0].out_of == 8
    assert bundle.run.partial is False and bundle.availability_events == []
    assert bundle.run.source_versions["materials_project"] == "2026.09.28"
    assert bundle.run.model_version is None and bundle.run.prompt_hash is None
    assert bundle.run.policy_version == pipeline.policy_version()
    assert bundle.run.note is not None and "Track A scorer not merged" in bundle.run.note
    hf = next(c for c in bundle.candidates if c.composition == "HfO2")
    assert hf.group.polymorphs.total == 15 and hf.group.polymorphs.ground_state is not None
    assert hf.group.polymorphs.ground_state.mp_id == "mp-352"
    assert hf.group.hazard is not None and hf.group.hazard.cid == 292779
    assert hf.group.literature is not None and len(hf.group.literature.hits) == 5
    assert hf.rationale_slot == "candidate:HfO2:one_line"
    assert len(bundle.evidence) == sum(
        len(c.group.literature.hits) for c in bundle.ranked() if c.group.literature
    )
    assert {e.label for e in bundle.evidence} == {EvidenceLabel.UNCLASSIFIED}
    assert bundle.verifier is not None and bundle.verifier.passed
    assert all(s.verified for s in bundle.rationale.values())
    steps = [d.step for d in bundle.decision_log]
    assert steps[:4] == ["start", "fetch", "score", "classify"] and steps[-1] == "verify"
    assert bundle.decision_log[0].detail["code_version"]
    assert len(bundle.missing_properties) == 7
    text = markdown.render_pi_summary(bundle, layers[1])
    assert "| 1 | Al2O3 |" in text
    ProvenanceBundle.model_validate_json(bundle.model_dump_json())


def test_missing_sources_become_events_and_a_partial_run(
    layers: Layers, tmp_path: Path, transport: CassetteTransport, sources: pipeline.Sources
) -> None:
    def flaky(call: Call) -> RawResponse | None:
        if call.source.value == "openalex":
            return None
        return transport(call)

    inputs = _inputs(layers, tmp_path, ["HfO2", "Ga2O3"])
    bundle = pipeline.run(
        inputs, fetch=flaky, sources=sources, scorer=scoring_port.default_scorer()
    )
    assert bundle.run.partial is True
    assert bundle.run.partial_reasons == ["Ga2O3: no Materials Project summary available"]
    assert {e["source"] for e in bundle.availability_events} == {"openalex", "materials_project"}
    hf = next(c for c in bundle.candidates if c.composition == "HfO2")
    assert hf.group.literature is None and bundle.evidence == []


def test_llm_run_records_model_prompt_hash_and_budgets(
    layers: Layers, tmp_path: Path, transport: CassetteTransport, sources: pipeline.Sources
) -> None:
    inputs = _inputs(layers, tmp_path, ["HfO2"])
    fake = llm.FakeLLM(
        [{"expect_tool": "classify_abstract", "stop_reason": "refusal", "content": []}] * 5
        + [
            {
                "expect_tool": "write_rationale",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "write_rationale",
                        "input": {
                            "slots": [
                                {
                                    "slot": "candidate:HfO2:one_line",
                                    "text": "{formula:HfO2} leads. It has a gap of 9.9 eV.",
                                }
                            ]
                        },
                    }
                ],
                "usage": {"input_tokens": 50, "output_tokens": 20},
            }
        ],
        model="fake-opus",
    )
    bundle = pipeline.run(
        inputs, fetch=transport, sources=sources, scorer=scoring_port.default_scorer(), llm=fake
    )
    assert bundle.run.model_version == "fake-opus" and bundle.run.provider == "fake"
    assert bundle.run.prompt_hash is not None and bundle.run.budgets_used["tool_calls"] == 6.0
    assert bundle.rationale["candidate:HfO2:one_line"].text == "{formula:HfO2} leads."
    assert bundle.rationale["candidate:HfO2:one_line"].removed_fragments == [
        "It has a gap of 9.9 eV."
    ]
    assert bundle.verifier is not None and bundle.verifier.passed is False
    assert [f.kind for f in bundle.verifier.failures] == ["unresolved_number"]
    assert all(e.verifier_note == "classifier failed: refusal" for e in bundle.evidence)


def test_refused_request_yields_an_empty_bundle_with_the_refusal_logged(
    layers: Layers, sources: pipeline.Sources
) -> None:
    core, site, profile = layers
    outcome = parse.ParseOutcome(
        parsed_by="llm", refusal=core.refusals.wetlab, category=parse.OutOfScope.WETLAB
    )
    inputs = pipeline.RunInputs(
        request_text="Deposit it tomorrow",
        parse=outcome,
        core=core,
        site=site,
        profile=profile,
        hazard_policy={},
    )
    bundle = pipeline.run(
        inputs, fetch=lambda c: None, sources=sources, scorer=scoring_port.default_scorer()
    )
    assert bundle.candidates == [] and bundle.criteria.mode == "refused"
    refused = next(d for d in bundle.decision_log if d.step == "refused")
    assert refused.detail["text"] == core.refusals.wetlab and refused.detail["category"] == "wetlab"
    assert core.refusals.wetlab in markdown.render_pi_summary(bundle, site)
