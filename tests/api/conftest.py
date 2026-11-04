"""API tests run the real pipeline over recorded cassettes with no model (LLM_PROVIDER=none)
and no network. Each test gets its own data cache directory, so runs and audit entries do
not leak between tests."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from materials_triage.api.app import create_app
from materials_triage.cli import wiring
from materials_triage.settings import Settings


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "_env_file": None,
        "llm_provider": "none",
        "data_cache_dir": tmp_path / "cache",
        "fetch_mode": "replay",
        "auth_mode": "none",
    }
    base.update(overrides)
    return Settings(**base)


@pytest.fixture(autouse=True)
def cassettes_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every API run reads the recorded cassettes; Postgres is never consulted."""
    monkeypatch.setattr(
        wiring,
        "resolve_fetch_source",
        lambda settings, requested, **kw: ("cassettes", "fetch: cassettes (test)"),
    )


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(make_settings(tmp_path))
    with TestClient(app) as c:
        yield c


def wait_for_run(client: TestClient, run_id: str, timeout_s: float = 120.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        status = client.get(f"/api/runs/{run_id}/status").json()
        if status["status"] not in ("queued", "running"):
            return status
        time.sleep(0.2)
    raise AssertionError(f"run {run_id} did not finish in {timeout_s}s")


def sse_events(text: str) -> list[dict[str, Any]]:
    """Parse an SSE body into [{event, data}] with the data decoded from JSON."""
    out: list[dict[str, Any]] = []
    for block in text.replace("\r\n", "\n").strip().split("\n\n"):  # sse-starlette uses CRLF
        event = None
        data_lines = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if event and data_lines:
            out.append({"event": event, "data": json.loads("\n".join(data_lines))})
    return out
