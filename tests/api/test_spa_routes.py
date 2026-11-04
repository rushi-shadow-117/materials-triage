"""The API lives only under /api; every other path is the web app (human test session, Nov 4,
breaker 2: reloading a result or Run history showed raw JSON)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from materials_triage.api import app as app_mod
from tests.api.conftest import make_settings, wait_for_run

INDEX = '<!doctype html><html><body><div id="root"></div></body></html>'
RANK = {
    "request_text": "rank",
    "settings": {"mode": "candidate_list", "candidate_list": ["HfO2", "ZrO2"]},
}


@pytest.fixture
def served(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX)
    (dist / "assets" / "app.js").write_text("console.log(1)")
    monkeypatch.setattr(app_mod, "WEB_DIST", dist)
    return TestClient(app_mod.create_app(make_settings(tmp_path), serve_web=True))


def test_reloading_any_page_serves_the_app(served: TestClient) -> None:
    run_id = served.post("/api/runs", json=RANK).json()["run_id"]
    assert wait_for_run(served, run_id)["status"] == "completed"
    for path in (
        "/",
        "/runs",
        f"/runs/{run_id}",
        f"/runs/{run_id}/rows/HfO2/band_gap",
        "/console",
        "/console/profiles",
    ):
        r = served.get(path, headers={"Accept": "text/html"})
        assert r.status_code == 200 and r.text == INDEX, path
        assert r.headers["content-type"].startswith("text/html"), path
    assert served.get("/assets/app.js").text == "console.log(1)"


def test_the_api_answers_only_under_api(served: TestClient) -> None:
    assert served.get("/api/health").json()["status"] == "ok"
    assert isinstance(served.get("/api/runs").json(), list)
    # an unknown API path is a JSON 404, never the app
    missing = served.get("/api/no-such-route")
    assert missing.status_code == 404 and missing.headers["content-type"] == "application/json"
    assert served.get("/api").status_code == 404
    # the old unprefixed API paths are the app now, not JSON
    assert served.get("/health").text == INDEX
    assert served.get("/api/openapi.json").json()["info"]["title"] == "materials-triage"
