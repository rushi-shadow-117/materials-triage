"""Browser tests against the served app: `materials-triage serve` on a free port with the built
web/dist, recorded cassettes, no model (LLM_PROVIDER=none), and static tokens. They skip when
Playwright's Chromium is not installed or web/dist is not built."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "web" / "dist"
TOKENS = {"scientist": "sci-e2e", "fde": "fde-e2e", "admin": "adm-e2e"}
SHOTS = ROOT / ".data-cache" / "e2e-screenshots"

pytestmark = pytest.mark.e2e


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            browser.close()
        return True
    except Exception:  # noqa: BLE001 - no browser binary means skip, not fail
        return False


@pytest.fixture(scope="session")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    if not DIST.exists():
        pytest.skip("web/dist is not built (cd web && npm ci && npm run build)")
    if not _chromium_available():
        pytest.skip("Playwright Chromium is not installed (uv run playwright install chromium)")
    port = _free_port()
    cache = tmp_path_factory.mktemp("cache")
    env = {
        **os.environ,
        "LLM_PROVIDER": "none",
        "AUTH_MODE": "static",
        "STATIC_TOKENS": ",".join(f"{t}:{r}" for r, t in TOKENS.items()),
        "DATA_CACHE_DIR": str(cache),
        "FETCH_MODE": "replay",
        # unreachable on purpose: --fetch auto then uses the cassettes
        "DATABASE_URL": "postgresql+psycopg://nobody:nobody@127.0.0.1:1/none",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "materials_triage.cli", "serve", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 180  # the first /health builds the cassette index
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{base}/health", timeout=2.0).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.3)
    else:
        proc.kill()
        out = proc.stdout.read().decode() if proc.stdout else ""
        pytest.fail(f"server did not start:\n{out}")
    try:
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture
def page(server: str):  # type: ignore[no-untyped-def]
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        pg = context.new_page()
        pg.set_default_timeout(30_000)
        yield pg
        context.close()
        browser.close()


def sign_in(page, server: str, role: str) -> None:  # type: ignore[no-untyped-def]
    page.goto(server + "/")
    page.get_by_label("bearer token").fill(TOKENS[role])
    page.get_by_role("button", name="Sign in").click()
    page.get_by_text(f"Role: {role}").wait_for()


def shot(page, name: str) -> Path:  # type: ignore[no-untyped-def]
    SHOTS.mkdir(parents=True, exist_ok=True)
    path = SHOTS / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    return path
