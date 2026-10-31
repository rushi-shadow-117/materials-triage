"""foreign key indexes and explicit role grants

Revision ID: 41f97da44c9d
Revises: 04e277dce19c
Create Date: 2026-10-31 15:58:04.719461

Autogenerate also proposed dropping and recreating the two foreign keys without names
(cross-schema comparison noise); those operations were removed by hand. This migration
adds the indexes behind the foreign keys and states the role privileges explicitly, so a
fresh database migrated by triage_migrate has exactly these grants.
"""

from __future__ import annotations

from alembic import op

revision = "41f97da44c9d"
down_revision = "04e277dce19c"
branch_labels = None
depends_on = None

GRANTS = (
    "REVOKE ALL ON ALL TABLES IN SCHEMA triage FROM triage_app",
    "GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA triage TO triage_app",
    "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA triage TO triage_app",
    "REVOKE ALL ON ALL TABLES IN SCHEMA triage FROM triage_maint",
    "GRANT SELECT, DELETE ON ALL TABLES IN SCHEMA triage TO triage_maint",
    "GRANT INSERT ON triage.maintenance_log TO triage_maint",
    "REVOKE ALL ON triage.alembic_version FROM triage_app, triage_maint",
)


def upgrade() -> None:
    op.create_index(
        "ix_fetch_raw_response_id",
        "fetch_events",
        ["raw_response_id"],
        unique=False,
        schema="triage",
    )
    op.create_index(
        "ix_records_raw_response_id", "records", ["raw_response_id"], unique=False, schema="triage"
    )
    for stmt in GRANTS:
        op.execute(stmt)


def downgrade() -> None:
    op.drop_index("ix_records_raw_response_id", table_name="records", schema="triage")
    op.drop_index("ix_fetch_raw_response_id", table_name="fetch_events", schema="triage")
    # Grants are left in place: they match the roles.sql defaults.
