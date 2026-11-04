"""Against the Compose keycloak service (`docker compose --profile auth up -d keycloak`): a
password grant for each seeded dev user gives a token whose realm role the API reads. Skipped
when the service is not up. No Anthropic call."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from materials_triage.api.app import create_app
from tests.api.conftest import make_settings

ISSUER = "http://localhost:8080/realms/materials-triage"
AUDIENCE = "materials-triage-api"
CLIENT_ID = "materials-triage-web"

pytestmark = pytest.mark.keycloak


def _up() -> bool:
    try:
        return (
            httpx.get(f"{ISSUER}/.well-known/openid-configuration", timeout=2.0).status_code == 200
        )
    except httpx.HTTPError:
        return False


def _token(username: str) -> str:
    r = httpx.post(
        f"{ISSUER}/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": CLIENT_ID,
            "username": username,
            "password": username,
            "scope": "openid",
        },
        timeout=10.0,
    )
    r.raise_for_status()
    return str(r.json()["access_token"])


@pytest.mark.skipif(not _up(), reason="keycloak is not running on localhost:8080")
def test_keycloak_tokens_carry_the_realm_role(tmp_path: Path) -> None:
    app = create_app(
        make_settings(tmp_path, auth_mode="oidc", oidc_issuer=ISSUER, oidc_audience=AUDIENCE)
    )
    with TestClient(app) as c:
        for user, role in (("scientist", "scientist"), ("fde", "fde"), ("admin", "admin")):
            me = c.get("/api/me", headers={"Authorization": f"Bearer {_token(user)}"})
            assert me.status_code == 200, me.text
            assert me.json()["role"] == role and me.json()["auth_mode"] == "oidc"
        assert c.get("/api/me").status_code == 401
        assert (
            c.get(
                "/api/config/layers", headers={"Authorization": f"Bearer {_token('scientist')}"}
            ).status_code
            == 403
        )
        assert (
            c.get("/api/audit", headers={"Authorization": f"Bearer {_token('admin')}"}).status_code
            == 200
        )
