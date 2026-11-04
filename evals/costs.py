"""Cost controls for live-model eval runs (owner rule, Track G).

Before a live run the harness prints each case's expected and worst-case number of API calls
and refuses to start when the expected total exceeds `EVAL_MAX_LIVE_CALLS` (default 30).
During the run every request is counted (`CountingClient`); once the suite total reaches the
limit, no further case starts. Each case's classify step is capped at
`EVAL_MAX_CLASSIFY_CALLS` (default 20): a case over the cap is marked partial, never
extended. The scripted model is free and is not capped.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from evals.schema import Case
from materials_triage.adapters import openalex
from materials_triage.adapters.base import RawResponse
from materials_triage.agent import classifier, prompts
from materials_triage.agent.llm import LLMClient, LLMResponse, ToolSpec, Turn
from materials_triage.agent.parse import split_candidates

DEFAULT_MAX_CLASSIFY = 20
DEFAULT_MAX_LIVE = 30
ABSTRACTS_PER_CANDIDATE = 5  # CoreConfig.max_abstracts_per_candidate


def max_classify_calls() -> int:
    return int(os.environ.get("EVAL_MAX_CLASSIFY_CALLS", DEFAULT_MAX_CLASSIFY))


def max_live_calls() -> int:
    return int(os.environ.get("EVAL_MAX_LIVE_CALLS", DEFAULT_MAX_LIVE))


@dataclass
class CountingClient:
    """Counts every request sent to the wrapped provider client."""

    inner: LLMClient
    calls: int = 0
    model: str = field(init=False)
    provider: str = field(init=False)

    def __post_init__(self) -> None:
        self.model = self.inner.model
        self.provider = self.inner.provider

    def complete(
        self, *, system: str, turns: list[Turn], tools: list[ToolSpec], max_tokens: int
    ) -> LLMResponse:
        self.calls += 1
        return self.inner.complete(system=system, turns=turns, tools=tools, max_tokens=max_tokens)


def _expects_no_run(case: Case) -> bool:
    names = {c.name for c in [*case.checks, *case.task_completion, *case.defenses]}
    return bool(names & {"refusal_present", "clarification_requested"})


def _uncached_hits(
    keys: list[str],
    fetch: Any,
    cache: classifier.ClassifierCache,
    model: str,
    injected: dict[str, RawResponse],
) -> int:
    prompt_hash = prompts.step_hash("classify")
    n = 0
    for key in keys:
        query = f"{key} thin film"
        raw = injected.get(key) or fetch(openalex.plan_search(query))
        if raw is None:
            continue
        hits = openalex.result(
            raw, None, composition=key, query=query, scope="title_and_abstract"
        ).hits
        usable = [h for h in hits if h.abstract_text and h.quote_verifiable]
        for h in usable[:ABSTRACTS_PER_CANDIDATE]:
            k = classifier.cache_key(classifier.abstract_sha(h), prompt_hash, model)
            if cache.get(k) is None:
                n += 1
    return n


def estimate(
    case: Case,
    *,
    fetch: Any,
    cache: classifier.ClassifierCache,
    model: str,
    anchors: list[str],
    injected: dict[str, RawResponse] | None = None,
    judge_live: bool = False,
) -> tuple[int, int]:
    """(expected, worst case) API calls for one live run of the case: parse, classify
    (uncached abstracts, capped), rationale, and judge items when the live judge is on."""
    cap = max_classify_calls()
    judge = len(case.judge) if judge_live else 0
    worst = 1 + cap + 1 + judge
    if _expects_no_run(case):
        return 1, worst
    if case.mode == "candidate_list":
        keys, _ = split_candidates(case.candidate_list)
        keys = list(dict.fromkeys([*keys, *anchors]))
        classify = min(cap, _uncached_hits(keys, fetch, cache, model, injected or {}))
        expected = 1 + classify + 1 + judge
        return expected, expected
    return worst, worst
