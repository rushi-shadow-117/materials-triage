"""The provenance bundle: everything a run produced, in one validated document.

Renderers, the API, the UI, and the evals read only this. Scores and ranks are filled by
the scorer (Track A); evidence labels and rationale slots by the agent (Track B); the
verifier report by the verifier (Track B). Every number traces to a record through the
`Provenance` objects inside the summaries and criterion scores.

Polymorph rule (owner, 2026-11-02): the bundle carries a polymorph SUMMARY per composition
(ground state, lowest observed, observed and theoretical counts, the scored polymorph, and
the five lowest by hull energy). The full polymorph list stays in the provenance store and
is referenced by `PolymorphSummary.composition_id`, the pymatgen reduced formula that is the
`composition` column of `triage.records` (`Store.records_for(source="materials_project",
kind="mp_summary", composition=composition_id)`). `CompositionGroup` in `records` remains
the in-memory full object the scorer reads.

Every exclusion rule, flag, and caveat the scorer can emit is an enum here, so Track B
resolves text against a closed vocabulary.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import Field

from materials_triage.records import (
    ExperimentalGapAggregate,
    HazardRecord,
    LiteratureSearchResult,
    Provenance,
    ReferenceValue,
    Strict,
    Value,
)

BUNDLE_VERSION = 2


class FetchMode(StrEnum):
    LIVE = "live"
    REPLAY = "replay"
    REFRESH = "refresh"


# ----------------------------------------------------------------------------- vocabularies


class ExclusionRule(StrEnum):
    """Why a candidate (or a single polymorph) is out. Values are the strings shown to users."""

    STABILITY_CUTOFF = "stability.cutoff"
    BAND_GAP_HARD_MIN = "band_gap.hard_min"
    BAND_GAP_HARD_MAX = "band_gap.hard_max"
    HAZARD_RADIOACTIVE = "hazard.radioactive_exclude"
    HAZARD_EXCLUDE = "hazard.exclude"
    HAZARD_ACUTE_ELEMENT = "hazard.acute_toxicity.element"
    HAZARD_ACUTE_COMPOUND = "hazard.acute_toxicity.compound"
    HAZARD_ACUTE_GHS = "hazard.acute_toxicity.ghs"
    STRUCTURE_MOLECULAR = "structure.molecular"  # dimensionality 0 (Larsen 2019): molecules
    SIMPLICITY_MAX_ELEMENTS = "simplicity.max_elements"
    SIMPLICITY_ANION_POLICY = "simplicity.anion_policy"
    EVIDENCE_TIER_MIN = "evidence.tier_min"
    DATA_NO_SCORABLE_CRITERIA = "data.no_scorable_criteria"
    LICENSE_NON_COMMERCIAL = "license.non_commercial"  # polymorph level (adapter rule)
    DEPRECATED = "deprecated"  # polymorph level (adapter rule)


class Flag(StrEnum):
    """Row-level conditions the renderer shows beside the rank. Never change a score."""

    HULL_STATUS_CONFLICT = "hull_status_conflict"
    NEAR_CUTOFF = "near_cutoff"
    GROUND_STATE_IS_THEORETICAL = "ground_state_is_theoretical"
    POLYMORPH_REQUESTED = "polymorph_requested"  # the PI named an MP id; not the ground state
    BAND_GAP_CONFLICT = "band_gap_conflict"
    BAND_GAP_SINGLE_SOURCE = "band_gap_single_source"
    BAND_GAP_SOURCES_UNCOMPARED = "band_gap_sources_uncompared"  # tolerance not configured
    PBE_ONLY_BELOW_WINDOW = "pbe_only_below_window"  # kept between the PBE floor and the minimum
    HAZARD_FLAG = "hazard_flag"
    HAZARD_UNKNOWN = "hazard_unknown"
    PROCESS_HAZARD = "process_hazard"
    ANION_UNDETERMINED = "anion_undetermined"
    EVIDENCE_UNCLASSIFIED = "evidence_unclassified"
    ENRICHMENT_MISSING = "enrichment_missing"  # summary-level data only (discovery pass 1)


class CaveatId(StrEnum):
    """Caveat texts live in config; the id names the entry. `subject` carries the element or
    composition the text is about."""

    BAND_OFFSETS_NOT_CHECKED = "band_offsets_not_checked"
    STABILITY_CUTOFF_HULL_MISMATCH = "stability_cutoff_hull_mismatch"
    STABILITY_CUTOFF_OXIDE_CALIBRATED = "stability_cutoff_oxide_calibrated"  # anion policy
    EXPERIMENTAL_GAP_COMPOSITION_LEVEL = "experimental_gap_composition_level"
    EXPERIMENTAL_GAP_UNREFERENCED = "experimental_gap_unreferenced"
    PBE_ONLY_BELOW_WINDOW = "pbe_only_below_window"
    REFERENCE_VALUE_PENDING = "reference_value_pending"
    HAZARD_FLAG = "hazard_flag"
    HAZARD_UNKNOWN = "hazard_unknown"
    PROCESS_HAZARD = "process_hazard"
    ATTRIBUTION_ECHA = "attribution_echa"
    ANION_UNDETERMINED = "anion_undetermined"
    EVIDENCE_UNCLASSIFIED = "evidence_unclassified"
    ENRICHMENT_MISSING = "enrichment_missing"
    # data-state caveats that carry a row flag's meaning in words (owner text, Nov 4)
    BAND_GAP_CONFLICT = "band_gap_conflict"
    NEAR_CUTOFF = "near_cutoff"
    GROUND_STATE_IS_THEORETICAL = "ground_state_is_theoretical"


class Caveat(Strict):
    id: CaveatId
    subject: str | None = None  # element symbol or composition the caveat is about
    source_ref: str | None = None  # config entry path that holds the text


# ----------------------------------------------------------------------------- run


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
    # Track F; defaulted, so version-2 bundles written before these fields still validate.
    unresolved_candidates: list[str] = Field(default_factory=list)  # not a chemical formula
    stability_cutoff_mev: float | None = None  # effective hull cutoff after site bounds
    unavailable_properties: list[str] = Field(default_factory=list)  # no configured source


# ----------------------------------------------------------------------------- summaries


class PolymorphSummaryRow(Strict):
    """One polymorph as the bundle shows it. Values keep their provenance."""

    mp_id: str | None
    jarvis_jid: str | None = None
    spacegroup_number: int | None
    spacegroup_symbol: str | None
    hull_energy: Value[float] | None  # mixed hull, eV/atom
    is_stable: dict[str, bool] = Field(default_factory=dict)  # by thermo_type
    hull_status_conflict: bool = False
    observed: bool | None
    theoretical: bool | None
    band_gap: dict[str, Value[float]] = Field(default_factory=dict)
    dielectric: dict[str, Value[float]] = Field(default_factory=dict)
    excluded_rule: ExclusionRule | None = None  # stability.cutoff, license, deprecated
    dimensionality: Value[int] | None = None  # Larsen 2019; None = structure not fetched


class PolymorphSummary(Strict):
    composition_id: str  # reduced formula; key into triage.records.composition
    total: int
    observed_count: int
    theoretical_count: int
    unknown_count: int  # observed is None
    ground_state: PolymorphSummaryRow | None
    ground_state_is_theoretical: bool | None
    lowest_observed: PolymorphSummaryRow | None
    scored: PolymorphSummaryRow | None  # the polymorph the scorer used
    top_by_hull: list[PolymorphSummaryRow] = Field(default_factory=list)  # at most 5


class CompositionSummary(Strict):
    composition: str
    polymorphs: PolymorphSummary
    experimental_gaps: ExperimentalGapAggregate | None
    reference_values: list[ReferenceValue] = Field(default_factory=list)
    hazard: HazardRecord | None
    literature: LiteratureSearchResult | None


# ----------------------------------------------------------------------------- scoring


class CriterionScore(Strict):
    criterion: str  # one of config.schema.CRITERIA
    raw_value: float | None
    raw_unit: str | None
    source: str | None  # which record/method the raw value came from
    normalized: float | None  # 0..1, None when missing
    weight: float
    contribution: float  # normalized * weight, 0 when missing
    missing: bool
    missing_reason: str | None = None
    provenance: Provenance | None = None  # the record the raw value came from
    # every record whose value entered raw_value (an aggregate has several; one otherwise)
    used_record_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class Exclusion(Strict):
    rule: ExclusionRule
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
    # The scored polymorph's structural dimensionality, or why it is missing (Track G)
    dimensionality: Value[int] | None = None
    dimensionality_note: str | None = None


class Candidate(Strict):
    composition: str
    group: CompositionSummary
    score: ScoreBreakdown | None
    rank: int | None  # None when excluded
    excluded: Exclusion | None
    flags: list[Flag] = Field(default_factory=list)
    caveats: list[Caveat] = Field(default_factory=list)
    sensitivity: RankStability | None = None
    rationale_slot: str | None = None  # key into bundle.rationale


class Anchor(Strict):
    composition: str
    group: CompositionSummary
    score: ScoreBreakdown | None
    would_rank: int | None  # the place it would take if ranked, counting itself
    out_of: int  # ranked candidates plus this anchor
    excluded: Exclusion | None = None
    ranked_above: str | None = None  # the candidate just above that place
    ranked_below: str | None = None  # the candidate just below it
    flags: list[Flag] = Field(default_factory=list)
    caveats: list[Caveat] = Field(default_factory=list)


# ----------------------------------------------------------------------------- evidence


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
