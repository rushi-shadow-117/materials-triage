"""Append-only provenance store over Postgres.

The store is also the cache: a lookup finds the latest fetch event for a call's cache key
within a TTL and returns the stored raw response. Raw bodies are deduplicated by
(source, sha256); every fetch or cache hit adds a fetch_events row, so nothing is ever
updated or overwritten. The app role cannot UPDATE or DELETE (roles.sql).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, create_engine, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from materials_triage.adapters.base import Call, RawResponse, Source
from materials_triage.provenance import schema as s
from materials_triage.records import SourceRecord


def make_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True, future=True)


class Store:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    # ---------------------------------------------------------------- raw responses

    def put_raw(
        self,
        raw: RawResponse,
        *,
        mode: str,
        run_id: UUID | None = None,
    ) -> tuple[UUID, bool]:
        """Store a response immutably. Returns (raw_id, was_new).

        An identical body from the same source reuses the existing row; a new fetch_events
        row is written either way, so the fetch itself is always on record.
        """
        sha = raw.sha256
        with self._engine.begin() as conn:
            inserted = conn.execute(
                pg_insert(s.raw_responses)
                .values(
                    source=str(raw.call.source),
                    endpoint=raw.call.endpoint,
                    url=raw.call.url,
                    params=dict(raw.call.params),
                    cache_key=raw.call.cache_key,
                    status=raw.status,
                    body=raw.body,
                    sha256=sha,
                    content_type=raw.content_type,
                    first_fetched_at=raw.fetched_at,
                    source_version=raw.source_version,
                    license=raw.license,
                )
                .on_conflict_do_nothing(constraint="uq_raw_source_sha")
                .returning(s.raw_responses.c.id)
            ).scalar_one_or_none()
            was_new = inserted is not None
            raw_id: UUID = (
                inserted
                or conn.execute(
                    select(s.raw_responses.c.id).where(
                        s.raw_responses.c.source == str(raw.call.source),
                        s.raw_responses.c.sha256 == sha,
                    )
                ).scalar_one()
            )
            conn.execute(
                insert(s.fetch_events).values(
                    raw_response_id=raw_id,
                    source=str(raw.call.source),
                    cache_key=raw.call.cache_key,
                    fetched_at=raw.fetched_at,
                    run_id=run_id,
                    cache_hit=False,
                    transport_mode=mode,
                    source_version=raw.source_version,
                )
            )
        return raw_id, was_new

    def record_cache_hit(self, raw_id: UUID, call: Call, *, mode: str, run_id: UUID | None) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                insert(s.fetch_events).values(
                    raw_response_id=raw_id,
                    source=str(call.source),
                    cache_key=call.cache_key,
                    fetched_at=datetime.now(UTC),
                    run_id=run_id,
                    cache_hit=True,
                    transport_mode=mode,
                )
            )

    def lookup(
        self,
        call: Call,
        *,
        ttl: timedelta | None,
        now: datetime | None = None,
        require_source_version: str | None = None,
    ) -> tuple[UUID, RawResponse] | None:
        """Latest stored response for this call, if fetched within `ttl` (None = no expiry)
        and, when given, carrying `require_source_version` (for MP database version changes)."""
        now = now or datetime.now(UTC)
        q = (
            select(s.fetch_events.c.raw_response_id, s.fetch_events.c.fetched_at)
            .where(
                s.fetch_events.c.source == str(call.source),
                s.fetch_events.c.cache_key == call.cache_key,
                s.fetch_events.c.cache_hit.is_(False),
            )
            .order_by(s.fetch_events.c.fetched_at.desc())
            .limit(1)
        )
        with self._engine.connect() as conn:
            row = conn.execute(q).first()
            if row is None:
                return None
            raw_id, fetched_at = row
            if ttl is not None and fetched_at < now - ttl:
                return None
            raw = self._load_raw(conn, raw_id)
        if require_source_version is not None and raw.source_version != require_source_version:
            return None
        return raw_id, raw

    def get_raw(self, raw_id: UUID) -> RawResponse:
        with self._engine.connect() as conn:
            return self._load_raw(conn, raw_id)

    def _load_raw(self, conn: Any, raw_id: UUID) -> RawResponse:
        r = conn.execute(select(s.raw_responses).where(s.raw_responses.c.id == raw_id)).one()
        return RawResponse(
            call=Call(
                source=Source(r.source), endpoint=r.endpoint, url=r.url, params=dict(r.params)
            ),
            status=r.status,
            body=bytes(r.body),
            content_type=r.content_type,
            fetched_at=r.first_fetched_at,
            source_version=r.source_version,
            license=r.license,
        )

    # ---------------------------------------------------------------- records

    def put_records(self, records: list[SourceRecord], *, raw_id: UUID) -> list[UUID]:
        if not records:
            return []
        now = datetime.now(UTC)
        rows = [
            {
                "source": rec.provenance.source,
                "kind": rec.kind,
                "source_record_id": rec.source_record_id,
                "raw_response_id": raw_id,
                "payload": rec.payload,
                "composition": rec.composition,
                "license": rec.license,
                "created_at": now,
            }
            for rec in records
        ]
        with self._engine.begin() as conn:
            result = conn.execute(insert(s.records).returning(s.records.c.id), rows)
            return [row[0] for row in result]

    def records_for(
        self, *, source: str, kind: str, composition: str | None = None
    ) -> list[dict[str, Any]]:
        q = select(
            s.records.c.source_record_id, s.records.c.payload, s.records.c.raw_response_id
        ).where(s.records.c.source == source, s.records.c.kind == kind)
        if composition is not None:
            q = q.where(s.records.c.composition == composition)
        with self._engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(q)]

    # ---------------------------------------------------------------- snapshots and runs

    def put_snapshot(
        self,
        *,
        name: str,
        url: str,
        sha256: str,
        fetched_at: datetime,
        entries_total: int | None,
        slice_path: str | None,
    ) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                pg_insert(s.snapshots)
                .values(
                    name=name,
                    url=url,
                    sha256=sha256,
                    fetched_at=fetched_at,
                    entries_total=entries_total,
                    slice_path=slice_path,
                )
                .on_conflict_do_nothing(index_elements=["name"])
            )

    def start_run(self, *, config_sha: str, source_versions: dict[str, str] | None = None) -> UUID:
        with self._engine.begin() as conn:
            run_id: UUID = conn.execute(
                insert(s.runs)
                .values(
                    started_at=datetime.now(UTC),
                    config_sha=config_sha,
                    status="running",
                    source_versions=source_versions or {},
                )
                .returning(s.runs.c.run_id)
            ).scalar_one()
        return run_id


class MaintenanceStore:
    """Retention deletes, performed only by the maintenance role and always logged."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def delete_fetch_events_before(self, cutoff: datetime, *, reason: str) -> int:
        with self._engine.begin() as conn:
            result = conn.execute(
                s.fetch_events.delete().where(s.fetch_events.c.fetched_at < cutoff)
            )
            deleted = result.rowcount
            conn.execute(
                insert(s.maintenance_log).values(
                    performed_at=datetime.now(UTC),
                    role="triage_maint",
                    action="delete_fetch_events_before",
                    details={"cutoff": cutoff.isoformat(), "deleted": deleted, "reason": reason},
                )
            )
        return int(deleted)
