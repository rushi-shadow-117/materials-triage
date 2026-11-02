"""The provenance bundle: everything a run produced, in one validated document.

Renderers, the API, the UI, and the evals read only this. Scores and ranks are filled by
the scorer (Track A); evidence labels and rationale slots by the agent (Track B); the
verifier report by the verifier (Track B). Every number traces to a record through the
`Provenance` objects inside `CompositionGroup`.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import Field

from materials_triage.records import CompositionGroup, Provenance, Strict

BUNDLE_VERSION = 1


class FetchMode(StrEnum):
    LIVE = "live"
    REPLAY = "replay"
    REFRESH = "refresh"


class RunMetadata(Strict):
    run_id: UUID
    started_at: datetime
    finished_at: datetime | None
    config_sha: str  # sha256 over the effective layered config
    profile_name: str
    profile_version: str
    policy_version: str  # hazard policy version
    prompt_hash: str | None  # None in no-LLM mode
    model_version: str | None  # pinned dated model id, None in no-LLM mode
    provider: str | None  # anthropic | bedrock | openai_compatible | None
    source_versions: dict[str, str]  # e.g. materials_project -> 2026.09.28
    fetch_mode: FetchMode
    partial: bool
    partial_reasons: list[str] = Field(default_factory=list)
    budgets_used: dict[str, float] = Field(default_factory=dict)  # tool_calls, tokens, seconds
    budgets_limit: dict[str, float] = Field(default_factory=dict)
    note: str | None = None  # e.g. "sample bundle: scores illustrative"


class Clamp(Strict):
    """A query setting moved into the site's bounds, shown to the user."""

    setting: str
    requested: Any
    applied: Any
    bound: str  # which bound, e.g. "site.weight_bounds.band_gap.max"


class ConfirmedCriteria(Strict):
    """What the PI confirmed after parsing, plus the effective settings after clamping."""

    request_text: str
    parsed_by: str  # llm | criteria_file | form
    confirmed_at: datetime | None
    mode: str  # discovery | candidate_list
    candidate_list: list[str] = Field(default_factory=list)
    effective_settings: dict[str, Any]  # QuerySettings after resolve(), as a dict
    clamps: list[Clamp] = Field(default_factory=list)
    defaults_applied: list[str] = Field(default_factory=list)


class CriterionScore(Strict):
    criterion: str  # stability | band_gap | hazard | simplicity | evidence | dielectric_constant
    raw_value: float | None
    raw_unit: str | None
    source: str | None  # which record/method the raw value came from
    normalized: float | None  # 0..1, None when missing
    weight: float
    contribution: float  # normalized * weight, 0 when missing
    missing: bool
    missing_reason: str | None = None
    notes: list[str] = Field(default_factory=list)


class Exclusion(Strict):
    rule: str  # e.g. hazard.radioactive, stability.cutoff, license.non_commercial
    detail: str
    source_ref: str | None = None  # config entry id or record id that triggered it


class RankStability(Strict):
    rank_min: int
    rank_max: int
    rank_median: float
    perturbations: int
    stable: bool  # rank never left its band under the perturbation scheme


class ScoreBreakdown(Strict):
    total: float | None  # None when excluded
    criteria: list[CriterionScore]
    band_gap_source: str | None  # experimental_median | tbmbj | pbe | None
    band_gap_conflict: bool = False
    hull_status_conflict: bool = False
    ground_state_is_theoretical: bool | None = None
    near_cutoff: bool = False


class Candidate(Strict):
    composition: str
    group: CompositionGroup
    score: ScoreBreakdown | None
    rank: int | None  # None when excluded
    excluded: Exclusion | None
    flags: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)  # ids of caveat texts from config
    sensitivity: RankStability | None = None
    rationale_slot: str | None = None  # key into bundle.rationale


class Anchor(Strict):
    composition: str
    group: CompositionGroup
    score: ScoreBreakdown | None
    would_rank: int | None  # position it would take among ranked candidates
    out_of: int


class EvidenceLabel(StrEnum):
    COMPUTED_ONLY = "computed_only"
    BULK_SYNTHESIZED = "bulk_synthesized"
    THIN_FILM_DEPOSITED = "thin_film_deposited"
    DIELECTRIC_CHARACTERIZED = "dielectric_characterized"
    NOT_RELEVANT = "not_relevant"
    NO_ABSTRACT = "no_abstract"
    UNCLASSIFIED = "unclassified"  # no-LLM mode


class EvidenceHit(Strict):
    composition: str
    openalex_id: str
    label: EvidenceLabel
    deposition_method: str | None  # from the fixed enum in config, when stated
    supporting_sentence: str | None  # exact sentence from the abstract
    verified: bool  # verifier found the sentence verbatim in the stored abstract
    verifier_note: str | None = None
    quote_verifiable: bool = True  # False for fulltext-scope hits
    classifier_cache_key: str | None = None  # (abstract sha, prompt hash, model version)
    provenance: Provenance


class MissingPropertyMarker(Strict):
    """A property the screen never estimates, shown as missing on every row."""

    property: str  # breakdown_field | leakage_current_density | band_offsets | ...
    text: str  # from the site profile's screen_cannot_tell_you list
    source_entry: str  # config entry id


class DecisionLogEntry(Strict):
    at: datetime
    actor: str  # agent | pipeline | verifier | user | scorer
    step: str
    summary: str
    detail: dict[str, Any] = Field(default_factory=dict)


class RationaleSlot(Strict):
    slot: str  # e.g. candidate:HfO2:one_line
    text: str  # LLM text after verification; numbers and formulas are template tokens
    verified: bool
    removed_fragments: list[str] = Field(default_factory=list)


class VerifierFailure(Strict):
    kind: str  # unknown_record_id | unresolved_number | quote_mismatch | formula_not_in_bundle
    location: str  # slot or evidence id
    fragment: str
    action: str  # removed | hit_dropped


class VerifierReport(Strict):
    checked_slots: int
    checked_evidence: int
    failures: list[VerifierFailure] = Field(default_factory=list)
    passed: bool


class ProvenanceBundle(Strict):
    bundle_version: int = BUNDLE_VERSION
    run: RunMetadata
    criteria: ConfirmedCriteria
    candidates: list[Candidate]
    anchors: list[Anchor] = Field(default_factory=list)
    evidence: list[EvidenceHit] = Field(default_factory=list)
    missing_properties: list[MissingPropertyMarker] = Field(default_factory=list)
    decision_log: list[DecisionLogEntry] = Field(default_factory=list)
    rationale: dict[str, RationaleSlot] = Field(default_factory=dict)
    verifier: VerifierReport | None = None
    availability_events: list[dict[str, Any]] = Field(default_factory=list)

    def ranked(self) -> list[Candidate]:
        return sorted((c for c in self.candidates if c.rank is not None), key=lambda c: c.rank or 0)

    def excluded(self) -> list[Candidate]:
        return [c for c in self.candidates if c.excluded is not None]
