"""The API enforces the core input limits with a 422 and a sentence, and splits typed
candidate text itself (Track H, item 3)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from materials_triage.config.schema import CoreConfig

CORE = CoreConfig()


def test_a_request_over_the_character_limit_is_refused_with_a_sentence(
    client: TestClient,
) -> None:
    ok = client.post("/api/parse", json={"request_text": "x" * CORE.max_request_chars})
    assert ok.status_code == 200
    r = client.post("/api/parse", json={"request_text": "x" * (CORE.max_request_chars + 1)})
    assert r.status_code == 422
    assert r.json()["detail"] == (
        "The request is 2,001 characters; the limit is 2,000. Shorten it and try again."
    )
    r = client.post(
        "/api/runs",
        json={
            "request_text": "x" * (CORE.max_request_chars + 1),
            "settings": {"mode": "discovery"},
        },
    )
    assert r.status_code == 422 and "2,001 characters" in r.json()["detail"]


def test_a_candidate_list_over_the_limit_is_refused_on_resolve_and_on_run(
    client: TestClient,
) -> None:
    names = [f"X{i}" for i in range(CORE.max_candidates)]
    ok = client.post(
        "/api/criteria/resolve",
        json={"settings": {"mode": "candidate_list", "candidate_list": names}},
    )
    assert ok.status_code == 200
    too_many = {"mode": "candidate_list", "candidate_text": "; ".join([*names, "X50"])}
    r = client.post("/api/criteria/resolve", json={"settings": too_many})
    assert r.status_code == 422
    assert r.json()["detail"] == (
        "51 candidates were given; the limit is 50. Remove some and try again."
    )
    r = client.post("/api/runs", json={"request_text": "", "settings": too_many})
    assert r.status_code == 422 and r.json()["detail"].startswith("51 candidates")


def test_typed_text_is_split_on_commas_semicolons_and_new_lines(client: TestClient) -> None:
    body = {"settings": {"mode": "candidate_list", "candidate_text": "HfO2; ZrO2\nAl2O3, hfo2"}}
    r = client.post("/api/criteria/resolve", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["settings"]["candidate_list"] == ["HfO2", "ZrO2", "Al2O3"]
    assert data["unresolved"] == []
    assert data["estimated_model_calls"]["total"] == 0  # no model in tests
    assert "No model configured" in data["estimated_model_calls"]["basis"]


def test_the_limits_are_readable_from_the_effective_config(client: TestClient) -> None:
    core = client.get("/api/config/effective").json()["effective"]["core"]
    assert core["max_request_chars"] == 2000 and core["max_candidates"] == 50
