"""A real run over the API: confirmed criteria in, progress events out, then the view, the
exports, the drill-down, and the relaxation list. No model, no network."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from materials_triage.records.bundle import UNRESOLVED_REASON
from tests.api.conftest import sse_events, wait_for_run

RANK = {
    "request_text": "Rank these for me as thin-film dielectrics",
    "profile": "oxide_dielectric_thin_film",
    "settings": {
        "mode": "candidate_list",
        "candidate_list": ["HfO2", "ZrO2", "Al2O3", "Unobtainium oxide"],
    },
}


def test_candidate_list_run_end_to_end(client: TestClient, tmp_path: Path) -> None:
    accepted = client.post("/api/runs", json=RANK)
    assert accepted.status_code == 202, accepted.text
    run_id = accepted.json()["run_id"]
    status = wait_for_run(client, run_id)
    assert status["status"] == "completed", status
    assert status["ranked"] == 3 and status["excluded"] == 0

    # progress: the stream replays every step, tagged code (no model configured), then done
    events = sse_events(client.get(f"/api/runs/{run_id}/events").text)
    steps = [e["data"]["step"] for e in events]
    assert steps[0] == "fetch_source" and "confirmed" in steps and steps[-1] == "done"
    assert {"start", "fetch", "score", "verify"} <= set(steps)
    assert {e["data"]["by"] for e in events} == {"code"}

    bundle = client.get(f"/api/runs/{run_id}").json()
    ranked = sorted((c for c in bundle["candidates"] if c["rank"]), key=lambda c: c["rank"])
    assert [c["composition"] for c in ranked] == ["Al2O3", "HfO2", "ZrO2"]
    assert bundle["criteria"]["unresolved_candidates"] == ["Unobtainium oxide"]
    assert [a["composition"] for a in bundle["anchors"]] == ["SiO2"]
    assert bundle["run"]["fetch_mode"] == "replay" and bundle["run"]["model_version"] is None

    # the PI view carries no record ids; the audit view does
    pi = client.get(f"/api/runs/{run_id}/view", params={"view": "pi_summary"}).json()
    assert [r["composition"] for r in pi["rows"]] == ["Al2O3", "HfO2", "ZrO2"]
    assert pi["anchors"][0]["rank"].startswith("would place") or pi["anchors"][0]["is_anchor"]
    assert "mp-" not in json.dumps(pi["rows"]) and "mp-" not in pi["markdown"]
    assert "Nothing is shown for: Unobtainium oxide (not a chemical" in pi["markdown"]
    assert pi["unresolved"][0]["text"] == "Unobtainium oxide"
    audit = client.get(f"/api/runs/{run_id}/view", params={"view": "audit"}).json()
    assert "mp-352" in json.dumps(audit["rows"])  # HfO2's ground state record
    assert audit["decision_log"] and audit["relaxations"] == []

    # exports
    csv_text = client.get(f"/api/runs/{run_id}/export", params={"format": "csv"}).text
    assert csv_text.splitlines()[0].startswith("run_id,composition,kind,rank")
    assert len([line for line in csv_text.splitlines() if line.strip()]) == 5  # header, 3, anchor
    md = client.get(f"/api/runs/{run_id}/export", params={"format": "md", "view": "audit"}).text
    assert md.startswith("# Audit view")
    assert client.get(f"/api/runs/{run_id}/export").json()["run"]["run_id"] == run_id

    # drill-down: HfO2's band gap, with the other sources the run holds
    drill = client.get(f"/api/runs/{run_id}/drill/HfO2/band_gap").json()
    assert (
        drill["record_id"]
        and drill["raw_sha256"]
        and drill["rule_ref"].endswith("#criteria.band_gap")
    )
    methods = {v["method"] for v in drill["other_values"]}
    assert "mp_summary" in methods or "pbe" in methods or any("experimental" in m for m in methods)
    assert any(v["used"] for v in drill["other_values"])
    assert (
        client.get(f"/api/runs/{run_id}/drill/HfO2/cost").json()["missing_reason"]
        == "no source wired"
    )
    assert client.get(f"/api/runs/{run_id}/drill/Nope/band_gap").status_code == 404

    # listing and the saved file
    runs = client.get("/api/runs").json()
    assert runs[0]["run_id"] == run_id and runs[0]["status"] == "completed"
    assert (tmp_path / "cache" / "runs" / f"{run_id}.json").exists()


def test_resolve_previews_clamps_and_a_vague_request_is_clarified(client: TestClient) -> None:
    body = {
        "profile": "oxide_dielectric_thin_film",
        "settings": {"mode": "discovery", "e_above_hull_max_mev": 2000, "weights": {"hazard": 0.0}},
    }
    r = client.post("/api/criteria/resolve", json=body).json()
    assert r["stability_cutoff_mev"] == 94.0 and r["effective_weights"]["hazard"] == 0.1
    assert sorted(c["setting"] for c in r["clamps"]) == ["e_above_hull_max_mev", "weights.hazard"]
    assert (
        client.post("/api/criteria/resolve", json={"settings": {"top_n": "many"}}).status_code
        == 422
    )

    vague = client.post(
        "/api/runs",
        json={"request_text": "", "profile": "oxide_dielectric_thin_film", "settings": {}},
    )
    assert vague.status_code == 422
    assert vague.json()["detail"]["missing_required"] == [
        "application",
        "chemistry",
        "property preference",
    ]


def test_parse_is_unavailable_without_a_model(client: TestClient) -> None:
    r = client.post("/api/parse", json={"request_text": "wide gap oxides"}).json()
    assert r["parse_available"] is False and "LLM_PROVIDER=none" in r["reason"]


def test_profiles_effective_config_and_health(client: TestClient) -> None:
    profiles = client.get("/api/profiles").json()
    assert profiles[0]["id"] == "oxide_dielectric_thin_film"
    assert {p["id"] for p in profiles} >= {"oxide_photocatalyst", "nitride_wide_gap"}
    nitride = client.get("/api/config/effective", params={"profile": "nitride_wide_gap"}).json()
    assert nitride["profile"] == "nitride_wide_gap"
    assert nitride["effective"]["profile"]["simplicity"]["anion_policy"] == "strict_nitride"
    assert client.get("/api/config/effective", params={"profile": "nope"}).status_code == 404
    health = client.get("/api/health").json()
    assert health["fetch_source"] == "cassettes" and health["llm_provider"] == "none"
    assert {s["source"] for s in health["sources"]} >= {"materials_project", "openalex", "pubchem"}
    mp = next(s for s in health["sources"] if s["source"] == "materials_project")
    assert mp["records"] and mp["allowed_host"] == "api.materialsproject.org"


def test_unknown_run_and_run_in_progress_states(client: TestClient) -> None:
    assert client.get("/api/runs/nope").status_code == 404
    assert client.get("/api/runs/nope/events").status_code == 404
    assert client.post("/api/runs/nope/cancel").status_code == 409


def test_gan_under_the_nitride_profile(client: TestClient) -> None:
    """Human test session, item 5: GaN's only gap is PBE 1.738 eV, below the nitride profile's
    2.4 eV PBE floor, so it stays excluded; nothing in the list sits inside the window."""
    body = {
        "request_text": "nitrides",
        "profile": "nitride_wide_gap",
        "settings": {"mode": "candidate_list", "candidate_list": ["AlN", "GaN", "Si3N4", "BN"]},
    }
    run_id = client.post("/api/runs", json=body).json()["run_id"]
    assert wait_for_run(client, run_id)["status"] == "completed"
    bundle = client.get(f"/api/runs/{run_id}").json()
    gan = next(c for c in bundle["candidates"] if c["composition"] == "GaN")
    assert gan["excluded"]["rule"] == "band_gap.hard_min"
    assert "1.738 eV (pbe) is below the 4 eV minimum" in gan["excluded"]["detail"]
    assert "pbe_only_below_window" not in gan["flags"]


def test_anchor_placement_reads_correctly(client: TestClient) -> None:
    """Human test session, item 9: "would rank 5 of 5" read as last while SiO2 outscored
    TiO2. The count includes the anchor, and the neighbours are named."""
    body = {
        "request_text": "rank my list",
        "settings": {
            "mode": "candidate_list",
            "candidate_list": [
                "HfO2",
                "ZrO2",
                "Al2O3",
                "SiO2",
                "TiO2",
                "ThO2",
                "BeO",
                "Y2O3",
                "Unobtainium",
            ],
        },
    }
    run_id = client.post("/api/runs", json=body).json()["run_id"]
    assert wait_for_run(client, run_id)["status"] == "completed"
    pi = client.get(f"/api/runs/{run_id}/view", params={"view": "pi_summary"}).json()
    assert [a["rank"] for a in pi["anchors"]] == ["would place 5th of 6, between ZrO2 and TiO2"]
    assert "- SiO2 (reference): would place 5th of 6, between ZrO2 and TiO2" in pi["markdown"]


def test_every_materials_project_value_links_to_its_page(client: TestClient) -> None:
    """Human test session, item 10: no HfO2 drill-down page linked to Materials Project;
    the hull records carried no URL."""
    run_id = client.post("/api/runs", json=RANK).json()["run_id"]
    assert wait_for_run(client, run_id)["status"] == "completed"
    page = "https://next-gen.materialsproject.org/materials/"
    stability = client.get(f"/api/runs/{run_id}/drill/HfO2/stability").json()
    assert stability["source_url"] == page + "mp-352"
    assert all(v["url"] == page + v["record_id"] for v in stability["other_values"])
    gap = client.get(f"/api/runs/{run_id}/drill/HfO2/band_gap").json()
    mp_rows = [v for v in gap["other_values"] if v["source"] == "materials_project"]
    assert mp_rows and all(v["url"] == page + v["record_id"] for v in mp_rows)
    bundle = client.get(f"/api/runs/{run_id}").json()
    missing: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            is_mp = node.get("source") == "materials_project" and "raw_sha256" in node
            if is_mp and not node.get("url"):
                missing.append(node["source_record_id"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(bundle)
    assert missing == []


def test_resolve_matches_names_and_reports_the_rest(client: TestClient) -> None:
    body = {
        "profile": "oxide_dielectric_thin_film",
        "settings": {
            "mode": "candidate_list",
            "candidate_list": ["hfo2", "hafnia", "zirconia", "xx1"],
        },
    }
    r = client.post("/api/criteria/resolve", json=body)
    assert r.status_code == 200
    out = r.json()
    assert out["settings"]["candidate_list"] == ["HfO2", "ZrO2"]
    assert out["unresolved"] == [{"text": "xx1", "reason": UNRESOLVED_REASON}]
    nothing = {
        "profile": "oxide_dielectric_thin_film",
        "settings": {"mode": "candidate_list", "candidate_list": ["xx1", "yy"]},
    }
    r = client.post("/api/criteria/resolve", json=nothing)
    assert r.status_code == 200 and r.json()["missing_required"] == ["candidate_list"]
    started = client.post("/api/runs", json={"request_text": "x", **nothing})
    assert started.status_code == 422
    detail = started.json()["detail"]
    assert detail.startswith("None of these matched") and "[" not in detail
