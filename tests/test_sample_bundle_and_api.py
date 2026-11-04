"""The sample bundle is valid, the API stubs serve it, and the OpenAPI export is stable."""

import json
from pathlib import Path

from materials_triage.api.openapi import openapi_schema
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
        summary = c.group.polymorphs
        assert 0 < len(summary.top_by_hull) <= 5 and summary.total >= len(summary.top_by_hull)
        assert summary.ground_state is not None and summary.scored is not None
        for row in summary.top_by_hull:
            assert row.hull_energy is None or (
                row.hull_energy.value is not None or row.hull_energy.missing_reason is not None
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
        "/runs/{run_id}/view",
        "/runs/{run_id}/drill/{composition}/{criterion}",
        "/criteria/resolve",
        "/parse",
        "/config/effective",
        "/config/layers",
        "/profiles",
        "/admin/refresh",
        "/admin/profiles/validate",
        "/health",
        "/me",
    } <= routes
