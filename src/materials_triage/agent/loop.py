"""One bounded conversation per step, with only that step's tool offered.

The model acts by calling the tool; the handler (code) validates the input, performs the
effect, and returns a result or an error the model sees once. Budgets are checked before
every request; a breach ends the step as partial with the reason. Every request appends a
decision-log entry. Nothing here knows what the tool does.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from materials_triage.config.schema import CoreConfig
from materials_triage.records.bundle import DecisionLogEntry

from . import prompts
from .llm import LLMClient, ToolCall, ToolResult, ToolSpec, Turn, Usage
from .llm_status import LLMUnavailableError
from .tools import ToolInputError, validate_input

MAX_ATTEMPTS = 3
DEFAULT_MAX_TOKENS = 4096


@dataclass
class Budget:
    """Run-wide limits from CoreConfig. `tool_calls` counts model requests, each of which
    is one chance to call a tool."""

    max_tool_calls: int
    max_tokens: int
    max_seconds: float
    step: str = ""
    tool_calls: int = 0
    tokens: int = 0
    started: float = field(default_factory=time.monotonic)
    clock: Callable[[], float] = time.monotonic

    @classmethod
    def from_core(cls, core: CoreConfig, step: str) -> Budget:
        """The step's own budget; an unknown step name is a programming error."""
        limits = core.step_budgets[step]
        return cls(limits.max_tool_calls, limits.max_tokens, float(limits.max_seconds), step=step)

    @property
    def seconds(self) -> float:
        return self.clock() - self.started

    def breach(self) -> str | None:
        if self.tool_calls >= self.max_tool_calls:
            return f"max_tool_calls ({self.max_tool_calls}) reached"
        if self.tokens >= self.max_tokens:
            return f"max_tokens ({self.max_tokens}) reached"
        if self.seconds >= self.max_seconds:
            return f"max_seconds ({self.max_seconds:g}) reached"
        return None

    def charge(self, usage: Usage) -> None:
        self.tool_calls += 1
        self.tokens += usage.total

    def _key(self, name: str) -> str:
        return f"{self.step}.{name}" if self.step else name

    def used(self) -> dict[str, float]:
        return {
            self._key("tool_calls"): float(self.tool_calls),
            self._key("tokens"): float(self.tokens),
            self._key("seconds"): round(self.seconds, 3),
        }

    def limits(self) -> dict[str, float]:
        return {
            self._key("tool_calls"): float(self.max_tool_calls),
            self._key("tokens"): float(self.max_tokens),
            self._key("seconds"): self.max_seconds,
        }


@dataclass(frozen=True)
class ToolOutcome:
    """What a handler returns: the text the model sees, whether it was an error, the
    validated effect, and what the decision log may record (never unverified text)."""

    content: str
    is_error: bool = False
    data: Any = None
    log_detail: dict[str, Any] = field(default_factory=dict)


Handler = Callable[[BaseModel], ToolOutcome]


class StepStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"
    BUDGET = "budget"


@dataclass
class StepResult:
    status: StepStatus
    reason: str | None = None
    tool_input: BaseModel | None = None
    outcome: ToolOutcome | None = None
    entries: list[DecisionLogEntry] = field(default_factory=list)
    turns: list[Turn] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == StepStatus.OK


def _entry(step: str, summary: str, detail: dict[str, Any]) -> DecisionLogEntry:
    return DecisionLogEntry(
        at=datetime.now(UTC), actor="agent", step=step, summary=summary, detail=detail
    )


def estimated_prompt_tokens(system: str, turns: list[Turn]) -> int:
    """A deliberately high estimate of a request's input tokens (one per 3 characters), used
    to refuse a request that cannot fit before it is sent."""
    chars = len(system)
    for t in turns:
        chars += len(t.text or "")
        for r in t.tool_results or ():
            chars += len(r.content)
        for c in t.tool_calls or ():
            chars += len(str(c.input))
    return chars // 3 + 1


