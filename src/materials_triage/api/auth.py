"""Roles come only from the bearer token. Nothing in a body, a query string, a header other
than Authorization, or chat text can change a role.

Modes (Settings.auth_mode):
- none: local development; every request carries `dev_role`.
- static: tokens from STATIC_TOKENS ("token:role,..."). Refused at startup when SITE_MODE is
  true unless ALLOW_STATIC_TOKENS is true.
- oidc: RS256 JWTs from OIDC_ISSUER for OIDC_AUDIENCE, validated against the issuer's JWKS;
  roles read from OIDC_ROLES_CLAIM (Keycloak realm roles by default).

Every refused request (401, 403) is written to the audit log.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import httpx
from fastapi import Depends, HTTPException, Request

from materials_triage.adapters import egress
from materials_triage.settings import Role, Settings

ROLES: tuple[Role, ...] = ("scientist", "fde", "admin")
CLOCK_LEEWAY_S = 60  # issuer and API clocks differ by a few seconds (a Docker VM, for one)


class AuthConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Principal:
    subject: str
    role: Role
    mode: str


# ----------------------------------------------------------------------------- audit log


class AuditLog:
    """Append-only JSON lines: admin actions and every refused request."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def write(self, action: str, principal: Principal | None, **detail: Any) -> dict[str, Any]:
        entry = {
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "action": action,
            "subject": principal.subject if principal else None,
            "role": principal.role if principal else None,
            **detail,
        }
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as f:
                f.write(json.dumps(entry, sort_keys=True, default=str) + "\n")
        return entry

    def entries(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]


# ----------------------------------------------------------------------------- startup


def check_startup(settings: Settings) -> None:
    """Site mode refuses static tokens unless the operator says so explicitly."""
    if settings.auth_mode == "static":
        if settings.site_mode and not settings.allow_static_tokens:
            raise AuthConfigError(
                "AUTH_MODE=static with SITE_MODE=true needs ALLOW_STATIC_TOKENS=true; "
                "use AUTH_MODE=oidc for a site deployment"
            )
        if not parse_static_tokens(settings.static_tokens):
            raise AuthConfigError("AUTH_MODE=static needs STATIC_TOKENS=token:role,...")
    if settings.auth_mode == "oidc" and (not settings.oidc_issuer or not settings.oidc_audience):
        raise AuthConfigError("AUTH_MODE=oidc needs OIDC_ISSUER and OIDC_AUDIENCE")


def parse_static_tokens(spec: str | None) -> dict[str, Role]:
    out: dict[str, Role] = {}
    for item in (spec or "").split(","):
        item = item.strip()
        if not item:
            continue
        token, _, role = item.partition(":")
        if role not in ROLES:
            raise AuthConfigError(f"STATIC_TOKENS: unknown role {role!r} (one of {ROLES})")
        out[token.strip()] = role
    return out


# ----------------------------------------------------------------------------- OIDC


class OidcVerifier:
    """Validates RS256 JWTs against the issuer's JWKS. The JWKS fetch is the only network call
    and goes to the issuer host alone (egress)."""

    def __init__(
        self,
        issuer: str,
        audience: str,
        roles_claim: str,
        fetch_json: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        self.issuer = issuer.rstrip("/")
        self.audience = audience
        self.roles_claim = roles_claim
        self._fetch_json = fetch_json or self._default_fetch
        self._jwks: dict[str, Any] | None = None

    def _default_fetch(self, url: str) -> dict[str, Any]:
        egress.check(url, {egress.host_of(self.issuer) or ""})
        response = httpx.get(url, timeout=10.0)
        response.raise_for_status()
        data = response.json()
        assert isinstance(data, dict)
        return data

    def jwks(self, *, refresh: bool = False) -> dict[str, Any]:
        if self._jwks is None or refresh:
            meta = self._fetch_json(f"{self.issuer}/.well-known/openid-configuration")
            self._jwks = self._fetch_json(str(meta["jwks_uri"]))
        return self._jwks

    def claims(self, token: str) -> dict[str, Any]:
        from authlib.jose import JsonWebToken  # type: ignore[import-untyped]
        from authlib.jose.errors import JoseError  # type: ignore[import-untyped]

        jwt = JsonWebToken(["RS256"])
        options = {
            "iss": {"essential": True, "value": self.issuer},
            "aud": {"essential": True, "value": self.audience},
            "exp": {"essential": True},
        }
        try:
            claims = jwt.decode(token, self.jwks(), claims_options=options)
            claims.validate(leeway=CLOCK_LEEWAY_S)
        except JoseError:
            try:  # one retry with fresh keys, for a rotated signing key
                claims = jwt.decode(token, self.jwks(refresh=True), claims_options=options)
                claims.validate(leeway=CLOCK_LEEWAY_S)
            except JoseError as e:
                raise HTTPException(status_code=401, detail=f"invalid token: {e.error}") from None
        return dict(claims)

    def role_of(self, claims: dict[str, Any]) -> Role | None:
        node: Any = claims
        for part in self.roles_claim.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        roles = node if isinstance(node, list) else [node] if isinstance(node, str) else []
        best: Role | None = None
        for r in ROLES:  # ascending rank; the highest known role wins
            if r in roles:
                best = r
        return best


# ----------------------------------------------------------------------------- dependency


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def current_principal(request: Request) -> Principal:
    """The caller's identity, from the configured auth mode. Role from the token only."""
    settings: Settings = request.app.state.settings
    audit: AuditLog = request.app.state.audit
    if settings.auth_mode == "none":
        return Principal(subject="dev", role=settings.dev_role, mode="none")
    token = _bearer(request)
    if token is None:
        audit.write("refused", None, status=401, path=request.url.path, reason="no bearer token")
        raise HTTPException(
            status_code=401,
            detail="bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if settings.auth_mode == "static":
        role = request.app.state.static_tokens.get(token)
        if role is None:
            audit.write("refused", None, status=401, path=request.url.path, reason="unknown token")
            raise HTTPException(status_code=401, detail="unknown token")
        return Principal(subject=f"static:{token[:4]}...", role=role, mode="static")
    verifier: OidcVerifier = request.app.state.oidc
    try:
        claims = verifier.claims(token)
    except HTTPException as e:
        audit.write("refused", None, status=401, path=request.url.path, reason=str(e.detail))
        raise
    role = verifier.role_of(claims)
    if role is None:
        audit.write(
            "refused",
            Principal(str(claims.get("sub", "?")), "scientist", "oidc"),
            status=403,
            path=request.url.path,
            reason="token carries no known role",
        )
        raise HTTPException(status_code=403, detail="token carries no known role")
    return Principal(subject=str(claims.get("sub", "?")), role=role, mode="oidc")


def require(*roles: Role) -> Callable[..., Principal]:
    """A dependency that admits only the named roles; a refusal is audit-logged."""

    def dependency(
        request: Request, principal: Annotated[Principal, Depends(current_principal)]
    ) -> Principal:
        if principal.role not in roles:
            request.app.state.audit.write(
                "refused",
                principal,
                status=403,
                path=request.url.path,
                required=list(roles),
            )
            raise HTTPException(
                status_code=403, detail=f"role {principal.role} may not do this; needs {roles}"
            )
        return principal

    return dependency


any_role = require(*ROLES)
console_roles = require("fde", "admin")
admin_only = require("admin")

# Dependency types for route signatures (FastAPI's Annotated form).
Current = Annotated[Principal, Depends(current_principal)]
AnyRole = Annotated[Principal, Depends(any_role)]
ConsoleRole = Annotated[Principal, Depends(console_roles)]
AdminRole = Annotated[Principal, Depends(admin_only)]
