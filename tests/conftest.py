"""Store tests run against the real Postgres from Compose (or the CI service container)."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text

from materials_triage.agent import llm_status
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


DB_REACHABLE = _reachable(SETTINGS.database_url_migrate)


@pytest.fixture(autouse=True)
def clean_tables(request: pytest.FixtureRequest) -> Iterator[None]:
    """The owner role empties the tables around each test; the app role never could.
    Without Postgres this does nothing, so tests that need the store skip (requires_db)
    instead of every test erroring on the cleanup."""
    if not DB_REACHABLE:
        yield
        return
    migrate_engine: Engine = request.getfixturevalue("migrate_engine")
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


class ModelCallInTestError(AssertionError):
    """A test reached the model provider's HTTP layer. Tests use fakes only."""


@pytest.fixture(autouse=True)
def no_model_calls(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No test may send a request to a model provider, whatever keys .env holds: the SDK's
    request method raises. Each test also starts with a fresh model status."""
    from anthropic._base_client import SyncAPIClient

    def refuse(*_a: object, **_k: object) -> None:
        raise ModelCallInTestError("a test tried to call the model provider; use a fake")

    monkeypatch.setattr(SyncAPIClient, "request", refuse)
    llm_status.reset()
    yield
    llm_status.reset()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "e2e: browser tests against the served app (skip without web/dist or Chromium)"
    )
    config.addinivalue_line("markers", "keycloak: needs the Compose keycloak service")
