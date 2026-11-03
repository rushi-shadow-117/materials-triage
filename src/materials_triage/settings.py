"""Process settings. Read from the environment and a local .env; unknown keys are rejected."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

FetchMode = Literal["live", "replay", "refresh"]
LLMProvider = Literal["anthropic", "bedrock", "openai_compatible", "none"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="forbid")

    # Postgres roles (see provenance/roles.sql). The app role can only INSERT and SELECT.
    database_url: str = "postgresql+psycopg://triage_app:triage_app@localhost:5433/triage"
    database_url_migrate: str = (
        "postgresql+psycopg://triage_migrate:triage_migrate@localhost:5433/triage"
    )
    database_url_maint: str = "postgresql+psycopg://triage_maint:triage_maint@localhost:5433/triage"

    # Upstream credentials. Injected by the transport; never written to raw records.
    mp_api_key: SecretStr | None = None
    openalex_api_key: SecretStr | None = None
    openalex_mailto: str | None = None

    # LLM access (Track B). The model id is the exact string the provider serves; it is
    # recorded in every bundle. Provider "none" runs the pipeline with no LLM step.
    llm_provider: LLMProvider = "anthropic"
    llm_model: str = "claude-opus-5-5"
    anthropic_api_key: SecretStr | None = None
    llm_base_url: str | None = None  # openai_compatible: the server's /v1 base URL
    llm_api_key: SecretStr | None = None  # openai_compatible: optional bearer token
    aws_region: str | None = None  # bedrock

    data_cache_dir: Path = Path(".data-cache")
    fetch_mode: FetchMode = "live"

    def require(self, name: str) -> str:
        """Return a secret's value or raise with the variable name, never the value."""
        secret = getattr(self, name)
        if secret is None:
            raise MissingSettingError(name.upper())
        return str(secret.get_secret_value())


class MissingSettingError(RuntimeError):
    def __init__(self, variable: str) -> None:
        super().__init__(f"{variable} is not set")
        self.variable = variable


def load_settings(**overrides: object) -> Settings:
    return Settings(**overrides)  # type: ignore[arg-type]
