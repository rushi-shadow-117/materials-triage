"""Process settings. Read from the environment and a local .env; unknown keys are rejected."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

FetchMode = Literal["live", "replay", "refresh"]
LLMProvider = Literal["anthropic", "bedrock", "openai_compatible", "none"]
ClassifyMode = Literal["live", "cache_only"]
AuthMode = Literal["none", "static", "oidc"]
Role = Literal["scientist", "fde", "admin"]


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
    # recorded in every bundle. Provider "none" runs the pipeline with no LLM step. A missing,
    # rejected, or out-of-credit key falls back to no model with a banner (agent/llm_status.py).
    llm_provider: LLMProvider = "anthropic"
    llm_model: str = "claude-sonnet-5-5"
    anthropic_api_key: SecretStr | None = None
    llm_base_url: str | None = None  # openai_compatible: the server's /v1 base URL
    llm_api_key: SecretStr | None = None  # openai_compatible: optional bearer token
    aws_region: str | None = None  # bedrock

    # live (the default): abstracts are classified by the model within the classify budget;
    # /api/criteria/resolve returns the run's estimated model calls first. cache_only: labels
    # come from the classifier cache only and a miss stays unclassified (the demo option).
    classify_mode: ClassifyMode = "live"

    data_cache_dir: Path = Path(".data-cache")
    # Unset: every source is the recorded cassettes, so a fresh clone runs with no keys and no
    # database. Set (live, replay, refresh): the Postgres store when it answers, else cassettes.
    fetch_mode: FetchMode | None = None

    # Auth (Track C). Roles come only from the bearer token (static or OIDC); in mode "none"
    # every request carries dev_role. site_mode refuses static tokens unless allowed.
    auth_mode: AuthMode = "none"
    dev_role: Role = "scientist"
    static_tokens: str | None = None  # "token:role,token:role"
    site_mode: bool = False
    allow_static_tokens: bool = False
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_roles_claim: str = "realm_access.roles"

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
