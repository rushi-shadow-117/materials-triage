"""The four configuration layers and how they combine.

Precedence: core > site profile > scoring profile > query settings. Lower layers can only
set what higher layers allow, and query values are clamped into site bounds; every clamp is
returned so the UI can show it. Settings that shape prompts are enumerations mapped to fixed
template fragments (TEMPLATE_FRAGMENTS), so the same settings always produce the same prompt.

Entries loaded from the YAML files carry a `status`; only `entered` values are usable.
This module validates and resolves; it never scores.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = ROOT / "config"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ----------------------------------------------------------------------------- enums


class Verbosity(StrEnum):
    CONCISE = "concise"
    STANDARD = "standard"
    DETAILED = "detailed"


class Terminology(StrEnum):
    GENERAL = "general"
    TECHNICAL = "technical"


class Units(StrEnum):
    EV = "eV"
    MEV = "meV"


class View(StrEnum):
    PI_SUMMARY = "pi_summary"
    AUDIT = "audit"


class BandGapPolicy(StrEnum):
    PBE_ONLY = "pbe_only"
    BEST_AVAILABLE = "best_available"


class Aggregate(StrEnum):
    MEDIAN = "median"
    MINIMUM = "minimum"


class OnConflict(StrEnum):
    NEXT_SOURCE = "next_source"
    MINIMUM = "minimum"


class EntryStatus(StrEnum):
    ENTERED = "entered"
    PENDING_VERIFICATION = "pending_verification"
    PENDING_SIGNOFF = "pending_signoff"
    OPEN = "open"


# Every enum value maps to one fixed prompt/template fragment id. Fragments themselves live
# with the renderer and agent (Track B); the mapping is the contract.
TEMPLATE_FRAGMENTS: dict[str, dict[str, str]] = {
    "verbosity": {v.value: f"verbosity.{v.value}" for v in Verbosity},
    "terminology": {t.value: f"terminology.{t.value}" for t in Terminology},
    "units": {u.value: f"units.{u.value}" for u in Units},
    "view": {v.value: f"view.{v.value}" for v in View},
}

CRITERIA = (
    "stability",
    "band_gap",
    "hazard",
    "simplicity",
    "evidence",
    "dielectric_constant",
    "deposition_method",
    "cost",
)
OPTIONAL_CRITERIA = ("dielectric_constant", "deposition_method", "cost")  # weight 0 by default

# Names a request may use for a property, mapped to the criterion that covers it. A requested
# property that is not here has no configured source: the run carries it as unavailable and
# both views say so (Track F). Names only; no thresholds or chemistry.
PROPERTY_CRITERIA: dict[str, str] = {
    "stability": "stability",
    "thermodynamic stability": "stability",
    "energy above hull": "stability",
    "band gap": "band_gap",
    "gap": "band_gap",
    "wide band gap": "band_gap",
    "toxicity": "hazard",
    "non-toxic": "hazard",
    "hazard": "hazard",
    "simplicity": "simplicity",
    "simple composition": "simplicity",
    "simple compositions": "simplicity",
    "element count": "simplicity",
    "evidence": "evidence",
    "public evidence": "evidence",
    "published synthesis": "evidence",
    "synthesis": "evidence",
    "dielectric constant": "dielectric_constant",
    "permittivity": "dielectric_constant",
    "k": "dielectric_constant",
    "high-k": "dielectric_constant",
    "deposition method": "deposition_method",
    "cost": "cost",
}


# Phrases a request uses for a property that the exact table above does not list, matched by
# containment in order (the first hit wins). A None criterion names a property no source
# covers even though a word in it would otherwise match (thermal conductivity holds "thermal",
# conductivity is not a criterion). Names only; no thresholds or chemistry.
PROPERTY_PHRASES: tuple[tuple[str, str | None], ...] = (
    ("conductiv", None),
    ("thermal", None),
    ("dielectric", "dielectric_constant"),
    ("permittivity", "dielectric_constant"),
    ("high-k", "dielectric_constant"),
    ("band gap", "band_gap"),
    ("bandgap", "band_gap"),
    ("band-gap", "band_gap"),
    ("gap", "band_gap"),
    ("toxic", "hazard"),
    ("hazard", "hazard"),
    ("safe", "hazard"),
    ("radioactiv", "hazard"),
    ("stab", "stability"),
    ("thermodynamic", "stability"),
    ("hull", "stability"),
    ("simple", "simplicity"),
    ("composition", "simplicity"),
    ("element", "simplicity"),
    ("evidence", "evidence"),
    ("literature", "evidence"),
    ("publish", "evidence"),
    ("public", "evidence"),
    ("synthes", "evidence"),
    ("deposition", "deposition_method"),
    ("cost", "cost"),
    ("abundan", "cost"),
)


def _normalized(name: str) -> str:
    return " ".join(name.lower().split())


def criterion_for_property(name: str) -> str | None:
    """The criterion that covers a requested property name, or None when no source does.
    The exact table first, then the phrase rules; the researcher's words are kept as typed."""
    key = _normalized(name)
    if not key:
        return None
    if key in PROPERTY_CRITERIA:
        return PROPERTY_CRITERIA[key]
    for phrase, criterion in PROPERTY_PHRASES:
        if phrase in key:
            return criterion
    return None


