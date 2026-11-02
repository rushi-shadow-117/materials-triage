"""Adapter tests run against cassettes under fixtures/adapters/<source>/.

WIRE_RECORD=once records missing cassettes with real keys from .env (local only).
The default, none, replays and fails on any unrecorded request (CI).
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from materials_triage.adapters.base import Call, RawResponse, Source
from materials_triage.adapters.recording import make_vcr
from materials_triage.adapters.transport import TIMEOUT, USER_AGENT, HttpxTransport
from materials_triage.settings import Settings

ROOT = Path(__file__).resolve().parents[2]
ADAPTER_CASSETTES = ROOT / "fixtures" / "adapters"
SNAPSHOTS = ROOT / "fixtures" / "snapshots"
SYNTHETIC = ROOT / "fixtures" / "synthetic"
RECORD_MODE = os.environ.get("WIRE_RECORD", "none")

VCR = make_vcr(RECORD_MODE)


@pytest.fixture(scope="session")
def settings() -> Settings:
    if RECORD_MODE != "none":
        return Settings()  # real keys from .env, needed to record
    return Settings(_env_file=None, mp_api_key="recorded", openalex_api_key="recorded")  # type: ignore[call-arg]


@pytest.fixture
def transport(settings: Settings) -> HttpxTransport:
    client = httpx.Client(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
    return HttpxTransport(settings, client=client, sleep=lambda _s: None)


@pytest.fixture
def cassette() -> Callable[[str, str], object]:
    @contextmanager
    def _use(source: str, name: str) -> Iterator[None]:
        path = ADAPTER_CASSETTES / source / f"{name}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        with VCR.use_cassette(str(path)):
            yield

    return _use


@pytest.fixture
def manifest() -> dict:  # type: ignore[type-arg]
    return json.loads((SNAPSHOTS / "MANIFEST.json").read_text())["snapshots"]


def synthetic_raw(name: str, call: Call) -> RawResponse:
    """Wrap a synthetic fixture as a RawResponse (marker stripped from the body)."""
    doc = json.loads((SYNTHETIC / name).read_text())
    assert doc.get("_synthetic") is True
    body = {k: v for k, v in doc.items() if not k.startswith("_")}
    return RawResponse(
        call=call,
        status=200,
        body=json.dumps(body).encode(),
        content_type="application/json",
        fetched_at=datetime.now(UTC),
        source_version="synthetic",
    )


def make_call(source: Source, endpoint: str, url: str, **params: str) -> Call:
    return Call(source=source, endpoint=endpoint, url=url, params=params)
