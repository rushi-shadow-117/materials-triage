"""Live-eval cost controls: estimates before any call, a per-case classify cap, and a suite
limit that stops cases from starting (owner rule, Track G). No API call is made here."""

from __future__ import annotations

from pathlib import Path

import pytest
from evals.cases import load_cases, select
from evals.execute import PipelineExecutor

from evals import costs
from materials_triage.agent.classifier import ClassifierCache
from materials_triage.cli.wiring import CassetteFetch

CASES = {c.id: c for c in load_cases()}


def test_estimates_refusals_candidate_lists_and_discovery(tmp_path: Path) -> None:
    kw = {"fetch": CassetteFetch(), "cache": ClassifierCache(tmp_path), "model": "m"}
    assert costs.estimate(CASES["F1"], anchors=[], **kw) == (1, 22)  # expected refusal
    expected, worst = costs.estimate(CASES["A2"], anchors=["SiO2"], **kw)
    assert expected == worst and 2 < expected <= 22  # parse + classify (capped) + rationale
    assert costs.estimate(CASES["A1"], anchors=["SiO2"], **kw) == (22, 22)  # discovery bound


def test_the_cap_is_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVAL_MAX_CLASSIFY_CALLS", "5")
    monkeypatch.setenv("EVAL_MAX_LIVE_CALLS", "9")
    assert costs.max_classify_calls() == 5 and costs.max_live_calls() == 9


def test_a_case_over_the_suite_limit_never_starts() -> None:
    ex = PipelineExecutor(llm="live", fetch_source="cassettes")
    ex.worst_calls["F4"] = costs.max_live_calls() + 1
    obs = ex.run(select(load_cases(), "F4")[0], 1)
    assert obs.bundle is None and ex._live is None  # no client was even built
    assert "case not started" in obs.errors[0]
