"""End to end over recorded cassettes with no network, no database, and the sample stand-in
scorer: the pipeline produces a valid bundle whose ranks match the sample."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
from scripts.seed_store_from_cassettes import iter_raw

from materials_triage.adapters.base import Call, RawResponse
from materials_triage.agent import llm, parse, pipeline, scoring_port
from materials_triage.agent.loop import Budget
from materials_triage.config import schema as cs
from materials_triage.records.bundle import EvidenceLabel, FetchMode, ProvenanceBundle
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


SCORED_BUNDLE = ROOT / "fixtures" / "bundles" / "scored_bundle.json"


def test_candidate_list_run_matches_the_golden_bundle(
    layers: Layers, tmp_path: Path, transport: CassetteTransport, sources: pipeline.Sources
) -> None:
    """Against Track A's golden scored bundle once its scorer is importable, else the sample."""
    scorer = scoring_port.default_scorer()
    stand_in = isinstance(scorer, scoring_port.SampleBundleScorer)
    golden_path = scoring_port.SAMPLE_BUNDLE if stand_in else SCORED_BUNDLE
    sample = ProvenanceBundle.model_validate_json(golden_path.read_text())
    formulas = [c.composition for c in sample.candidates]
    inputs = _inputs(layers, tmp_path, formulas)
    bundle = pipeline.run(inputs, fetch=transport, sources=sources, scorer=scorer)
    assert transport.misses == []
    assert bundle.bundle_version == 2 and bundle.run.finished_at is not None
    assert [(c.rank, c.composition) for c in bundle.ranked()] == [
        (c.rank, c.composition) for c in sample.ranked()
    ]
    assert {c.composition for c in bundle.excluded()} == {"ThO2", "BeO"}
    assert [a.composition for a in bundle.anchors] == ["SiO2"] and bundle.anchors[0].out_of == 9
    assert bundle.run.partial is False and bundle.availability_events == []
    assert bundle.run.source_versions["materials_project"] == "2026.09.28"
    assert bundle.run.model_version is None and bundle.run.prompt_hash is None
    assert bundle.run.policy_version == pipeline.policy_version()
    if stand_in:
        assert bundle.run.note is not None and "Track A scorer not merged" in bundle.run.note
    else:
        assert bundle.run.note is None
        assert [a.would_rank for a in bundle.anchors] == [a.would_rank for a in sample.anchors]
        assert any(d.actor == "scorer" and d.step == "sensitivity" for d in bundle.decision_log)
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
    assert steps[:2] == ["start", "fetch"] and steps[-1] == "verify"
    assert steps.count("score") == 1 and "classify" in steps
    times = [d.at for d in bundle.decision_log]
    assert times == sorted(times)  # the log reads in the order things happened
    assert bundle.decision_log[0].detail["code_version"]
    assert len(bundle.missing_properties) == 8  # site list plus the profile item
    text = markdown.render_pi_summary(bundle, layers[1])
    assert "| 1= | Al2O3 |" in text  # tied at 1.000 (human test session, item 7)
    ProvenanceBundle.model_validate_json(bundle.model_dump_json())


def test_missing_sources_become_events_and_a_partial_run(
    layers: Layers, tmp_path: Path, transport: CassetteTransport, sources: pipeline.Sources
) -> None:
    def flaky(call: Call) -> RawResponse | None:
        if call.source.value == "openalex":
            return None
        return transport(call)

    # XeF2 is never recorded (no case and no oxide discovery reaches it)
    inputs = _inputs(layers, tmp_path, ["HfO2", "XeF2"])
    bundle = pipeline.run(
        inputs, fetch=flaky, sources=sources, scorer=scoring_port.default_scorer()
    )
    assert bundle.run.partial is True
    # offline (replay): never says the source lacks it (human test session, item 12)
    offline = "Not in the recorded data (offline mode); available with live fetching"
    assert bundle.run.partial_reasons == [f"XeF2: {offline}"]
    assert bundle.criteria.not_fetched == {"XeF2": offline}
    live = pipeline.run(
        dataclasses.replace(inputs, fetch_mode=FetchMode.LIVE),
        fetch=flaky,
        sources=sources,
        scorer=scoring_port.default_scorer(),
    )
    assert live.run.partial_reasons == ["XeF2: no Materials Project summary available"]
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
    assert bundle.run.prompt_hash is not None
    assert bundle.run.budgets_used["classify.tool_calls"] == 5.0
    assert bundle.run.budgets_used["rationale.tool_calls"] == 1.0
    assert bundle.run.budgets_limit["classify.tool_calls"] == 120.0
    assert "parse.tool_calls" not in bundle.run.budgets_limit
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


