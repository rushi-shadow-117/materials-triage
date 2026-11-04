"""Egress is refused in code before anything is sent (Track G item 2)."""

from __future__ import annotations

import httpx
import pytest

from materials_triage.adapters import egress, mp
from materials_triage.adapters.base import Auth, Call, Source
from materials_triage.adapters.transport import HttpxTransport
from materials_triage.agent.llm import OpenAICompatibleClient, make_client
from materials_triage.settings import Settings


def _settings(**kw: object) -> Settings:
    return Settings(_env_file=None, mp_api_key="k", **kw)  # type: ignore[call-arg]


def _transport(sent: list[httpx.Request], **kw: object) -> HttpxTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"data": [], "meta": {"total_doc": 0}})

    return HttpxTransport(
        _settings(**kw),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda s: None,
    )


def test_a_host_off_the_list_is_refused_before_sending() -> None:
    sent: list[httpx.Request] = []
    t = _transport(sent)
    call = Call(
        source=Source.MP, endpoint="x", url="https://evil.example.com/x", params={}, auth=Auth.NONE
    )
    with pytest.raises(egress.EgressRefusedError, match="evil.example.com"):
        t.get(call)
    assert sent == []


def test_allowlisted_source_hosts_pass() -> None:
    sent: list[httpx.Request] = []
    t = _transport(sent)
    t.get(mp.plan_heartbeat())
    assert len(sent) == 1 and sent[0].url.host == "api.materialsproject.org"


def test_the_llm_endpoint_is_allowed_only_for_the_configured_provider() -> None:
    assert "api.anthropic.com" in egress.allowed_hosts(_settings(llm_provider="anthropic"))
    assert "api.anthropic.com" not in egress.allowed_hosts(_settings(llm_provider="none"))
    compat = egress.allowed_hosts(
        _settings(llm_provider="openai_compatible", llm_base_url="http://llm.internal:8000/v1")
    )
    assert "llm.internal" in compat and "api.anthropic.com" not in compat
    bedrock = egress.allowed_hosts(_settings(llm_provider="bedrock", aws_region="us-east-1"))
    assert "bedrock-mantle.us-east-1.api.aws" in bedrock
    # the named presets (Track H item 6) add their endpoint host automatically
    assert "api.openai.com" in egress.allowed_hosts(_settings(llm_provider="openai"))
    gemini = egress.allowed_hosts(_settings(llm_provider="gemini"))
    assert "generativelanguage.googleapis.com" in gemini and "api.openai.com" not in gemini
    proxied = egress.allowed_hosts(
        _settings(llm_provider="openai", llm_base_url="https://proxy.internal/v1")
    )
    assert "proxy.internal" in proxied and "api.openai.com" not in proxied


def test_llm_clients_refuse_other_hosts() -> None:
    client = make_client(_settings(llm_provider="anthropic", anthropic_api_key="x"))
    assert client is not None
    hook = client._client._client.event_hooks["request"][0]  # type: ignore[attr-defined]
    hook(httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    with pytest.raises(egress.EgressRefusedError):
        hook(httpx.Request("POST", "https://other.example.com/v1/messages"))
    compat = OpenAICompatibleClient(base_url="http://llm.internal:8000/v1", model="m", api_key=None)
    with pytest.raises(egress.EgressRefusedError):
        compat._client.post("http://elsewhere.example.com/chat/completions", json={})
