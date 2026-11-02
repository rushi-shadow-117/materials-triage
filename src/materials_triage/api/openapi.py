"""Route stubs that define the OpenAPI contract. Every route returns static data from the
sample bundle until Track C wires the pipeline, auth, and SSE progress."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from materials_triage.config.schema import (
    CoreConfig,
    QuerySettings,
    default_paths,
    resolve,
    scoring_profile_from_yaml,
    site_profile_from_yaml,
)
from materials_triage.records.bundle import ProvenanceBundle

ROOT = Path(__file__).resolve().parents[3]
SAMPLE_BUNDLE = ROOT / "fixtures" / "bundles" / "sample_bundle.json"

app = FastAPI(
    title="materials-triage",
    version="0.0.1",
    description=(
        "Triage candidate materials from public data. Every number traces to a source record."
    ),
)


class RunRequest(BaseModel):
    request_text: str
    profile: str = "gate_dielectric_on_si"
    settings: QuerySettings | None = None
    confirm: bool = False


class RunAccepted(BaseModel):
    run_id: str
    status: str


class ProfileSummary(BaseModel):
    name: str
    version: str
    notes: list[str]


class RefreshRequest(BaseModel):
    source: str
    reason: str


def load_sample() -> ProvenanceBundle:
    if not SAMPLE_BUNDLE.exists():
        raise HTTPException(status_code=503, detail="sample bundle not built")
    return ProvenanceBundle.model_validate_json(SAMPLE_BUNDLE.read_text())


@app.post("/runs", response_model=RunAccepted, status_code=202)
def create_run(body: RunRequest) -> RunAccepted:
    """Start a run (stub: returns the sample run id)."""
    sample = load_sample()
    return RunAccepted(run_id=str(sample.run.run_id), status="completed")


@app.get("/runs", response_model=list[RunAccepted])
def list_runs() -> list[RunAccepted]:
    sample = load_sample()
    return [RunAccepted(run_id=str(sample.run.run_id), status="completed")]


@app.get("/runs/{run_id}", response_model=ProvenanceBundle)
def get_run(run_id: str) -> ProvenanceBundle:
    sample = load_sample()
    if run_id not in ("sample", str(sample.run.run_id)):
        raise HTTPException(status_code=404, detail="run not found")
    return sample


@app.get("/runs/{run_id}/events")
async def run_events(run_id: str) -> StreamingResponse:
    """Server-sent progress events (stub: three fixed events then done)."""

    async def gen() -> AsyncIterator[str]:
        for step in ("parsed", "fetched", "scored", "done"):
            yield f"event: progress\ndata: {json.dumps({'run_id': run_id, 'step': step})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/config/effective")
def effective_config(profile: str = "gate_dielectric_on_si") -> dict[str, Any]:
    paths = default_paths()
    prof, notes = scoring_profile_from_yaml(paths["scoring_profile"])
    site = site_profile_from_yaml(paths["site_profile"])
    eff, clamps = resolve(CoreConfig(), site, prof, QuerySettings(profile=prof.name))
    return {
        "effective": eff.model_dump(mode="json"),
        "clamps": [c.model_dump() for c in clamps],
        "notes": notes,
    }


@app.get("/profiles", response_model=list[ProfileSummary])
def list_profiles() -> list[ProfileSummary]:
    out = []
    for path in sorted((ROOT / "config" / "scoring_profiles").glob("*.yaml")):
        prof, notes = scoring_profile_from_yaml(path)
        out.append(ProfileSummary(name=prof.name, version=prof.version, notes=notes))
    return out


@app.post("/admin/refresh", status_code=202)
def admin_refresh(body: RefreshRequest) -> dict[str, str]:
    """Logged, admin-only cache refresh (stub: accepted, not performed)."""
    return {
        "status": "accepted",
        "source": body.source,
        "note": "stub; Track C adds auth and the runner call",
    }


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "sources": {}}


def openapi_schema() -> dict[str, Any]:
    return app.openapi()
