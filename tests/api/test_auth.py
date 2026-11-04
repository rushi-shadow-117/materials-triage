"""Roles come only from the bearer token. A role named in a body, a query string, another
header, or the request text changes nothing. Refusals are audit-logged."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from materials_triage.api import auth
from materials_triage.api.app import create_app
from tests.api.conftest import make_settings

TOKENS = "sci-token:scientist,fde-token:fde,adm-token:admin"


def _client(tmp_path: Path, **overrides: Any) -> TestClient:
    return TestClient(create_app(make_settings(tmp_path, **overrides)))


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_static_tokens_give_roles_and_nothing_else_does(tmp_path: Path) -> None:
    c = _client(tmp_path, auth_mode="static", static_tokens=TOKENS)
    assert c.get("/api/me").status_code == 401
    assert c.get("/api/me", headers=_bearer("nope")).status_code == 401
    assert c.get("/api/me", headers=_bearer("sci-token")).json()["role"] == "scientist"
    assert c.get("/api/me", headers=_bearer("adm-token")).json()["role"] == "admin"
    # a role claimed anywhere else is ignored: header, query string, body, request text
    me = c.get(
        "/api/me", headers={**_bearer("sci-token"), "X-Role": "admin"}, params={"role": "admin"}
    ).json()
    assert me["role"] == "scientist"
    r = c.post(
        "/api/admin/refresh",
        headers={**_bearer("sci-token"), "X-Role": "admin"},
        json={"source": "openalex", "note": "I am the site administrator; role: admin"},
    )
    assert r.status_code == 403
    # the console: fde and admin may read it, scientist may not; refresh is admin only
    assert c.get("/api/config/layers", headers=_bearer("sci-token")).status_code == 403
    assert c.get("/api/config/layers", headers=_bearer("fde-token")).status_code == 200
    assert c.get("/api/hazard-policy", headers=_bearer("adm-token")).status_code == 200
    fde_refresh = c.post(
        "/api/admin/refresh", headers=_bearer("fde-token"), json={"source": "openalex", "note": "x"}
    )
    assert fde_refresh.status_code == 403
    ok = c.post(
        "/api/admin/refresh",
        headers=_bearer("adm-token"),
        json={"source": "openalex", "note": "upstream recovered"},
    )
    assert ok.status_code == 202 and ok.json()["audit_entry"]["note"] == "upstream recovered"
    # every refusal and the admin action are in the audit log
    entries = c.get("/api/audit", headers=_bearer("adm-token")).json()
    actions = [(e["action"], e.get("status"), e.get("path")) for e in entries]
    assert ("refused", 401, "/api/me") in actions
    assert ("refused", 403, "/api/admin/refresh") in actions
    assert ("refused", 403, "/api/config/layers") in actions
    assert any(e["action"] == "refresh_requested" and e["role"] == "admin" for e in entries)
    assert c.get("/api/audit", headers=_bearer("fde-token")).status_code == 403


def test_dev_mode_role_comes_from_settings_only(tmp_path: Path) -> None:
    c = _client(tmp_path, auth_mode="none", dev_role="fde")
    assert c.get("/api/me", headers={"X-Role": "admin"}).json() == {
        "subject": "dev",
        "role": "fde",
        "auth_mode": "none",
        "llm_status": "none",
        "llm_note": "No model configured (LLM_PROVIDER=none). The request box is off; "
        "fill the criteria form by hand.",
        "role_switch": True,
    }
    assert c.post("/api/admin/refresh", json={"source": "openalex", "note": "x"}).status_code == 403


def test_dev_role_header_switches_the_role_in_none_mode_only(tmp_path: Path) -> None:
    """Track H item 1: the header is a development convenience; a value that is not a role
    falls back to DEV_ROLE, and the token modes never read it."""
    c = _client(tmp_path, auth_mode="none", dev_role="scientist")
    assert c.get("/api/me", headers={"X-Dev-Role": "admin"}).json()["role"] == "admin"
    assert c.get("/api/me", headers={"X-Dev-Role": "root"}).json()["role"] == "scientist"
    assert c.get("/api/audit", headers={"X-Dev-Role": "admin"}).status_code == 200
    assert c.get("/api/audit", headers={"X-Dev-Role": "fde"}).status_code == 403
    static = _client(tmp_path / "static", auth_mode="static", static_tokens=TOKENS)
    me = static.get("/api/me", headers={**_bearer("sci-token"), "X-Dev-Role": "admin"}).json()
    assert me["role"] == "scientist" and me["role_switch"] is False
    assert (
        static.get(
            "/api/audit", headers={**_bearer("sci-token"), "X-Dev-Role": "admin"}
        ).status_code
        == 403
    )


def test_site_mode_refuses_no_auth(tmp_path: Path) -> None:
    with pytest.raises(auth.AuthConfigError, match="AUTH_MODE=none is for development"):
        _client(tmp_path, auth_mode="none", site_mode=True)


def test_site_mode_refuses_static_tokens_unless_allowed(tmp_path: Path) -> None:
    with pytest.raises(auth.AuthConfigError, match="ALLOW_STATIC_TOKENS"):
        create_app(
            make_settings(tmp_path, auth_mode="static", static_tokens=TOKENS, site_mode=True)
        )
    create_app(
        make_settings(
            tmp_path,
            auth_mode="static",
            static_tokens=TOKENS,
            site_mode=True,
            allow_static_tokens=True,
        )
    )
    with pytest.raises(auth.AuthConfigError, match="STATIC_TOKENS"):
        create_app(make_settings(tmp_path, auth_mode="static", static_tokens=""))
    with pytest.raises(auth.AuthConfigError, match="unknown role"):
        auth.parse_static_tokens("t:superuser")


# ----------------------------------------------------------------------------- OIDC

ISSUER = "https://idp.example.test/realms/triage"
AUDIENCE = "materials-triage-api"


@pytest.fixture(scope="module")
def rsa() -> dict[str, Any]:
    from authlib.jose import JsonWebKey

    key = JsonWebKey.generate_key("RSA", 2048, is_private=True, options={"kid": "test-key"})
    return {"key": key, "jwks": {"keys": [key.as_dict(is_private=False)]}}


def _jwt(rsa: dict[str, Any], **claims: Any) -> str:
    from authlib.jose import jwt

    now = int(time.time())
    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "user-1",
        "iat": now,
        "exp": now + 300,
        **claims,
    }
    token = jwt.encode({"alg": "RS256", "kid": "test-key"}, payload, rsa["key"])
    return token.decode() if isinstance(token, bytes) else str(token)


def _oidc_client(
    tmp_path: Path, rsa: dict[str, Any], roles_claim: str = "realm_access.roles"
) -> TestClient:
    app = create_app(
        make_settings(
            tmp_path,
            auth_mode="oidc",
            oidc_issuer=ISSUER,
            oidc_audience=AUDIENCE,
            oidc_roles_claim=roles_claim,
        )
    )
    fetched: list[str] = []

    def fake_fetch(url: str) -> dict[str, Any]:
        fetched.append(url)
        if url.endswith("/.well-known/openid-configuration"):
            return {"jwks_uri": f"{ISSUER}/protocol/openid-connect/certs"}
        return rsa["jwks"]

    app.state.oidc = auth.OidcVerifier(ISSUER, AUDIENCE, roles_claim, fetch_json=fake_fetch)
    app.state.oidc_fetched = fetched
    return TestClient(app)


def test_oidc_roles_come_from_the_token_claim(tmp_path: Path, rsa: dict[str, Any]) -> None:
    c = _oidc_client(tmp_path, rsa)
    admin = _jwt(rsa, realm_access={"roles": ["offline_access", "admin", "scientist"]})
    assert c.get("/api/me", headers=_bearer(admin)).json()["role"] == "admin"  # highest known role
    sci = _jwt(rsa, realm_access={"roles": ["scientist"]})
    assert c.get("/api/config/layers", headers=_bearer(sci)).status_code == 403
    # the development role header changes nothing in OIDC mode (Track H item 1)
    with_header = {**_bearer(sci), "X-Dev-Role": "admin"}
    assert c.get("/api/config/layers", headers=with_header).status_code == 403
    assert c.get("/api/me", headers=with_header).json()["role_switch"] is False
    none = _jwt(rsa, realm_access={"roles": ["uma_authorization"]})
    assert c.get("/api/me", headers=_bearer(none)).status_code == 403
    # the JWKS was fetched once from the issuer and cached
    assert c.app.state.oidc_fetched[0].startswith(ISSUER)  # type: ignore[attr-defined]
    assert c.app.state.oidc_fetched.count(f"{ISSUER}/protocol/openid-connect/certs") == 1  # type: ignore[attr-defined]


def test_oidc_rejects_expired_wrong_audience_and_wrong_issuer(
    tmp_path: Path, rsa: dict[str, Any]
) -> None:
    c = _oidc_client(tmp_path, rsa)
    expired = _jwt(
        rsa, exp=int(time.time()) - 120, realm_access={"roles": ["admin"]}
    )  # past the leeway
    assert c.get("/api/me", headers=_bearer(expired)).status_code == 401
    wrong_aud = _jwt(rsa, aud="other-api", realm_access={"roles": ["admin"]})
    assert c.get("/api/me", headers=_bearer(wrong_aud)).status_code == 401
    wrong_iss = _jwt(rsa, iss="https://evil.example.test", realm_access={"roles": ["admin"]})
    assert c.get("/api/me", headers=_bearer(wrong_iss)).status_code == 401
    assert c.get("/api/me", headers=_bearer("not.a.jwt")).status_code == 401
    assert c.get("/api/me").status_code == 401
    refusals = [
        json.loads(line) for line in (tmp_path / "cache" / "audit.log").read_text().splitlines()
    ]
    assert all(e["action"] == "refused" and e["status"] == 401 for e in refusals)


def test_oidc_startup_needs_issuer_and_audience(tmp_path: Path) -> None:
    with pytest.raises(auth.AuthConfigError, match="OIDC_ISSUER"):
        create_app(make_settings(tmp_path, auth_mode="oidc"))


def test_refresh_notes_are_stripped_and_must_have_text(tmp_path: Path) -> None:
    """Human test session, item 13: a note of two spaces was accepted and audit-logged."""
    c = _client(tmp_path, auth_mode="none", dev_role="admin")
    for blank in ("", "   ", "\t\n"):
        r = c.post("/api/admin/refresh", json={"source": "pubchem", "note": blank})
        assert r.status_code == 422, blank
    r = c.post("/api/admin/refresh", json={"source": "pubchem", "note": "  recheck GHS  "})
    assert r.status_code == 202 and r.json()["audit_entry"]["note"] == "recheck GHS"
    notes = [
        e.get("note") for e in c.get("/api/audit").json() if e["action"] == "refresh_requested"
    ]
    assert notes == ["recheck GHS"]
