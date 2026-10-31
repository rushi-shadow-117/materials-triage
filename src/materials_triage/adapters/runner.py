"""The impure middle: cache lookup, transport, immutable storage.

Modes: live (store first within TTL, else network), replay (store only; a miss is missing
data, never a fetch), refresh (network, appending a new raw row). Transport failures become
availability events instead of exceptions, so a run can finish labeled partial.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from materials_triage.adapters.base import Call, NotFetchedError, RawResponse, Source, Transport
from materials_triage.adapters.transport import TransportFailedError
from materials_triage.provenance.store import Store
from materials_triage.settings import FetchMode

DEFAULT_TTLS: dict[Source, timedelta | None] = {
    Source.MP: timedelta(days=7),
    Source.OPENALEX: timedelta(days=30),
    Source.PUBCHEM: timedelta(days=90),
    Source.COD: timedelta(days=30),
    Source.OQMD: timedelta(days=30),
    Source.JARVIS: None,  # snapshots never expire; they are pinned by hash
    Source.EXPT_GAP: None,
    Source.CONFIG: None,
}


@dataclass(frozen=True)
class AvailabilityEvent:
    source: Source
    endpoint: str
    at: datetime
    error: str


@dataclass
class Fetched:
    raw_id: UUID
    raw: RawResponse
    cache_hit: bool


@dataclass
class Runner:
    store: Store
    transport: Transport
    mode: FetchMode = "live"
    run_id: UUID | None = None
    ttls: dict[Source, timedelta | None] = field(default_factory=lambda: dict(DEFAULT_TTLS))
    required_versions: dict[Source, str] = field(default_factory=dict)  # e.g. MP db_version
    events: list[AvailabilityEvent] = field(default_factory=list)

    def fetch(self, call: Call) -> Fetched:
        ttl = self.ttls.get(call.source)
        version = self.required_versions.get(call.source)
        if self.mode in ("live", "replay"):
            hit = self.store.lookup(
                call, ttl=None if self.mode == "replay" else ttl, require_source_version=version
            )
            if hit is not None:
                raw_id, raw = hit
                self.store.record_cache_hit(raw_id, call, mode=self.mode, run_id=self.run_id)
                return Fetched(raw_id, raw, cache_hit=True)
            if self.mode == "replay":
                raise NotFetchedError(call)
        raw = self.transport.get(call)
        if version is not None and raw.source_version is None:
            raw = raw.model_copy(update={"source_version": version})
        raw_id, _ = self.store.put_raw(raw, mode=self.mode, run_id=self.run_id)
        return Fetched(raw_id, raw, cache_hit=False)

    def try_fetch(self, call: Call) -> Fetched | None:
        """Like fetch, but a transport failure or replay miss is recorded, not raised."""
        try:
            return self.fetch(call)
        except (TransportFailedError, NotFetchedError) as e:
            self.events.append(
                AvailabilityEvent(
                    call.source, call.endpoint, datetime.now(UTC), f"{type(e).__name__}: {e}"
                )
            )
            return None
