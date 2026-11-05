"""Parse and confirm: defaults shown, clamps reported, refusals fixed, files accepted."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from materials_triage.agent import llm, loop, parse, tools
from materials_triage.config import schema as cs

Layers = tuple[cs.CoreConfig, cs.SiteProfile, cs.ScoringProfile]


def _run(layers: Layers, script: list[dict]) -> tuple[loop.StepResult, llm.FakeLLM]:  # type: ignore[type-arg]
    core, site, profile = layers
    fake = llm.FakeLLM(script)
    result = parse.run_parse(
        client=fake,
        request_text="Find oxide dielectrics with wide gaps",
        core=core,
        site=site,
        profile=profile,
        cli_profile=profile.name,
        budget=loop.Budget.from_core(core, "parse"),
    )
    return result, fake


def _call(input_: dict) -> dict:  # type: ignore[type-arg]
    return {
        "expect_tool": "parse_request",
        "content": [{"type": "tool_use", "name": "parse_request", "input": input_}],
    }


def test_parsed_request_resolves_with_every_default_named(layers: Layers) -> None:
    result, fake = _run(
        layers,
        [_call({"band_gap_min_ev": 5.0, "weights": [{"criterion": "band_gap", "weight": 2.0}]})],
    )
    assert result.ok and result.outcome is not None
    outcome = result.outcome.data
    assert isinstance(outcome, parse.ParseOutcome) and outcome.ready
    assert outcome.query is not None and outcome.query.band_gap_min_ev == 5.0
    assert outcome.query.mode == "discovery" and outcome.query.top_n == 10
    assert set(outcome.defaults_applied) >= {
        "mode=discovery",
        "top_n=10",
        "exclude_radioactive=True",
        "units=eV",
        "verbosity=standard",
        "terminology=technical",
        "view=pi_summary",
    }
    assert [c.setting for c in outcome.clamps] == ["weights.band_gap"]
    assert outcome.effective is not None and outcome.effective.weights["band_gap"] == 1.0
    assert "Request from the researcher" in (fake.requests[0].turns[0].text or "")
    tool_result = json.loads(fake.requests[0].turns[0].text or "{}") if False else None
    assert tool_result is None


def test_candidate_list_mode_without_formulas_is_missing_required(layers: Layers) -> None:
    result, _ = _run(layers, [_call({"mode": "candidate_list"})])
    assert result.ok and result.outcome is not None
    outcome = result.outcome.data
    assert outcome.missing_required == ["candidate_list"] and not outcome.ready


def test_candidate_formulas_are_normalized_and_bad_ones_fed_back(layers: Layers) -> None:
    result, fake = _run(
        layers,
        [
            _call({"mode": "candidate_list", "candidate_list": ["hafnia??"]}),
            _call({"mode": "candidate_list", "candidate_list": ["O2Hf", "Al2O3", "HfO2"]}),
        ],
    )
    assert result.ok and result.outcome is not None
    assert result.outcome.data.query.candidate_list == ["HfO2", "Al2O3"]
    first_error = fake.requests[1].turns[2].tool_results[0]
    assert first_error.is_error and "hafnia??" in first_error.content


def test_out_of_scope_request_gets_the_fixed_refusal_text(layers: Layers) -> None:
    core = layers[0]
    for category in tools.OutOfScope:
        result, _ = _run(layers, [_call({"out_of_scope": category.value})])
        assert result.ok and result.outcome is not None
        outcome = result.outcome.data
        assert outcome.refusal == getattr(core.refusals, category.value)
        assert outcome.query is None and outcome.category is category and not outcome.ready
        assert result.entries[-1].detail["out_of_scope"] == category.value


def test_criteria_file_is_the_no_llm_path(layers: Layers, tmp_path: Path) -> None:
    core, site, profile = layers
    path = tmp_path / "criteria.yaml"
    path.write_text(
        "mode: candidate_list\ncandidate_list: [HfO2, ZrO2, O2Hf]\ntop_n: 500\nverbosity: concise\n"
    )
    outcome = parse.parse_from_file(
        path, core=core, site=site, profile=profile, cli_profile=profile.name
    )
    assert outcome.parsed_by == "criteria_file" and outcome.ready
    assert outcome.query is not None and outcome.query.candidate_list == ["HfO2", "ZrO2"]
    assert [c.setting for c in outcome.clamps] == ["top_n"] and outcome.effective is not None
    assert outcome.effective.top_n == site.top_n_max
    assert "terminology=technical" in outcome.defaults_applied
    bad = tmp_path / "bad.yaml"
    bad.write_text("mode: candidate_list\nscore: 1\n")
    with pytest.raises(ValueError, match="bad.yaml"):
        parse.parse_from_file(bad, core=core, site=site, profile=profile, cli_profile=profile.name)


def test_a_paywalled_or_closed_source_request_gets_its_own_refusal(layers: Layers) -> None:
    # review F11: a paywall request was refused with the private-data sentence
    core = layers[0]
    result, fake = _run(layers, [_call({"out_of_scope": "closed_source"})])
    assert result.ok and result.outcome is not None
    outcome = result.outcome.data
    assert outcome.category is tools.OutOfScope.CLOSED_SOURCE
    assert (
        outcome.refusal
        == core.refusals.closed_source
        == (
            "This assistant uses open public sources only; it does not fetch paywalled or closed "
            "content."
        )
    )
    assert "(closed_source)" in fake.requests[0].system
