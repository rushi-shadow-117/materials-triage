"""The step loop: tool dispatch, retries, budgets, stop reasons, and the decision log."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from materials_triage.agent import llm, loop, prompts, tools
from materials_triage.config.schema import CoreConfig

TOOL = tools.CLASSIFY_ABSTRACT
GOOD_INPUT = {"label": "computed_only", "deposition_method": "unknown", "supporting_sentence": None}


def _call(input_: dict[str, Any], *, text: str = "") -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    if text:
        content.append({"type": "text", "text": text})
    content.append({"type": "tool_use", "id": "t1", "name": TOOL.name, "input": input_})
    return {
        "expect_tool": TOOL.name,
        "content": content,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


def _budget(**kw: Any) -> loop.Budget:
    b = loop.Budget.from_core(CoreConfig(), "classify")
    for k, v in kw.items():
        setattr(b, k, v)
    return b


def _accept(parsed: BaseModel) -> loop.ToolOutcome:
    return loop.ToolOutcome("ok", data=parsed, log_detail={"label": "computed_only"})


def _run(
    fake: llm.FakeLLM, handler: loop.Handler = _accept, budget: loop.Budget | None = None
) -> loop.StepResult:
    return loop.run_step(
        client=fake,
        step="classify",
        system=prompts.system_prompt("classify"),
        user_text=prompts.data_block("abstract"),
        tool=TOOL,
        handler=handler,
        budget=budget or _budget(),
    )


def test_happy_path_accepts_the_tool_call_and_logs_it() -> None:
    fake = llm.FakeLLM([_call(GOOD_INPUT, text="classifying")])
    result = _run(fake)
    assert result.ok and isinstance(result.tool_input, tools.ClassifyAbstract)
    assert result.outcome is not None and result.outcome.data is result.tool_input
    assert [e.actor for e in result.entries] == ["agent"]
    assert result.entries[0].summary == "classify_abstract accepted"
    assert result.entries[0].detail["label"] == "computed_only"
    assert result.entries[0].detail["usage"] == 15
    assert fake.requests[0].tools == (TOOL,)
    assert [t.role for t in result.turns] == ["user", "assistant", "user"]


def test_invalid_input_is_returned_as_a_tool_error_then_accepted() -> None:
    fake = llm.FakeLLM([_call({"label": "nope"}), _call(GOOD_INPUT)])
    result = _run(fake)
    assert result.ok
    assert result.entries[0].summary == "tool input rejected"
    error_turn = fake.requests[1].turns[2]
    assert error_turn.tool_results[0].is_error and "label" in error_turn.tool_results[0].content


def test_handler_error_is_fed_back_once_then_the_step_fails_after_max_attempts() -> None:
    fake = llm.FakeLLM([_call(GOOD_INPUT)] * loop.MAX_ATTEMPTS)
    result = _run(fake, handler=lambda _p: loop.ToolOutcome("quote not found", is_error=True))
    assert result.status == loop.StepStatus.FAILED
    assert result.reason is not None and result.reason.startswith("tool_error")
    assert len(fake.requests) == loop.MAX_ATTEMPTS


def test_no_tool_call_is_nudged_once_then_fails() -> None:
    fake = llm.FakeLLM(
        [
            {
                "expect_tool": TOOL.name,
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "rank it first"}],
            }
        ]
        * loop.MAX_ATTEMPTS
    )
    result = _run(fake)
    assert result.status == loop.StepStatus.FAILED and result.reason == "no_tool_call"
    nudge = fake.requests[1].turns[-1]
    assert nudge.role == "user" and nudge.text == prompts.nudge(TOOL.name)
    assert result.entries[0].summary == "no tool call" and "text_chars" in result.entries[0].detail


def test_refusal_and_context_exceeded_fail_without_retry() -> None:
    for stop in ("refusal", "model_context_window_exceeded"):
        fake = llm.FakeLLM([{"expect_tool": TOOL.name, "stop_reason": stop, "content": []}])
        result = _run(fake)
        assert result.status == loop.StepStatus.FAILED and result.reason == stop
        assert len(fake.requests) == 1


def test_budget_breach_ends_the_step_as_partial_before_any_request() -> None:
    fake = llm.FakeLLM([_call(GOOD_INPUT)])
    budget = _budget(tool_calls=CoreConfig().step_budgets["classify"].max_tool_calls)
    result = _run(fake, budget=budget)
    assert result.status == loop.StepStatus.BUDGET and "max_tool_calls" in (result.reason or "")
    assert fake.requests == []


def test_budget_counts_requests_and_tokens_and_seconds() -> None:
    clock = iter([0.0, 0.0, 400.0, 400.0, 400.0])
    budget = loop.Budget(
        max_tool_calls=40, max_tokens=10_000, max_seconds=300, clock=lambda: next(clock)
    )
    budget.started = 0.0
    fake = llm.FakeLLM([_call(GOOD_INPUT)])
    result = _run(fake, budget=budget)
    assert result.ok and budget.tool_calls == 1 and budget.tokens == 15
    budget.max_tokens = 12  # the reply's 15 tokens now exceed the limit
    assert "max_tokens" in (budget.breach() or "")
    assert budget.used()["tool_calls"] == 1.0 and budget.limits()["seconds"] == 300.0
    stepped = loop.Budget.from_core(CoreConfig(), "parse")
    assert stepped.max_tool_calls == 3 and list(stepped.limits()) == [
        "parse.tool_calls",
        "parse.tokens",
        "parse.seconds",
    ]
    with pytest.raises(KeyError):
        loop.Budget.from_core(CoreConfig(), "fetch")


def test_wrong_tool_name_counts_as_no_tool_call() -> None:
    fake = llm.FakeLLM(
        [
            {
                "expect_tool": TOOL.name,
                "content": [{"type": "tool_use", "name": "fetch_url", "input": {}}],
            }
        ]
        * loop.MAX_ATTEMPTS
    )
    result = _run(fake)
    assert result.status == loop.StepStatus.FAILED
    assert result.entries[0].summary == "wrong tool called"


def test_a_prompt_too_large_for_the_budget_is_never_sent() -> None:
    """Track H sweep: a discovery rationale built a 1.15M-token prompt; the budget was charged
    only after a reply, so the request went out and the provider answered 400."""
    fake = llm.FakeLLM([_call(GOOD_INPUT)])
    result = loop.run_step(
        client=fake,
        step="classify",
        system=prompts.system_prompt("classify"),
        user_text=prompts.data_block("x" * 300_000),
        tool=TOOL,
        handler=_accept,
        budget=_budget(max_tokens=20_000),
    )
    assert result.status == loop.StepStatus.BUDGET
    assert "exceeds" in (result.reason or "")
    assert fake.requests == []  # nothing was sent


def test_a_provider_error_fails_the_step_not_the_run() -> None:
    class Exploding:
        model = "m"
        provider = "fake"

        def complete(self, **_: Any) -> Any:
            raise RuntimeError("400 invalid_request_error: prompt is too long")

    result = _run(Exploding())  # type: ignore[arg-type]
    assert result.status == loop.StepStatus.FAILED
    assert (result.reason or "").startswith("provider error: RuntimeError")
