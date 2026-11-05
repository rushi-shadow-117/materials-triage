"""The LLM boundary: provider-neutral shapes, the fake, and the factory."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from anthropic.types import Message, TextBlock, ToolUseBlock
from anthropic.types import Usage as AUsage

from materials_triage.agent import llm
from materials_triage.settings import MissingSettingError, Settings

TOOL = llm.ToolSpec(
    name="classify_abstract",
    description="x",
    input_schema={"type": "object", "properties": {}, "additionalProperties": False},
)


def _settings(**kw: object) -> Settings:
    return Settings(_env_file=None, **kw)  # type: ignore[call-arg]


def test_settings_accept_the_llm_keys_from_an_env_file(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("ANTHROPIC_API_KEY=k\nLLM_PROVIDER=none\nLLM_MODEL=m\nLLM_BASE_URL=http://x\n")
    s = Settings(_env_file=env)  # type: ignore[call-arg]
    assert s.llm_provider == "none" and s.llm_model == "m" and s.llm_base_url == "http://x"
    assert s.anthropic_api_key is not None and "k" not in repr(s.anthropic_api_key)


def test_default_model_is_the_exact_pinned_id() -> None:
    # owner rule (Nov 4): never default to Opus
    assert _settings().llm_model == "claude-sonnet-5-5"


def test_usage_total_sums_all_four_counters() -> None:
    assert llm.Usage(1, 2, 3, 4).total == 10


def test_fake_replays_script_records_requests_and_checks_the_offered_tool() -> None:
    fake = llm.FakeLLM(
        [
            {
                "expect_tool": "classify_abstract",
                "content": [
                    {"type": "text", "text": "ok"},
                    {"type": "tool_use", "name": "classify_abstract", "input": {"a": 1}},
                ],
                "usage": {"input_tokens": 5, "output_tokens": 7},
            }
        ]
    )
    r = fake.complete(system="S", turns=[llm.Turn("user", "hi")], tools=[TOOL], max_tokens=10)
    assert r.stop_reason == "tool_use" and r.text == "ok"
    assert r.tool_calls[0].name == "classify_abstract" and r.tool_calls[0].input == {"a": 1}
    assert r.usage.total == 12
    assert fake.requests[0].system == "S" and fake.requests[0].tools == (TOOL,)
    with pytest.raises(llm.FakeLLMExhaustedError):
        fake.complete(system="S", turns=[], tools=[TOOL], max_tokens=10)


def test_fake_rejects_a_step_that_offers_the_wrong_tool() -> None:
    fake = llm.FakeLLM([{"expect_tool": "write_rationale", "content": []}])
    with pytest.raises(AssertionError):
        fake.complete(system="S", turns=[], tools=[TOOL], max_tokens=10)


def test_fake_from_file(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    p.write_text(json.dumps([{"expect_tool": None, "stop_reason": "end_turn", "content": []}]))
    r = llm.FakeLLM.from_file(p).complete(system="", turns=[], tools=[], max_tokens=1)
    assert r.stop_reason == "end_turn" and r.tool_calls == ()


def test_anthropic_message_conversion_round_trip() -> None:
    turns = [
        llm.Turn("user", "question"),
        llm.Turn("assistant", "thinking", tool_calls=(llm.ToolCall("t1", "parse_request", {}),)),
        llm.Turn("user", tool_results=(llm.ToolResult("t1", "bad", is_error=True),)),
    ]
    msgs = llm._anthropic_messages(turns)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    third = list(msgs[2]["content"])
    assert third[0]["type"] == "tool_result" and third[0]["is_error"] is True  # type: ignore[index]
    tools = llm._anthropic_tools([TOOL])
    assert tools[0]["strict"] is True and tools[0]["name"] == "classify_abstract"


def test_anthropic_reply_is_parsed_into_the_neutral_shape() -> None:
    message = Message(
        id="msg_1",
        type="message",
        role="assistant",
        model="claude-opus-5-5",
        stop_reason="tool_use",
        stop_sequence=None,
        content=[
            TextBlock(type="text", text="calling"),
            ToolUseBlock(type="tool_use", id="toolu_1", name="classify_abstract", input={"k": 2}),
        ],
        usage=AUsage(
            input_tokens=10,
            output_tokens=3,
            cache_read_input_tokens=4,
            cache_creation_input_tokens=0,
        ),
    )
    r = llm.parse_anthropic_message(message)
    assert r.stop_reason == "tool_use" and r.text == "calling" and r.model == "claude-opus-5-5"
    assert r.tool_calls == (llm.ToolCall("toolu_1", "classify_abstract", {"k": 2}),)
    assert r.usage == llm.Usage(10, 3, 4, 0)


def test_openai_compatible_client_posts_chat_completions_and_parses_tool_calls() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "local-model",
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "classify_abstract",
                                        "arguments": '{"label": "computed_only"}',
                                    },
                                }
                            ],
                        },
                    }
                ],
                "usage": {"prompt_tokens": 8, "completion_tokens": 2},
            },
        )

    client = llm.OpenAICompatibleClient(
        base_url="http://llm.local/v1",
        model="local-model",
        api_key="tok",
        client=httpx.Client(
            base_url="http://llm.local/v1",
            headers={"Authorization": "Bearer tok"},
            transport=httpx.MockTransport(handler),
        ),
    )
    turns = [
        llm.Turn("assistant", "x", tool_calls=(llm.ToolCall("c0", "parse_request", {"a": 1}),)),
        llm.Turn("user", "more", tool_results=(llm.ToolResult("c0", "ok"),)),
    ]
    r = client.complete(system="SYS", turns=turns, tools=[TOOL], max_tokens=50)
    body = seen["body"]
    assert isinstance(body, dict)
    assert seen["path"] == "/v1/chat/completions" and seen["auth"] == "Bearer tok"
    assert body["messages"][0] == {"role": "system", "content": "SYS"}
    assert body["messages"][2]["role"] == "tool" and body["messages"][3]["role"] == "user"
    assert body["tools"][0]["function"]["strict"] is True
    assert r.stop_reason == "tool_use" and r.model == "local-model"
    expected = llm.ToolCall("call_1", "classify_abstract", {"label": "computed_only"})
    assert r.tool_calls == (expected,)
    assert r.usage.total == 10


def test_openai_finish_reasons_map_to_neutral_stop_reasons() -> None:
    cases = (("stop", "end_turn"), ("length", "max_tokens"), ("content_filter", "refusal"))
    for fin, stop in cases:
        body = {"choices": [{"finish_reason": fin, "message": {"content": "t"}}]}
        assert llm.parse_openai_body(body).stop_reason == stop


def test_factory_picks_the_provider_and_requires_its_settings() -> None:
    assert llm.make_client(_settings(llm_provider="none")) is None
    for provider in ("anthropic", "openai_compatible", "bedrock"):
        with pytest.raises(MissingSettingError):
            llm.make_client(_settings(llm_provider=provider))
    a = llm.make_client(_settings(llm_provider="anthropic", anthropic_api_key="k"))
    assert isinstance(a, llm.AnthropicClient) and a.provider == "anthropic"
    assert a.model == "claude-sonnet-5-5"
    o = llm.make_client(_settings(llm_provider="openai_compatible", llm_base_url="http://x/v1"))
    assert isinstance(o, llm.OpenAICompatibleClient)
    b = llm.make_client(_settings(llm_provider="bedrock", aws_region="us-east-1"))
    assert isinstance(b, llm.AnthropicClient) and b.model == "anthropic.claude-sonnet-5-5"
    assert b.provider == "bedrock"


def test_preset_providers_need_their_own_key_and_an_explicit_model() -> None:
    """Track H item 6: openai and gemini go through the OpenAI-compatible client with their
    own key variable; the Claude default model is refused for them."""
    with pytest.raises(MissingSettingError, match="OPENAI_API_KEY"):
        llm.make_client(_settings(llm_provider="openai", llm_model="some-model"))
    with pytest.raises(MissingSettingError, match="GEMINI_API_KEY"):
        llm.make_client(_settings(llm_provider="gemini", llm_model="some-model"))
    with pytest.raises(MissingSettingError, match="LLM_MODEL"):
        llm.make_client(_settings(llm_provider="openai", openai_api_key="k"))
    o = llm.make_client(_settings(llm_provider="openai", openai_api_key="k", llm_model="m"))
    assert isinstance(o, llm.OpenAICompatibleClient) and o.provider == "openai"
    assert str(o._client.base_url).startswith("https://api.openai.com/v1")
    g = llm.make_client(
        _settings(
            llm_provider="gemini", gemini_api_key="k", llm_model="m", llm_base_url="http://p/v1"
        )
    )
    assert isinstance(g, llm.OpenAICompatibleClient) and g.provider == "gemini"
    assert str(g._client.base_url).startswith("http://p/v1")  # LLM_BASE_URL overrides a preset


def test_http_status_errors_from_a_compatible_endpoint_set_the_model_status() -> None:
    from materials_triage.agent import llm_status

    def err(code: int, body: str = "") -> httpx.HTTPStatusError:
        req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        resp = httpx.Response(code, text=body, request=req)
        return httpx.HTTPStatusError("x", request=req, response=resp)

    assert llm_status.classify_error(err(401)) == "invalid_key"
    assert llm_status.classify_error(err(403)) == "invalid_key"
    assert llm_status.classify_error(err(402)) == "no_credit"
    assert llm_status.classify_error(err(429, '{"error": "insufficient_quota"}')) == "no_credit"
    assert llm_status.classify_error(err(429, "rate limited, retry")) is None
    assert llm_status.classify_error(err(500)) is None


def test_a_usage_limit_counts_as_no_credit() -> None:
    """Track H sweep: the account's spend limit answered every call with HTTP 400 "You have
    reached your specified API usage limits"; the app kept calling instead of showing the
    banner."""
    import anthropic

    from materials_triage.agent import llm_status

    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx.Response(400, request=req)
    err = anthropic.BadRequestError(
        "You have reached your specified API usage limits. You will regain access on 2026-12-01.",
        response=resp,
        body=None,
    )
    assert llm_status.classify_error(err) == "no_credit"
