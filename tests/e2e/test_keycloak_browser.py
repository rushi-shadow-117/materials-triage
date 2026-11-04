"""Browser sign-in through the Compose Keycloak, from the host (human test session, Nov 4,
breaker 3: Keycloak sat on an internal-only network and published no port).

Needs `docker compose --profile auth up -d keycloak` and Playwright Chromium; skips otherwise.
The web app is built with VITE_AUTH_MODE=oidc into a temporary folder and served on 8799,
the port the dev realm allows for this test.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Iterator

import httpx
import pytest

from tests.e2e.conftest import ROOT, _chromium_available, shot

pytestmark = [pytest.mark.e2e, pytest.mark.keycloak]

ISSUER = "http://localhost:8080/realms/materials-triage"
PORT = 8799


def _keycloak_up() -> bool:
    try:
        return httpx.get(f"{ISSUER}/.well-known/openid-configuration", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.fixture(scope="module")
def oidc_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    if not _keycloak_up():
        pytest.skip("Keycloak not reachable (docker compose --profile auth up -d keycloak)")
    if not _chromium_available():
        pytest.skip("Playwright Chromium is not installed")
    dist = tmp_path_factory.mktemp("dist-oidc")
    subprocess.run(
        ["npx", "vite", "build", "--outDir", str(dist), "--emptyOutDir"],
        cwd=ROOT / "web",
        env={**os.environ, "VITE_AUTH_MODE": "oidc", "VITE_OIDC_ISSUER": ISSUER},
        check=True,
        capture_output=True,
    )
    env = {
        **os.environ,
        "LLM_PROVIDER": "none",
        "AUTH_MODE": "oidc",
        "OIDC_ISSUER": ISSUER,
        "OIDC_AUDIENCE": "materials-triage-api",
        "WEB_DIST": str(dist),
        "DATA_CACHE_DIR": str(tmp_path_factory.mktemp("cache")),
        "DATABASE_URL": "postgresql+psycopg://nobody:nobody@127.0.0.1:1/none",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "materials_triage.cli", "serve", "--port", str(PORT)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{PORT}"
    try:
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{base}/api/health", timeout=2.0).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.5)
        else:
            raise AssertionError("the oidc server did not start")
        yield base
    finally:
        proc.terminate()
        proc.wait(timeout=20)


def test_scientist_signs_in_through_keycloak_from_the_host(page, oidc_server: str) -> None:  # type: ignore[no-untyped-def]
    page.goto(oidc_server + "/")
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url(lambda url: url.startswith("http://localhost:8080/"))
    page.fill("#username", "scientist")
    page.fill("#password", "scientist")
    page.click("#kc-login")
    page.get_by_text("Role: scientist").wait_for(timeout=30000)
    assert page.url.startswith(oidc_server)
    shot(page, "08-keycloak-signed-in")
