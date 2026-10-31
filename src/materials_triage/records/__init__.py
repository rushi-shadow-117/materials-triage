"""Normalized record model.

Every number is a `Value` carrying its unit, method, missing reason, and provenance, so
invariant 1 (every number traces to a source record) is a type, not a convention. Missing
is `None` plus a reason; nothing is ever defaulted to zero. Values from different
functionals or methods sit side by side in dicts; nothing collapses until Phase 2 scoring
applies policy.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

T = TypeVar("T")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Provenance(Strict):
    source: str  # Source enum value
    source_record_id: str  # the source's own identifier (mp-643, JVASP-1169, CID 292779, ...)
    raw_response_id: UUID | None  # None only before the raw row is stored
    raw_sha256: str
    fetched_at: datetime
    source_version: str | None = None  # MP db_version, snapshot sha, OpenAlex none, ...
    url: str | None = None  # human-readable link
    license: str | None = None


class MissingReason(StrEnum):
    ABSENT = "absent"  # field not in the response
    NA_SENTINEL = "na_sentinel"  # source used a sentinel such as "na"
    NOT_COMPUTED = "not_computed"  # source says no calculation exists
    NOT_FETCHED = "not_fetched"  # replay mode and nothing stored
    PENDING_VERIFICATION = "pending_verification"  # config entry not yet usable


class Value(Strict, Generic[T]):
    value: T | None
    unit: str  # "eV", "eV/atom", "1" for dimensionless
    method: str | None = None  # functional, measurement, table name
    missing_reason: MissingReason | None = None
    provenance: Provenance

    @model_validator(mode="after")
    def _missing_has_reason(self) -> Value[T]:
        if self.value is None and self.missing_reason is None:
            raise ValueError("a missing value needs a missing_reason")
        if self.value is not None and self.missing_reason is not None:
            raise ValueError("a present value cannot carry a missing_reason")
        return self


class ObservationEvidence(StrEnum):
    MP_NOT_THEORETICAL = "mp_theoretical_false"
    MP_ICSD_IDS = "mp_icsd_ids"
    JARVIS_ICSD_IDS = "jarvis_icsd_ids"
    COD_HIT = "cod_hit"


class MatchRule(StrEnum):
    ICSD_INTERSECTION = "icsd_intersection"
    COMPOSITION_SPACEGROUP = "composition_spacegroup"


class Ids(Strict):
    mp: str | None = None
    mp_raw: str | None = None  # the alpha form as it appears in the raw body
    jarvis_jid: str | None = None
    oqmd: str | None = None
    cod: list[str] = Field(default_factory=list)
    icsd: list[int] = Field(default_factory=list)


class Polymorph(Strict):
    composition: str  # reduced formula (pymatgen)
    spacegroup_number: int | None
    spacegroup_symbol: str | None
    ids: Ids
    observed: bool | None  # None when no source speaks to it
    observation_evidence: list[ObservationEvidence] = Field(default_factory=list)
    hull_energy: dict[str, Value[float]] = Field(default_factory=dict)  # by thermo_type, eV/atom
    is_stable: dict[str, bool] = Field(default_factory=dict)  # by thermo_type
    hull_status_conflict: bool = False
    band_gap: dict[str, Value[float]] = Field(default_factory=dict)  # by method, eV
    dielectric: dict[str, Value[float]] = Field(
        default_factory=dict
    )  # e_total, e_ionic, e_electronic
    theoretical: bool | None = None
    deprecated: bool = False
    license: str | None = None
    matched_by: MatchRule | None = None
    provenance: list[Provenance] = Field(default_factory=list)

    def ground_state_energy(self, thermo_type: str) -> float | None:
        v = self.hull_energy.get(thermo_type)
        return None if v is None else v.value


class ExperimentalGap(Strict):
    composition: str
    value_ev: Value[float]
    table: str  # expt_gap | matbench_expt_gap
    role: str  # product | validation
    source_formula: str  # formula string as written in the table


class ExperimentalGapAggregate(Strict):
    composition: str
    n: int
    min: float
    median: float
    max: float
    values: list[ExperimentalGap]


class HazardRecord(Strict):
    composition: str
    cid: int | None
    cids_by_name: list[int]
    cids_by_formula: list[int]
    chosen_rule: str
    notifications_total: int | None
    notifications_not_classified: int | None
    h_codes: list[str]
    raw_strings: list[str]
    references: list[str]  # source names from PUG-View references (for attribution)
    echa_attribution_required: bool
    synonyms: list[str]
    provenance: Provenance


class LiteratureHit(Strict):
    openalex_id: str
    doi: str | None
    title: str | None
    year: int | None
    abstract_text: str | None
    abstract_index_sha256: str | None
    is_oa: bool | None
    license: str | None
    source_name: str | None
    landing_page_url: str | None
    query: str
    scope: str  # title_and_abstract | fulltext
    quote_verifiable: bool  # False for fulltext-scope hits
    cost_usd: float | None
    provenance: Provenance


class LiteratureSearchResult(Strict):
    composition: str
    query: str
    scope: str
    matched_total: int | None  # unfiltered count
    matched_with_abstract: int | None
    hits: list[LiteratureHit]


class ReferenceValue(Strict):
    entry_id: str
    composition: str
    property: str
    value: Value[float] | None
    value_range: tuple[float, float] | None
    form: str
    status: str
    citation: str
    url: str | None
    provenance: Provenance


class CompositionGroup(Strict):
    composition: str
    polymorphs: list[Polymorph]
    ground_state_mp: str | None  # mp id of the lowest mixed-hull polymorph
    ground_state_is_theoretical: bool | None
    lowest_observed_mp: str | None
    experimental_gaps: ExperimentalGapAggregate | None
    hazard: HazardRecord | None
    literature: LiteratureSearchResult | None


class SourceRecord(Strict):
    """What an adapter emits and the store persists: one normalized payload plus provenance."""

    kind: str  # polymorph | experimental_gap | hazard | literature | reference_value
    source_record_id: str
    composition: str | None
    payload: dict[str, Any]
    provenance: Provenance
    license: str | None = None
