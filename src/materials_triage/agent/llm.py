"""The LLM boundary. One provider-neutral request and response shape for every provider.

The loop (loop.py) never sees provider objects. A provider adapter turns `Turn` and `ToolSpec`
into its wire format and the reply back into `LLMResponse`. `FakeLLM` replays scripted
responses so every loop test runs without a network and asserts on the exact request sent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

import anthropic
import httpx
from anthropic.types import MessageParam, ToolParam

from materials_triage.adapters import egress
from materials_triage.settings import MissingSettingError, Settings

StopReason = Literal[
    "end_turn", "tool_use", "max_tokens", "refusal", "model_context_window_exceeded", "other"
]
KNOWN_STOPS: frozenset[str] = frozenset(
    {"end_turn", "tool_use", "max_tokens", "refusal", "model_context_window_exceeded"}
)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]

    def neutral(self) -> dict[str, Any]:
        """Provider-independent form, used for the prompt hash."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass(frozen=True)
class Turn:
    role: Literal["user", "assistant"]
    text: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()  # assistant turns
    tool_results: tuple[ToolResult, ...] = ()  # user turns


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

    @property
    def total(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_creation_tokens
        )


@dataclass(frozen=True)
class LLMResponse:
    text: str
    tool_calls: tuple[ToolCall, ...]
    stop_reason: StopReason
    usage: Usage
    model: str | None = None


@dataclass(frozen=True)
class Request:
    """What was sent, kept so tests can compare prompts byte for byte."""

    system: str
    turns: tuple[Turn, ...]
    tools: tuple[ToolSpec, ...]
    max_tokens: int


class LLMClient(Protocol):
    model: str
    provider: str

    def complete(
        self, *, system: str, turns: list[Turn], tools: list[ToolSpec], max_tokens: int
    ) -> LLMResponse: ...


# ------------------------------------------------------------------------ Anthropic / Bedrock


def _anthropic_messages(turns: list[Turn]) -> list[MessageParam]:
    out: list[MessageParam] = []
    for t in turns:
        blocks: list[Any] = []
        if t.role == "assistant":
            if t.text:
                blocks.append({"type": "text", "text": t.text})
            for c in t.tool_calls:
                blocks.append({"type": "tool_use", "id": c.id, "name": c.name, "input": c.input})
        else:
            for r in t.tool_results:
                blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": r.tool_call_id,
                        "content": r.content,
                        "is_error": r.is_error,
                    }
                )
            if t.text:
                blocks.append({"type": "text", "text": t.text})
        if t.role == "assistant":
            out.append({"role": "assistant", "content": blocks})
        else:
            out.append({"role": "user", "content": blocks})
    return out


def _anthropic_tools(tools: list[ToolSpec]) -> list[ToolParam]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.input_schema,
            "strict": True,
        }
        for t in tools
    ]


def parse_anthropic_message(message: anthropic.types.Message) -> LLMResponse:
    text_parts: list[str] = []
    calls: list[ToolCall] = []
    for block in message.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            raw = block.input
            calls.append(
                ToolCall(id=block.id, name=block.name, input=raw if isinstance(raw, dict) else {})
            )
    stop: StopReason = "other"
    if message.stop_reason in KNOWN_STOPS:
        stop = message.stop_reason  # type: ignore[assignment]
    u = message.usage
    return LLMResponse(
        text="".join(text_parts),
        tool_calls=tuple(calls),
        stop_reason=stop,
        usage=Usage(
            input_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            cache_read_tokens=u.cache_read_input_tokens or 0,
            cache_creation_tokens=u.cache_creation_input_tokens or 0,
        ),
        model=message.model,
    )


class AnthropicClient:
    """Anthropic API or Bedrock through the SDK's Messages surface. No thinking parameter,
    no forced tool choice (rejected by the pinned model); every tool is strict."""

    def __init__(
        self,
        client: anthropic.Anthropic | anthropic.AnthropicBedrockMantle,
        *,
        model: str,
        provider: str,
    ) -> None:
        self._client = client
        self.model = model
        self.provider = provider

    def complete(
        self, *, system: str, turns: list[Turn], tools: list[ToolSpec], max_tokens: int
    ) -> LLMResponse:
        message = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=_anthropic_messages(turns),
            tools=_anthropic_tools(tools),
        )
        return parse_anthropic_message(message)


# ------------------------------------------------------------------------ OpenAI-compatible

OPENAI_STOP: dict[str, StopReason] = {
    "stop": "end_turn",
    "tool_calls": "tool_use",
    "function_call": "tool_use",
    "length": "max_tokens",
    "content_filter": "refusal",
}


def _openai_messages(system: str, turns: list[Turn]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for t in turns:
        if t.role == "assistant":
            msg: dict[str, Any] = {"role": "assistant", "content": t.text or ""}
            if t.tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {"name": c.name, "arguments": json.dumps(c.input)},
                    }
                    for c in t.tool_calls
                ]
            out.append(msg)
        else:
            for r in t.tool_results:
                out.append({"role": "tool", "tool_call_id": r.tool_call_id, "content": r.content})
            if t.text:
                out.append({"role": "user", "content": t.text})
    return out


def _openai_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema,
                "strict": True,
            },
        }
        for t in tools
    ]