def unavailable_properties(requested: list[str]) -> list[str]:
    """Requested property names no configured criterion covers, normalized and deduplicated."""
    out: list[str] = []
    for name in requested:
        key = _normalized(name)
        if key and criterion_for_property(key) is None and key not in out:
            out.append(key)
    return out


def covered_properties(requested: list[str]) -> list[tuple[str, str]]:
    """(name as typed, criterion) for every requested property a criterion covers, in order,
    deduplicated; what the confirm form shows as "understood as"."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name in requested:
        key = _normalized(name)
        criterion = criterion_for_property(key)
        if key and criterion is not None and key not in seen:
            seen.add(key)
            out.append((key, criterion))
    return out


# ----------------------------------------------------------------------------- core (code-owned)


class RefusalPolicy(Strict):
    wetlab: str = (
        "This assistant triages public data only; it does not plan, schedule, or perform "
        "laboratory work."
    )
    private_data: str = (
        "This assistant has no access to private or lab-internal data and will not use any."
    )
    estimates: str = (
        "This assistant does not estimate or predict values; missing data is reported as missing."
    )
    config_change: str = (
        "Settings and roles cannot be changed from the chat. Use the admin console or the "
        "configuration files."
    )


class StepBudget(Strict):
    """Limits for one agent step: model requests, tokens (input, output, cache), seconds."""

    max_tool_calls: int
    max_tokens: int
    max_seconds: int


def default_step_budgets() -> dict[str, StepBudget]:
    """Owner decision 2026-11-03: one budget per step, not one global pool. The classify
    step covers every abstract in the run (at most max_abstracts_per_candidate for each of
    the top_n candidates, with one retry each)."""
    return {
        "parse": StepBudget(max_tool_calls=3, max_tokens=8_000, max_seconds=60),
        "classify": StepBudget(max_tool_calls=120, max_tokens=150_000, max_seconds=300),
        "rationale": StepBudget(max_tool_calls=3, max_tokens=20_000, max_seconds=120),
        "relax": StepBudget(max_tool_calls=3, max_tokens=8_000, max_seconds=60),
    }


class CoreConfig(Strict):
    """Guardrails that no layer below can change."""

    refusals: RefusalPolicy = Field(default_factory=RefusalPolicy)
    citation_required_for_shortlist: bool = True
    verifier_required: bool = True
    evidence_labels: tuple[str, ...] = (
        "computed_only",
        "bulk_synthesized",
        "thin_film_deposited",
        "dielectric_characterized",
        "not_relevant",
        "no_abstract",
        "unclassified",
    )
    allowed_hosts: tuple[str, ...] = (
        "api.materialsproject.org",
        "api.openalex.org",
        "pubchem.ncbi.nlm.nih.gov",
        "www.crystallography.net",
    )
    step_budgets: dict[str, StepBudget] = Field(default_factory=default_step_budgets)
    max_abstracts_per_candidate: int = 5  # in the literature search's result order
    # Input limits (Track H). The API refuses a longer request or a longer candidate list
    # with a sentence; the web app shows the same limits before sending.
    max_request_chars: int = 2000
    max_candidates: int = 50


# ----------------------------------------------------------------------------- site profile (admin)


class Bounds(Strict):
    min: float = 0.0
    max: float = 1.0

    @model_validator(mode="after")
    def _ordered(self) -> Bounds:
        if self.min > self.max:
            raise ValueError("min must not exceed max")
        return self


class SourcePolicy(Strict):
    enabled: bool = True
    license: str | None = None
    commercial_ok: bool | None = None  # None = not yet verified
    ttl_days: int | None = None  # None = no expiry (snapshots)


class SiteProfile(Strict):
    name: str = "default"
    sources: dict[str, SourcePolicy] = Field(default_factory=dict)
    hazard_policy_path: str = "config/hazard_policy.yaml"
    weight_bounds: dict[str, Bounds] = Field(
        default_factory=lambda: {c: Bounds() for c in CRITERIA}
    )
    allowed_profiles: list[str] = Field(default_factory=list)  # empty = all
    default_view: View = View.PI_SUMMARY
    default_verbosity: Verbosity = Verbosity.STANDARD
    default_terminology: Terminology = Terminology.TECHNICAL
    glossary: dict[str, str] = Field(default_factory=dict)
    deposition_methods: list[str] = Field(default_factory=list)
    screen_cannot_tell_you: list[str] = Field(default_factory=list)
    retention_days: int | None = None
    top_n_max: int = 50
    radioactive_exclusion_locked: bool = True
    # meV/atom; a query cutoff is clamped into these; the max is the discovery hull prefilter
    stability_cutoff_bounds: Bounds | None = None


# ------------------------------------------------------------------- scoring profile (FDE)


class StabilitySettings(Strict):
    cutoff_mev_per_atom: float | None  # None = open, not usable
    near_cutoff_band_mev_per_atom: float | None
    hull: str = "GGA_GGA+U_R2SCAN"


class BandGapSettings(Strict):
    policy: BandGapPolicy = BandGapPolicy.BEST_AVAILABLE
    source_order: list[str] = Field(default_factory=lambda: ["experimental", "tbmbj", "pbe"])
    soft_preference_start_ev: float | None
    hard_min_ev: float | None = None
    hard_max_ev: float | None = None
    # PBE floor sent to the discovery API; the soft preference never is (Track F).
    discovery_pbe_floor_ev: float | None = None
    aggregate: Aggregate = Aggregate.MEDIAN
    # Experimental gaps are aggregated within one material form only, the first in this order
    # with a point value (owner decision 2026-11-04). Default: crystalline first.
    preferred_forms: tuple[str, ...] = (
        "crystalline_bulk",
        "compendium",
        "thin_film",
        "amorphous_film",
    )
    conflict_tolerance_ev: float | None = None  # None until derived (Phase 2 / Track E)
    on_conflict: OnConflict = OnConflict.NEXT_SOURCE


class DielectricSettings(Strict):
    weight: float = 0.0
    target_band: tuple[float, float] | None = None


class SimplicitySettings(Strict):
    max_elements: int = 3
    anion_policy: Literal["strict_oxide", "strict_nitride", "any"] = "strict_oxide"
    ternary_penalty: bool = True
    ternary_penalty_size: float | None = None


class ScoringProfile(Strict):
    name: str
    version: str = "0"
    weights: dict[str, float] = Field(
        default_factory=lambda: {c: (0.0 if c in OPTIONAL_CRITERIA else 1.0) for c in CRITERIA}
    )
    stability: StabilitySettings
    band_gap: BandGapSettings
    dielectric_constant: DielectricSettings = Field(default_factory=DielectricSettings)
    simplicity: SimplicitySettings = Field(default_factory=SimplicitySettings)
    anchors: list[str] = Field(default_factory=lambda: ["SiO2"])
    synonyms: dict[str, list[str]] = Field(default_factory=dict)  # composition -> search terms
    sensitivity_perturbation: float = 0.2
    # Structural dimensionalities (Larsen 2019) excluded by `structure.molecular`; [] = no rule
    structure_exclude_dimensionality: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def _weights_known(self) -> ScoringProfile:
        unknown = set(self.weights) - set(CRITERIA)
        if unknown:
            raise ValueError(f"unknown criteria in weights: {sorted(unknown)}")
        if any(w < 0 for w in self.weights.values()):
            raise ValueError("weights must be non-negative")
        return self


# --------------------------------------------------------------- query settings (scientist)


class QuerySettings(Strict):
    profile: str
    mode: Literal["discovery", "candidate_list"] = "discovery"
    candidate_list: list[str] = Field(default_factory=list)
    top_n: int = 10
    weights: dict[str, float] = Field(default_factory=dict)  # overrides within site bounds
    band_gap_min_ev: float | None = None
    band_gap_max_ev: float | None = None
    max_elements: int | None = None
    evidence_tier_min: str | None = None
    e_above_hull_max_mev: float | None = None  # None = the profile cutoff; site-bounded
    extra_anchors: list[str] = Field(default_factory=list)  # this run only; stay ranked
    exclude_radioactive: bool = True
    verbosity: Verbosity | None = None
    terminology: Terminology | None = None
    units: Units = Units.EV
    view: View | None = None


# ----------------------------------------------------------------------------- resolution


class Clamp(Strict):
    setting: str
    requested: Any
    applied: Any
    bound: str


class EffectiveConfig(Strict):
    core: CoreConfig
    site: SiteProfile
    profile: ScoringProfile
    query: QuerySettings
    weights: dict[str, float]
    verbosity: Verbosity
    terminology: Terminology
    units: Units
    view: View
    top_n: int
    exclude_radioactive: bool
    stability_cutoff_mev: float | None  # query value or profile cutoff, within site bounds
    fragments: dict[str, str]
    config_sha: str


def resolve(
    core: CoreConfig, site: SiteProfile, profile: ScoringProfile, query: QuerySettings
) -> tuple[EffectiveConfig, list[Clamp]]:
    """Combine the four layers. Core wins, then site, then profile, then query; query values
    outside site bounds are clamped and reported."""
    clamps: list[Clamp] = []
    if site.allowed_profiles and profile.name not in site.allowed_profiles:
        raise ValueError(f"profile {profile.name!r} is not allowed by the site profile")
    weights = dict(profile.weights)
    for name, requested in query.weights.items():
        if name not in CRITERIA:
            raise ValueError(f"unknown criterion {name!r}")
        bounds = site.weight_bounds.get(name, Bounds())
        applied = min(max(requested, bounds.min), bounds.max)
        if applied != requested:
            clamps.append(
                Clamp(
                    setting=f"weights.{name}",
                    requested=requested,
                    applied=applied,
                    bound=f"site.weight_bounds.{name}",
                )
            )
        weights[name] = applied
    top_n = query.top_n
    if top_n > site.top_n_max:
        clamps.append(
            Clamp(setting="top_n", requested=top_n, applied=site.top_n_max, bound="site.top_n_max")
        )
        top_n = site.top_n_max
    if top_n < 1:
        clamps.append(Clamp(setting="top_n", requested=top_n, applied=1, bound="min 1"))
        top_n = 1
    cutoff = (
        query.e_above_hull_max_mev
        if query.e_above_hull_max_mev is not None
        else profile.stability.cutoff_mev_per_atom
    )
    hull_bounds = site.stability_cutoff_bounds
    if cutoff is not None and hull_bounds is not None:
        applied = min(max(cutoff, hull_bounds.min), hull_bounds.max)
        if applied != cutoff:
            clamps.append(
                Clamp(
                    setting="e_above_hull_max_mev",
                    requested=cutoff,
                    applied=applied,
                    bound="site.stability_cutoff_bounds",
                )
            )
        cutoff = applied
    exclude_radioactive = query.exclude_radioactive
    if site.radioactive_exclusion_locked and not exclude_radioactive:
        clamps.append(
            Clamp(
                setting="exclude_radioactive",
                requested=False,
                applied=True,
                bound="site.radioactive_exclusion_locked",
            )
        )
        exclude_radioactive = True
    verbosity = query.verbosity or site.default_verbosity
    terminology = query.terminology or site.default_terminology
    view = query.view or site.default_view
    fragments = {
        "verbosity": TEMPLATE_FRAGMENTS["verbosity"][verbosity.value],
        "terminology": TEMPLATE_FRAGMENTS["terminology"][terminology.value],
        "units": TEMPLATE_FRAGMENTS["units"][query.units.value],
        "view": TEMPLATE_FRAGMENTS["view"][view.value],
    }
    payload = {
        "core": core.model_dump(mode="json"),
        "site": site.model_dump(mode="json"),
        "profile": profile.model_dump(mode="json"),
        "query": query.model_dump(mode="json"),
        "weights": weights,
        "top_n": top_n,
        "exclude_radioactive": exclude_radioactive,
        "stability_cutoff_mev": cutoff,
        "fragments": fragments,
    }
    sha = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    effective = EffectiveConfig(
        core=core,
        site=site,
        profile=profile,
        query=query,
        weights=weights,
        verbosity=verbosity,
        terminology=terminology,
        units=query.units,
        view=view,
        top_n=top_n,
        exclude_radioactive=exclude_radioactive,
        stability_cutoff_mev=cutoff,
        fragments=fragments,
        config_sha=sha,
    )
    return effective, clamps


# ----------------------------------------------------------------------------- YAML entry loading


class Entry(BaseModel):
    """Any owner-entered config entry: a value with status, source, and attribution.
    Extra keys are kept (extra='allow') because entries carry notes and quotes."""

    model_config = ConfigDict(extra="allow")

    status: EntryStatus
    entered_by: str | None = None
    entered_on: str | date | None = None  # YAML parses bare dates as date objects

    @property
    def usable(self) -> bool:
        return self.status == EntryStatus.ENTERED


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict) or data.get("schema_version") != 0:
        raise ValueError(f"{path} is not a schema_version 0 config file")
    return data


def entries_with_status(node: Any, path: str = "") -> list[tuple[str, Entry]]:
    """Every mapping carrying a status, validated as an Entry, with its path."""
    found: list[tuple[str, Entry]] = []
    if isinstance(node, dict):
        if "status" in node:
            found.append((path, Entry.model_validate(node)))
        for k, v in node.items():
            found.extend(entries_with_status(v, f"{path}/{k}"))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            found.extend(entries_with_status(v, f"{path}[{i}]"))
    return found


def scoring_profile_from_yaml(path: Path) -> tuple[ScoringProfile, list[str]]:
    """The scoring profile as the scorer loads it (scoring.profile.load_scoring_profile), with
    its notes. One loader serves the CLI, the API, the evals and the scorer (Track F)."""
    from materials_triage.scoring.profile import load_scoring_profile

    loaded = load_scoring_profile(path)
    return loaded.profile, list(loaded.notes)


def site_profile_from_yaml(path: Path) -> SiteProfile:
    """The site profile as the scorer loads it (scoring.profile.load_site_profile)."""
    from materials_triage.scoring.profile import load_site_profile

    return load_site_profile(path)


def default_paths() -> dict[str, Path]:
    return {
        "scoring_profile": CONFIG_DIR / "scoring_profiles" / "oxide_dielectric_thin_film.yaml",
        "site_profile": CONFIG_DIR / "site_profile.default.yaml",
        "hazard_policy": CONFIG_DIR / "hazard_policy.yaml",
        "reference_values": CONFIG_DIR / "reference_values.yaml",
    }
