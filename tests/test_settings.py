import pytest

from materials_triage.settings import MissingSettingError, Settings


def test_defaults_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("MP_API_KEY", "OPENALEX_API_KEY", "DATABASE_URL", "FETCH_MODE"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.fetch_mode == "live"
    assert s.mp_api_key is None
    assert "triage_app" in s.database_url


def test_secret_is_not_printed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MP_API_KEY", "not-a-real-key-123")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert "not-a-real-key-123" not in repr(s)
    assert s.require("mp_api_key") == "not-a-real-key-123"


def test_missing_secret_names_the_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    with pytest.raises(MissingSettingError) as e:
        s.require("openalex_api_key")
    assert e.value.variable == "OPENALEX_API_KEY"


def test_unknown_fetch_mode_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FETCH_MODE", "yolo")
    with pytest.raises(ValueError):
        Settings(_env_file=None)  # type: ignore[call-arg]
