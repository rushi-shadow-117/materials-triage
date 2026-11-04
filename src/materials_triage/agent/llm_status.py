"""Whether the configured model can be called, for this process.

A missing key, a rejected key, or an exhausted credit balance does not fail a run: the client
is dropped, every step takes its no-model path, and the app shows a banner. The status is set
once and kept until restart, so a bad key costs one rejected request, not one per abstract.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any, Literal

import anthropic

from materials_triage.agent.llm import LLMClient, LLMResponse, ToolSpec, Turn

LLMStatus = Literal["ok", "none", "missing_key", "invalid_key", "no_credit"]

NOTES: dict[LLMStatus, str] = {
    "ok": "",
    "none": "No model configured (LLM_PROVIDER=none).",
    "missing_key": "No model: the provider key is not set.",
    "invalid_key": "No model: the provider rejected the key.",
    "no_credit": "No model: the provider account has no credit.",
}
BANNER_SUFFIX = " The request box is off; fill the criteria form by hand."


@dataclass
class _State:
    status: LLMStatus = "ok"
    detail: str = ""


_state = _State()
_lock = Lock()


def current() -> LLMStatus:
    return _state.status


def note() -> str:
    """The banner sentence, empty while the model is available."""
    if _state.status == "ok":
        return ""
    return NOTES[_state.status] + BANNER_SUFFIX


def available() -> bool:
    return _state.status == "ok"


def set_status(status: LLMStatus, detail: str = "") -> None:
    with _lock:
        # a configured "none" is a choice, not a failure; a later failure cannot undo it
        if _state.status == "none" and status != "ok":
            return
        _state.status = status
        _state.detail = detail


def reset() -> None:
    """Process start (and tests)."""
    with _lock:
        _state.status = "ok"
        _state.detail = ""


class LLMUnavailableError(RuntimeError):
    """The model cannot be called in this process; the step takes its no-model path."""


def classify_error(e: Exception) -> LLMStatus | None:
    """Which unavailable status an SDK error means, or None for an ordinary failure."""
    if isinstance(e, anthropic.AuthenticationError):
        return "invalid_key"
    if isinstance(e, anthropic.APIStatusError):
        message = str(getattr(e, "message", "") or e).lower()
        if "credit balance" in message or "billing" in message:
            return "no_credit"
        if isinstance(e, anthropic.PermissionDeniedError):
            return "invalid_key"
    return None


class GuardedClient:
    """Wraps a provider client. An auth or credit error sets the status and raises
    LLMUnavailableError; once unavailable, every call raises without a request."""

    def __init__(self, inner: LLMClient) -> None:
        self._inner = inner
        self.model = inner.model
        self.provider = inner.provider

    def complete(
        self, *, system: str, turns: list[Turn], tools: list[ToolSpec], max_tokens: int
    ) -> LLMResponse:
        if not available():
            raise LLMUnavailableError(note())
        try:
            return self._inner.complete(
                system=system, turns=turns, tools=tools, max_tokens=max_tokens
            )
        except Exception as e:
            status = classify_error(e)
            if status is None:
                raise
            set_status(status, type(e).__name__)
            raise LLMUnavailableError(note()) from e


def describe() -> dict[str, Any]:
    return {"llm_status": _state.status, "llm_note": note()}
