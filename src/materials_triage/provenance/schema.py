"""Provenance store tables. Append-only by role policy (see roles.sql).

raw_responses   exact bytes of every upstream response, deduplicated by (source, sha256)
fetch_events    one row per fetch or cache hit, so "when did we last see this" is answerable
records         normalized records as jsonb, each pointing at the raw row it came from
snapshots       pinned file snapshots (JARVIS, gap tables)
runs            one row per triage run; Phase 3 adds prompt and model fields
maintenance_log every retention deletion, written by the maintenance role
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

SCHEMA = "triage"
metadata = MetaData(schema=SCHEMA)

raw_responses = Table(
    "raw_responses",
    metadata,
    Column("id", Uuid, primary_key=True, server_default=text("gen_random_uuid()")),
    Column("source", Text, nullable=False),
    Column("endpoint", Text, nullable=False),
    Column("url", Text, nullable=False),
    Column("params", JSONB, nullable=False),  # secrets never present
    Column("cache_key", Text, nullable=False),
    Column("status", Integer, nullable=False),
    Column("body", LargeBinary, nullable=False),
    Column("sha256", Text, nullable=False),
    Column("content_type", Text),
    Column("first_fetched_at", DateTime(timezone=True), nullable=False),
    Column("source_version", Text),
    Column("license", Text),
    UniqueConstraint("source", "sha256", name="uq_raw_source_sha"),
    Index("ix_raw_source_cache_key", "source", "cache_key"),
)

fetch_events = Table(
    "fetch_events",
    metadata,
    Column("id", Uuid, primary_key=True, server_default=text("gen_random_uuid()")),
    Column("raw_response_id", Uuid, ForeignKey("triage.raw_responses.id"), nullable=False),
    Column("source", Text, nullable=False),
    Column("cache_key", Text, nullable=False),
    Column("fetched_at", DateTime(timezone=True), nullable=False),
    Column("run_id", Uuid),
    Column("cache_hit", Boolean, nullable=False),
    Column("transport_mode", Text, nullable=False),  # live | replay | refresh | seed
    Column("source_version", Text),
    Index("ix_fetch_source_key_time", "source", "cache_key", "fetched_at"),
)

records = Table(
    "records",
    metadata,
    Column("id", Uuid, primary_key=True, server_default=text("gen_random_uuid()")),
    Column("source", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("source_record_id", Text, nullable=False),
    Column("raw_response_id", Uuid, ForeignKey("triage.raw_responses.id"), nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("composition", Text),
    Column("license", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("supersedes", Uuid),
    Index("ix_records_source_kind_id", "source", "kind", "source_record_id"),
    Index("ix_records_composition", "composition"),
)

snapshots = Table(
    "snapshots",
    metadata,
    Column("name", Text, primary_key=True),
    Column("url", Text, nullable=False),
    Column("sha256", Text, nullable=False),
    Column("fetched_at", DateTime(timezone=True), nullable=False),
    Column("entries_total", Integer),
    Column("slice_path", Text),
)

runs = Table(
    "runs",
    metadata,
    Column("run_id", Uuid, primary_key=True, server_default=text("gen_random_uuid()")),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("config_sha", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("partial", Boolean, nullable=False, server_default=text("false")),
    Column("source_versions", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
)

maintenance_log = Table(
    "maintenance_log",
    metadata,
    Column("id", Uuid, primary_key=True, server_default=text("gen_random_uuid()")),
    Column("performed_at", DateTime(timezone=True), nullable=False),
    Column("role", Text, nullable=False),
    Column("action", Text, nullable=False),
    Column("details", JSONB, nullable=False),
)
