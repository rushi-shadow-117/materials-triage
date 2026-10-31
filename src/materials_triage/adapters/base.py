"""Adapter contract: plan calls, fetch raw bytes, store them, then normalize.

The two pure steps (`plan`, `normalize`) are what tests exercise against recorded cassettes.
The runner owns the impure middle: cache lookup, transport, immutable storage.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class Source(StrEnum):
    MP = "materials_project"
    JARVIS = "jarvis_dft_3d"
    EXPT_GAP = "expt_gap"
    OPENALEX = "openalex"
    PUBCHEM = "pubchem"
    COD = "cod"
    OQMD = "oqmd"  # documented extension; not wired
    CONFIG = "config"


class Auth(StrEnum):
    """How the transport injects credentials. Never visible in RawResponse."""

    NONE = "none"
    MP_HEADER = "mp_header"  # X-API-KEY
    OPENALEX_PARAM = "openalex_param"  # api_key (and mailto) query parameters


class Call(BaseModel):
    """One planned HTTP GET. Params exclude secrets; the transport adds them."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Source
    endpoint: str  # short label, e.g. "materials/summary"
    url: str
    params: dict[str, str] = Field(default_factory=dict)
    auth: Auth = Auth.NONE

    @property
    def cache_key(self) -> str:
        canonical = json.dumps(
            {"url": self.url, "params": dict(sorted(self.params.items()))},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode()).hexdigest()


class RawResponse(BaseModel):
    """Exact bytes of one upstream response plus what was asked. Stored before parsing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    call: Call
    status: int
    body: bytes
    content_type: str | None
    fetched_at: datetime
    source_version: str | None = None  # MP db_version, snapshot sha, and so on
    license: str | None = None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()

    def json(self) -> Any:  # type: ignore[override]
        return json.loads(self.body)

    @classmethod
    def now(cls) -> datetime:
        return datetime.now(UTC)


class Transport(Protocol):
    def get(self, call: Call) -> RawResponse: ...


class NotFetchedError(RuntimeError):
    """Raised by a replay-only transport when a call has no stored response."""

    def __init__(self, call: Call) -> None:
        super().__init__(f"no stored response for {call.source} {call.endpoint}")
        self.call = call
