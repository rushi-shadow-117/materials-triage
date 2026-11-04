"""A fresh clone runs with no keys and no database (human test session, Nov 4, breaker 1).

The defaults are Sonnet, live classification, and recorded data. A missing, rejected, or
out-of-credit key falls back to no model with a banner; the run still completes. No test
reaches a model provider: the inner clients here are fakes that raise the SDK's errors.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient

from materials_triage.agent import llm_status
from materials_triage.agent.llm import LLMResponse, ToolSpec, Turn
from materials_triage.api.app import create_app
from materials_triage.cli import wiring
from materials_triage.settings import Settings
from tests.api.conftest import make_settings, wait_for_run

# taken at import, before tests/api/conftest.py replaces it with a cassettes-only stub
REAL_RESOLVE = wiring.resolve_fetch_source

RANK = {
    "request_text": "rank",
    "profile": "oxide_dielectric_thin_film",
    "settings": {"mode": "candidate_list", "candidate_list": ["HfO2", "ZrO2", "Al2O3"]},
}


def test_bare_defaults() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert (s.llm_provider, s.llm_model, s.classify_mode) == (
        "anthropic",
        "claude-sonnet-5-5",
        "live",
    )
    assert s.fetch_mode is None
    # unset FETCH_MODE means recorded data even when Postgres answers
    source, line = REAL_RESOLVE(s, "auto", reachable=lambda _url: True)
    assert source == "cassettes" and "FETCH_MODE not set" in line
    # an explicit FETCH_MODE keeps the store when it answers
    explicit = Settings(_env_file=None, fetch_mode="replay")  # type: ignore[call-arg]
    assert REAL_RESOLVE(explicit, "auto", reachable=lambda _url: True)[0] == "store"


def _bare(tmp_path: Path, **overrides: Any) -> TestClient:
    values: dict[str, Any] = {"llm_provider": "anthropic", "anthropic_api_key": None}
    values.update(fetch_mode=None, **overrides)
    settings = make_settings(tmp_path, **values)
    return TestClient(create_app(settings))


def test_missing_key_falls_back_and_the_run_completes(tmp_path: Path) -> None:
    with _bare(tmp_path) as client:
        health = client.get("/health").json()
        assert health["llm_status"] == "missing_key"
        assert health["llm_model"] == "claude-sonnet-5-5"
        assert "fill the criteria form by hand" in health["llm_note"]
        assert client.get("/me").json()["llm_status"] == "missing_key"
        parsed = client.post("/parse", json={"request_text": "hafnia please"}).json()
        assert parsed["parse_available"] is False and "key is not set" in parsed["reason"]
        run_id = client.post("/runs", json=RANK).json()["run_id"]
        status = wait_for_run(client, run_id)
        assert status["status"] == "completed", status
        assert status["ranked"] == 3


def _sdk_error(kind: str) -> Exception:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    if kind == "auth":
        response = httpx.Response(401, request=request)
        return anthropic.AuthenticationError("invalid x-api-key", response=response, body=None)
    response = httpx.Response(400, request=request)
    return anthropic.BadRequestError(
        "Your credit balance is too low to access the Anthropic API.",
        response=response,
        body=None,
    )


class RaisingClient:
    model = "claude-sonnet-5-5"
    provider = "anthropic"

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    def complete(
        self, *, system: str, turns: list[Turn], tools: list[ToolSpec], max_tokens: int
    ) -> LLMResponse:
        self.calls += 1
        raise self.error


@pytest.mark.parametrize(("kind", "status"), [("auth", "invalid_key"), ("credit", "no_credit")])
def test_rejected_key_or_no_credit_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str, status: str
) -> None:
    inner = RaisingClient(_sdk_error(kind))
    monkeypatch.setattr(wiring, "make_client", lambda _settings: inner)
    with _bare(tmp_path, anthropic_api_key="sk-test-not-a-key") as client:
        assert client.get("/health").json()["llm_status"] == "ok"
        parsed = client.post("/parse", json={"request_text": "hafnia please"}).json()
        assert parsed["parse_available"] is False
        assert client.get("/health").json()["llm_status"] == status
        run_id = client.post("/runs", json=RANK).json()["run_id"]
        assert wait_for_run(client, run_id)["status"] == "completed"
    # one rejected request; every later step skipped the provider
    assert inner.calls == 1


def test_resolve_returns_the_estimated_model_calls(tmp_path: Path) -> None:
    body = {"profile": "oxide_dielectric_thin_film", "settings": RANK["settings"]}
    with _bare(tmp_path, anthropic_api_key="sk-test-not-a-key") as client:
        est = client.post("/criteria/resolve", json=body).json()["estimated_model_calls"]
        # three candidates, at most five abstracts each, one call per abstract, plus rationale
        assert (est["classify"], est["rationale"], est["total"]) == (15, 1, 16)
        assert est["cap"] == 123 and "fewer when the classifier cache" in est["basis"]
    with _bare(tmp_path, anthropic_api_key="sk-x", classify_mode="cache_only") as client:
        est = client.post("/criteria/resolve", json=body).json()["estimated_model_calls"]
        assert (est["classify"], est["total"]) == (0, 1)
    with _bare(tmp_path) as client:  # no key: no model call at all
        est = client.post("/criteria/resolve", json=body).json()["estimated_model_calls"]
        assert est["total"] == 0 and "key is not set" in est["basis"]


def test_tests_cannot_reach_the_provider(tmp_path: Path) -> None:
    """The autouse guard in tests/conftest.py: a real SDK client fails before any request."""
    settings = make_settings(tmp_path, llm_provider="anthropic", anthropic_api_key="sk-x")
    client = wiring.make_llm(settings, no_llm=False)
    assert client is not None
    with pytest.raises(AssertionError, match="tried to call the model provider"):
        client.complete(system="s", turns=[Turn("user", "hi")], tools=[], max_tokens=10)
    assert llm_status.available()  # a test-guard refusal is not a key failure
