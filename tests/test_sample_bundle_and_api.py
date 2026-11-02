"""The sample bundle is valid, the API stubs serve it, and the OpenAPI export is stable."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from materials_triage.api.openapi import app, openapi_schema
from materials_triage.records.bundle import EvidenceLabel, ProvenanceBundle

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "fixtures" / "bundles" / "sample_bundle.json"
EXPORTED = ROOT / "web" / "src" / "api" / "openapi.json"


def test_sample_bundle_validates_and_has_the_planned_shape() -> None:
    bundle = ProvenanceBundle.model_validate_json(SAMPLE.read_text())
    assert "illustrative" in (bundle.run.note or "")
    ranked = bundle.ranked()
    assert len(ranked) == 8 and [c.rank for c in ranked] == list(range(1, 9))
    excluded = {c.composition: c.excluded.rule for c in bundle.excluded() if c.excluded}
    assert excluded == {"ThO2": "hazard.radioactive_exclude", "BeO": "hazard.exclude"}
    assert [a.composition for a in bundle.anchors] == ["SiO2"] and bundle.anchors[
        0
    ].would_rank is not None
    assert any(
        "hull_status_conflict" in c.flags for c in bundle.candidates if c.composition == "Ta2O5"
    )
    assert {e.verified for e in bundle.evidence} == {True, False}
    assert all(e.label in EvidenceLabel for e in bundle.evidence)
    assert len(bundle.missing_properties) == 7
    assert bundle.verifier is not None and bundle.verifier.passed is False
    for c in bundle.candidates:
        for p in c.group.polymorphs:
            assert all(
                v.value is not None or v.missing_reason is not None for v in p.hull_energy.values()
            )


def test_api_stubs_serve_the_sample_bundle() -> None:
    client = TestClient(app)
    runs = client.get("/runs").json()
    assert runs and runs[0]["status"] == "completed"
    run_id = runs[0]["run_id"]
    body = client.get(f"/runs/{run_id}").json()
    assert body["bundle_version"] == 1 and len(body["candidates"]) == 10
    assert client.get("/runs/sample").status_code == 200
    assert client.get("/runs/nope").status_code == 404
    events = client.get(f"/runs/{run_id}/events").text
    assert "event: progress" in events and '"step": "done"' in events
    eff = client.get("/config/effective").json()
    assert eff["effective"]["weights"]["dielectric_constant"] == 0.0 and eff["clamps"] == []
    profiles = client.get("/profiles").json()
    assert profiles[0]["name"] == "gate_dielectric_on_si"
    accepted = client.post("/runs", json={"request_text": "oxide dielectrics"}).json()
    assert accepted["run_id"] == run_id
    assert (
        client.post(
            "/admin/refresh", json={"source": "materials_project", "reason": "test"}
        ).status_code
        == 202
    )


def test_openapi_export_is_current() -> None:
    """web/src/api/openapi.json must match the live schema so the generated types stay honest."""
    live = json.dumps(openapi_schema(), indent=2, sort_keys=True) + "\n"
    assert EXPORTED.read_text() == live, "run scripts/export_openapi.py and regenerate types.ts"
    routes = {p for p in openapi_schema()["paths"]}
    assert {
        "/runs",
        "/runs/{run_id}",
        "/runs/{run_id}/events",
        "/config/effective",
        "/profiles",
        "/admin/refresh",
        "/health",
    } <= routes
