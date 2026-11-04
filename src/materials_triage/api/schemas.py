"""Request and response bodies of the HTTP API. Bundles and view models come from the records
and render packages; these are the small shapes around them."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from materials_triage.config.schema import Clamp, QuerySettings
from materials_triage.records.bundle import ProvenanceBundle

RunStatus = Literal["queued", "running", "completed", "refused", "cancelled", "failed"]


class ParseRequest(BaseModel):
    request_text: str
    profile: str = "oxide_dielectric_thin_film"  # scoring profile file stem


class ParseResponse(BaseModel):
    """What the parse produced, for the confirm form. `parse_available` is False when no
    model is configured; the form is then filled by hand."""

    parse_available: bool
    parsed_by: str | None = None
    refusal: str | None = None
    refusal_category: str | None = None
    settings: dict[str, Any] | None = None  # QuerySettings as the form edits them
    clamps: list[Clamp] = Field(default_factory=list)
    defaults_applied: list[str] = Field(default_factory=list)
    missing_required: list[str] = Field(default_factory=list)
    unresolved_candidates: list[str] = Field(default_factory=list)
    unavailable_properties: list[str] = Field(default_factory=list)
    model: str | None = None
    reason: str | None = None  # why a parse failed or is unavailable


class ResolveRequest(BaseModel):
    profile: str = "oxide_dielectric_thin_film"
    settings: dict[str, Any] = Field(default_factory=dict)  # QuerySettings fields


class CallEstimateOut(BaseModel):
    """Model calls the run may make (agent/estimate.py): typical count, and the hard cap the
    step budgets enforce."""

    classify: int
    rationale: int
    total: int
    cap: int
    basis: str


class UnresolvedOut(BaseModel):
    """An entry that matched no formula or known name, with the reason shown on its chip."""

    text: str
    reason: str


class ResolveResponse(BaseModel):
    settings: dict[str, Any]
    effective_weights: dict[str, float]
    stability_cutoff_mev: float | None
    clamps: list[Clamp]
    defaults_applied: list[str]
    missing_required: list[str]
    unresolved_candidates: list[str]
    unresolved: list[UnresolvedOut] = Field(default_factory=list)
    config_sha: str
    estimated_model_calls: CallEstimateOut


class RunRequest(BaseModel):
    """Confirmed criteria. The settings are what the confirm form shows after any edits."""

    request_text: str
    profile: str = "oxide_dielectric_thin_film"
    settings: dict[str, Any] = Field(default_factory=dict)
    requested_properties: list[str] = Field(default_factory=list)
    parsed_by: str = "form"


class RunAccepted(BaseModel):
    run_id: str
    status: RunStatus


class RunSummary(BaseModel):
    run_id: str
    status: RunStatus
    profile: str | None = None
    request_text: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    partial: bool | None = None
    ranked: int | None = None
    excluded: int | None = None
    error: str | None = None


class ProgressEvent(BaseModel):
    at: str
    step: str
    summary: str
    actor: str
    by: Literal["code", "llm"]


class ProfileSummary(BaseModel):
    id: str  # file stem, the value every `profile` parameter takes
    name: str
    version: str
    description: str | None = None
    notes: list[str]


class LayerRow(BaseModel):
    key: str
    core: str | None
    site: str | None
    profile: str | None
    query: str | None
    effective: str | None
    set_by: str


class HazardRow(BaseModel):
    subject: str  # element or composition
    kind: Literal["element", "compound"]
    tier: str
    reason: str | None
    source_ref: str


class WeightBoundRow(BaseModel):
    criterion: str
    min: float
    max: float
    profile_default: float


class ValidationIssue(BaseModel):
    level: Literal["error", "warning"]
    path: str
    message: str


class ProfileValidation(BaseModel):
    ok: bool
    profile: str | None
    version: str | None
    issues: list[ValidationIssue]
    clamp_preview: list[Clamp]


class ProfileSaved(BaseModel):
    id: str
    file: str
    profile: str
    version: str


class RefreshRequest(BaseModel):
    source: str
    note: str = Field(min_length=1)


class RefreshAccepted(BaseModel):
    status: str
    source: str
    applies_to: str
    audit_entry: dict[str, Any]


class SourceHealth(BaseModel):
    source: str
    status: str
    fetch_source: str  # store | cassettes
    last_fetch: str | None
    records: int | None
    allowed_host: str | None


class HealthResponse(BaseModel):
    status: str
    fetch_source: str
    fetch_mode: str | None  # None: FETCH_MODE unset, recorded data only
    llm_status: str  # ok, none, missing_key, invalid_key, no_credit (agent/llm_status.py)
    llm_note: str  # the banner sentence; empty while the model is available
    llm_provider: str
    llm_model: str | None
    classify_mode: str
    auth_mode: str
    sources: list[SourceHealth]


class RelaxChoice(BaseModel):
    choice_id: str
    setting: str
    current: float | int | None
    proposed: float | int
    adds: int
    admits: list[str]
    text: str


class RelaxRequest(BaseModel):
    choice_id: str


class DrillValue(BaseModel):
    method: str
    value: str
    source: str
    record_id: str | None
    used: bool
    form: str | None = None  # experimental gaps: the material form (amorphous_film, ...)
    url: str | None = None  # the record's page (every Materials Project value links)


class DrillResponse(BaseModel):
    composition: str
    criterion: str
    label: str
    raw: str
    normalized: str
    weight: str
    contribution: str
    missing_reason: str | None
    source: str | None
    record_id: str | None
    method: str | None
    fetched_at: str | None
    raw_sha256: str | None
    source_version: str | None
    source_url: str | None
    rule_ref: str | None
    notes: list[str]
    other_values: list[DrillValue]


class Me(BaseModel):
    subject: str
    role: str
    auth_mode: str
    llm_status: str
    llm_note: str


BundleOut = ProvenanceBundle
QueryOut = QuerySettings
