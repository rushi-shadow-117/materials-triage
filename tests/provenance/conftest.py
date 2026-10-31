"""Store tests run against the real Postgres from Compose (or the CI service container)."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text

from materials_triage.provenance.store import make_engine
from materials_triage.settings import Settings

SETTINGS = Settings(_env_file=None)  # type: ignore[call-arg]


def _reachable(url: str) -> bool:
    try:
        with make_engine(url).connect() as conn:
            conn.execute(text("select 1"))
        return True
    except Exception:  # noqa: BLE001 - any failure means "no database here"
        return False


requires_db = pytest.mark.skipif(
    not _reachable(SETTINGS.database_url_migrate), reason="Postgres not reachable"
)


@pytest.fixture(scope="session")
def migrate_engine() -> Engine:
    return make_engine(SETTINGS.database_url_migrate)


@pytest.fixture(scope="session")
def app_engine() -> Engine:
    return make_engine(SETTINGS.database_url)


@pytest.fixture(scope="session")
def maint_engine() -> Engine:
    return make_engine(SETTINGS.database_url_maint)


@pytest.fixture(autouse=True)
def clean_tables(migrate_engine: Engine) -> Iterator[None]:
    """The owner role empties the tables around each test; the app role never could."""
    with migrate_engine.begin() as conn:
        for t in (
            "fetch_events",
            "records",
            "raw_responses",
            "maintenance_log",
            "runs",
            "snapshots",
        ):
            conn.execute(text(f"delete from triage.{t}"))
    yield