def parse_openai_body(body: dict[str, Any]) -> LLMResponse:
    choice = body["choices"][0]
    msg = choice.get("message") or {}
    calls: list[ToolCall] = []
    for c in msg.get("tool_calls") or []:
        fn = c.get("function") or {}
        args = fn.get("arguments") or "{}"
        parsed = json.loads(args) if isinstance(args, str) else args
        calls.append(
            ToolCall(
                id=str(c.get("id")),
                name=str(fn.get("name")),
                input=parsed if isinstance(parsed, dict) else {},
            )
        )
    usage = body.get("usage") or {}
    return LLMResponse(
        text=msg.get("content") or "",
        tool_calls=tuple(calls),
        stop_reason=OPENAI_STOP.get(str(choice.get("finish_reason")), "other"),
        usage=Usage(
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
        ),
        model=body.get("model"),
    )


class OpenAICompatibleClient:
    """Chat-completions endpoint of a self-hosted or third-party server. Base URL from
    settings; bearer token optional. Only the chat/completions path is used."""

    provider = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = client or httpx.Client(
            base_url=base_url,
            headers=headers,
            timeout=120.0,
            event_hooks={"request": [egress.request_hook({egress.host_of(base_url) or ""})]},
        )
        self.model = model

    def complete(
        self, *, system: str, turns: list[Turn], tools: list[ToolSpec], max_tokens: int
    ) -> LLMResponse:
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": _openai_messages(system, turns),
            "tools": _openai_tools(tools),
        }
        resp = self._client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, dict):
            raise ValueError("unexpected chat/completions body")
        return parse_openai_body(body)


# ------------------------------------------------------------------------ fake


class FakeLLMExhaustedError(RuntimeError):
    pass


class FakeLLM:
    """Replays a scripted queue. Each entry: {"expect_tool": name | null, "stop_reason": ...,
    "content": [{"type": "text" | "tool_use", ...}], "usage": {...}}. Records every request."""

    provider = "fake"

    def __init__(self, script: list[dict[str, Any]], *, model: str = "fake-model") -> None:
        self._queue = list(script)
        self.model = model
        self.requests: list[Request] = []

    @classmethod
    def from_file(cls, path: Path, *, model: str = "fake-model") -> FakeLLM:
        data = json.loads(path.read_text())
        if not isinstance(data, list):
            raise ValueError(f"{path} must hold a list of scripted responses")
        return cls(data, model=model)

    def complete(
        self, *, system: str, turns: list[Turn], tools: list[ToolSpec], max_tokens: int
    ) -> LLMResponse:
        self.requests.append(Request(system, tuple(turns), tuple(tools), max_tokens))
        if not self._queue:
            raise FakeLLMExhaustedError("scripted responses exhausted")
        entry = self._queue.pop(0)
        expect = entry.get("expect_tool")
        offered = [t.name for t in tools]
        if expect is not None and offered != [expect]:
            raise AssertionError(f"script expected tool {expect!r} offered alone, got {offered}")
        text_parts: list[str] = []
        calls: list[ToolCall] = []
        for i, block in enumerate(entry.get("content", [])):
            if block["type"] == "text":
                text_parts.append(block["text"])
            elif block["type"] == "tool_use":
                calls.append(
                    ToolCall(
                        id=block.get("id", f"fake_{len(self.requests)}_{i}"),
                        name=block["name"],
                        input=dict(block.get("input", {})),
                    )
                )
        usage = entry.get("usage", {})
        return LLMResponse(
            text="".join(text_parts),
            tool_calls=tuple(calls),
            stop_reason=entry.get("stop_reason", "tool_use" if calls else "end_turn"),
            usage=Usage(
                input_tokens=int(usage.get("input_tokens", 0)),
                output_tokens=int(usage.get("output_tokens", 0)),
                cache_read_tokens=int(usage.get("cache_read_tokens", 0)),
                cache_creation_tokens=int(usage.get("cache_creation_tokens", 0)),
            ),
            model=self.model,
        )


# ------------------------------------------------------------------------ factory


def anthropic_sdk(settings: Settings) -> anthropic.Anthropic:
    """An Anthropic SDK client keyed from settings (.env), whose HTTP client refuses every
    host but its own endpoint (adapters/egress.py). Shared by the provider client and the
    eval judge."""
    allowed: set[str] = set()
    guarded = anthropic.DefaultHttpxClient(event_hooks={"request": [egress.request_hook(allowed)]})
    sdk = anthropic.Anthropic(api_key=settings.require("anthropic_api_key"), http_client=guarded)
    allowed.add(egress.host_of(sdk.base_url) or "")
    return sdk


def make_client(settings: Settings) -> LLMClient | None:
    """Build the configured provider's client, or None for provider "none"."""
    provider = settings.llm_provider
    if provider == "none":
        return None
    # Egress: the SDK's HTTP client refuses any host but the provider's own endpoint, which is
    # read from the built client (adapters/egress.py).
    allowed: set[str] = set()
    guarded = anthropic.DefaultHttpxClient(event_hooks={"request": [egress.request_hook(allowed)]})
    if provider == "anthropic":
        return AnthropicClient(
            anthropic_sdk(settings), model=settings.llm_model, provider="anthropic"
        )
    if provider == "bedrock":
        if settings.aws_region is None:
            raise MissingSettingError("AWS_REGION")
        model = settings.llm_model
        if not model.startswith("anthropic."):
            model = f"anthropic.{model}"
        bedrock = anthropic.AnthropicBedrockMantle(
            aws_region=settings.aws_region, http_client=guarded
        )
        allowed.add(egress.host_of(bedrock.base_url) or "")
        return AnthropicClient(bedrock, model=model, provider="bedrock")
    if settings.llm_base_url is None:
        raise MissingSettingError("LLM_BASE_URL")
    key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else None
    return OpenAICompatibleClient(
        base_url=settings.llm_base_url, model=settings.llm_model, api_key=key
    )