def test_at_most_five_abstracts_per_candidate_are_classified_in_search_order(
    layers: Layers, tmp_path: Path, transport: CassetteTransport, sources: pipeline.Sources
) -> None:
    """HfO2 has five recorded hits; a transport that doubles them shows the cap."""

    def doubled(call: Call) -> RawResponse | None:
        raw = transport(call)
        if raw is None or call.source.value != "openalex" or call.endpoint != "works":
            return raw
        body = json.loads(raw.body)
        extra = []
        for i, w in enumerate(body["results"]):
            copy = dict(w)
            copy["id"] = w["id"] + f"-dup{i}"
            extra.append(copy)
        body["results"] = body["results"] + extra
        return raw.model_copy(update={"body": json.dumps(body).encode()})

    inputs = _inputs(layers, tmp_path, ["HfO2"])
    inputs.prior_budgets = [Budget.from_core(layers[0], "parse")]
    bundle = pipeline.run(
        inputs, fetch=doubled, sources=sources, scorer=scoring_port.default_scorer()
    )
    hf = next(c for c in bundle.candidates if c.composition == "HfO2")
    assert hf.group.literature is not None and len(hf.group.literature.hits) == 10
    classified = [e.openalex_id for e in bundle.evidence if e.composition == "HfO2"]
    assert classified == [h.openalex_id for h in hf.group.literature.hits[:5]]
    assert layers[0].max_abstracts_per_candidate == 5
    assert "parse.tool_calls" in bundle.run.budgets_limit


def test_evidence_all_or_none_drops_evidence_when_shown_rows_are_mixed() -> None:
    """Track H sweep: B2O3 led the brief's example on a stale cached label while HfO2, ZrO2,
    Y2O3 went unread; when shown rows are mixed, evidence leaves every row."""
    from materials_triage.agent.pipeline import evidence_gaps
    from materials_triage.records.bundle import EvidenceHit, EvidenceLabel

    def hit(comp: str, label: EvidenceLabel, verified: bool) -> EvidenceHit:
        return EvidenceHit.model_construct(composition=comp, label=label, verified=verified)

    labelled = [hit("B2O3", EvidenceLabel.DIELECTRIC_CHARACTERIZED, True)]
    unread = [hit("HfO2", EvidenceLabel.UNCLASSIFIED, False)]
    mixed = {"B2O3": labelled, "HfO2": unread}
    assert evidence_gaps(mixed, ["B2O3", "HfO2"], []) == ["HfO2"]
    # every shown row labelled: evidence counts
    assert evidence_gaps({"B2O3": labelled}, ["B2O3"], []) is None
    # none labelled (no model): already uniform, no rule needed
    assert evidence_gaps({"HfO2": unread}, ["HfO2"], []) is None
    # a row with no abstracts is not a gap
    assert evidence_gaps({"B2O3": labelled, "ZrO2": []}, ["B2O3", "ZrO2"], []) is None
    # an anchor counts like a shown row
    assert evidence_gaps(mixed, ["B2O3"], ["HfO2"]) == ["HfO2"]


def test_the_evidence_note_names_only_rows_on_the_final_page() -> None:
    """The brief's example named SO3 (later excluded) and Li2O (12th) as unread shown rows."""
    from materials_triage.agent.pipeline import unread_rows
    from materials_triage.records.bundle import EvidenceHit, EvidenceLabel

    def hit(comp: str, label: EvidenceLabel) -> EvidenceHit:
        return EvidenceHit.model_construct(composition=comp, label=label, verified=False)

    evidence = {
        "SO3": [hit("SO3", EvidenceLabel.UNCLASSIFIED)],
        "HfO2": [hit("HfO2", EvidenceLabel.UNCLASSIFIED)],
        "Al2O3": [hit("Al2O3", EvidenceLabel.DIELECTRIC_CHARACTERIZED)],
    }
    assert unread_rows(evidence, ["Al2O3", "HfO2", "ZrO2"]) == ["HfO2"]


def test_the_rationale_budget_clock_starts_with_the_rationale_step(
    layers: Layers,
    tmp_path: Path,
    transport: CassetteTransport,
    sources: pipeline.Sources,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live A1 on Haiku: discovery and classification took 147 s, and the rationale's 120 s
    budget, timed from run start, had expired before the step began; no rationale call was
    made. A slow classify phase (250 s on a fake clock, inside the 300 s classify budget) must
    leave the rationale its own 120 s."""
    now = [0.0]

    def clock() -> float:
        return now[0]

    real_from_core = Budget.from_core

    def from_core(core: cs.CoreConfig, step: str) -> Budget:
        b = real_from_core(core, step)
        b.clock = clock
        b.started = clock()
        return b

    monkeypatch.setattr(pipeline.Budget, "from_core", staticmethod(from_core))
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
                                {"slot": "candidate:HfO2:one_line", "text": "{formula:HfO2} leads."}
                            ]
                        },
                    }
                ],
                "usage": {"input_tokens": 50, "output_tokens": 20},
            }
        ],
        model="fake-haiku",
    )

    class SlowClassify:
        model, provider = fake.model, fake.provider

        def complete(self, **kw):  # type: ignore[no-untyped-def]
            if kw["tools"][0].name == "classify_abstract":
                now[0] += 50.0  # five abstracts: 250 s
            return fake.complete(**kw)

    bundle = pipeline.run(
        inputs,
        fetch=transport,
        sources=sources,
        scorer=scoring_port.default_scorer(),
        llm=SlowClassify(),  # type: ignore[arg-type]
    )
    assert bundle.run.budgets_used["classify.seconds"] == 250.0
    assert bundle.run.budgets_used["rationale.tool_calls"] == 1.0
    assert bundle.run.budgets_used["rationale.seconds"] < 120.0
    assert not any(r.startswith("rationale not written") for r in bundle.run.partial_reasons)
    assert bundle.rationale["candidate:HfO2:one_line"].text == "{formula:HfO2} leads."