def run_step(
    *,
    client: LLMClient,
    step: prompts.Step,
    system: str,
    user_text: str,
    tool: ToolSpec,
    handler: Handler,
    budget: Budget,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> StepResult:
    turns: list[Turn] = [Turn("user", user_text)]
    entries: list[DecisionLogEntry] = []
    last_reason = "no_tool_call"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        breach = budget.breach()
        if breach is not None:
            entries.append(_entry(step, f"budget: {breach}", {"attempt": attempt}))
            return StepResult(StepStatus.BUDGET, breach, entries=entries, turns=turns)
        estimate = estimated_prompt_tokens(system, turns)
        remaining = budget.max_tokens - budget.tokens
        if estimate > remaining:
            # checked before sending: a request that cannot fit the step's token budget is
            # never made (the budget is otherwise charged only after a reply)
            reason = f"prompt of about {estimate} tokens exceeds the {remaining} left in the budget"
            entries.append(_entry(step, f"budget: {reason}", {"attempt": attempt}))
            return StepResult(StepStatus.BUDGET, reason, entries=entries, turns=turns)
        try:
            response = client.complete(
                system=system, turns=turns, tools=[tool], max_tokens=max_tokens
            )
        except LLMUnavailableError as e:
            entries.append(_entry(step, "model unavailable", {"attempt": attempt, "note": str(e)}))
            return StepResult(StepStatus.FAILED, "llm_unavailable", entries=entries, turns=turns)
        except Exception as e:  # noqa: BLE001 - any other provider error fails the step only
            note = f"provider error: {type(e).__name__}: {str(e)[:300]}"
            entries.append(_entry(step, note, {"attempt": attempt}))
            return StepResult(StepStatus.FAILED, note, entries=entries, turns=turns)
        budget.charge(response.usage)
        detail: dict[str, Any] = {
            "attempt": attempt,
            "stop_reason": response.stop_reason,
            "usage": response.usage.total,
            "model": response.model,
        }
        if response.stop_reason in ("refusal", "model_context_window_exceeded", "other"):
            entries.append(_entry(step, f"stopped: {response.stop_reason}", detail))
            return StepResult(
                StepStatus.FAILED, str(response.stop_reason), entries=entries, turns=turns
            )
        call: ToolCall | None = next((c for c in response.tool_calls if c.name == tool.name), None)
        if call is None:
            summary = "no tool call" if not response.tool_calls else "wrong tool called"
            entries.append(_entry(step, summary, {**detail, "text_chars": len(response.text)}))
            turns.append(Turn("assistant", response.text or "(no text)"))
            turns.append(Turn("user", prompts.nudge(tool.name)))
            last_reason = "no_tool_call"
            continue
        turns.append(Turn("assistant", response.text or None, tool_calls=(call,)))
        try:
            parsed = validate_input(tool.name, call.input)
        except ToolInputError as e:
            entries.append(_entry(step, "tool input rejected", {**detail, "error": str(e)}))
            turns.append(Turn("user", tool_results=(ToolResult(call.id, str(e), is_error=True),)))
            last_reason = f"invalid_input: {e}"
            continue
        outcome = handler(parsed)
        turns.append(
            Turn("user", tool_results=(ToolResult(call.id, outcome.content, outcome.is_error),))
        )
        if outcome.is_error:
            entries.append(
                _entry(
                    step,
                    "tool result error",
                    {**detail, "error": outcome.content, **outcome.log_detail},
                )
            )
            last_reason = f"tool_error: {outcome.content}"
            continue
        entries.append(_entry(step, f"{tool.name} accepted", {**detail, **outcome.log_detail}))
        return StepResult(StepStatus.OK, None, parsed, outcome, entries, turns)
    entries.append(_entry(step, f"failed after {MAX_ATTEMPTS} attempts", {"reason": last_reason}))
    return StepResult(StepStatus.FAILED, last_reason, entries=entries, turns=turns)
