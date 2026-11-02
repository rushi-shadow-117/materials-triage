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
    max_tool_calls: int = 40
    max_tokens: int = 60_000
    max_seconds: int = 300


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
    exclude_non_commercial: bool = True
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
    aggregate: Aggregate = Aggregate.MEDIAN
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
    """Build a ScoringProfile from a config/scoring_profiles/*.yaml file. Values whose entry
    is not `entered` become None (unusable) and are listed in the returned notes."""
    data = load_yaml(path)
    crit = data.get("criteria", {})
    notes: list[str] = []

    def usable(section: dict[str, Any], key: str) -> Any:
        if section.get("status") != "entered":
            notes.append(f"{key}: status {section.get('status')} -> unusable")
            return None
        return section.get(key)

    stab = crit.get("stability", {})
    gap = crit.get("band_gap", {})
    diel = crit.get("dielectric_constant", {})
    simp = crit.get("simplicity", {})
    anchors = data.get("anchors", {})
    profile = ScoringProfile(
        name=str(data.get("profile", path.stem)),
        version=str(data.get("version", "0")),
        stability=StabilitySettings(
            cutoff_mev_per_atom=usable(stab, "cutoff_mev_per_atom"),
            near_cutoff_band_mev_per_atom=usable(stab, "near_cutoff_band_mev_per_atom"),
            hull=str(stab.get("hull", "GGA_GGA+U_R2SCAN")).replace("mixed_", ""),
        ),
        band_gap=BandGapSettings(
            policy=BandGapPolicy(gap.get("policy", "best_available")),
            source_order=[
                s.replace("tbmbj", "tbmbj")
                for s in gap.get("source_order", ["experimental", "tbmbj", "pbe"])
            ],
            soft_preference_start_ev=usable(gap, "soft_preference_start_ev"),
            aggregate=Aggregate(gap.get("aggregate_when_several_experimental_values", "median")),
            conflict_tolerance_ev=gap.get("conflict_tolerance_ev"),
            on_conflict=OnConflict(gap.get("on_conflict", "next_source")),
        ),
        dielectric_constant=DielectricSettings(
            weight=float(diel.get("weight", 0.0)),
            target_band=tuple(diel["target_band"])
            if diel.get("status") == "entered" and diel.get("target_band")
            else None,
        ),
        simplicity=SimplicitySettings(
            max_elements=int(simp.get("max_elements", 3)),
            anion_policy=simp.get("anion_policy", "strict_oxide"),
            ternary_penalty=bool(simp.get("ternary_penalty", True)),
            ternary_penalty_size=simp.get("ternary_penalty_size"),
        ),
        anchors=list(anchors.get("compositions", ["SiO2"]))
        if anchors.get("status") == "entered"
        else ["SiO2"],
    )
    if diel.get("status") != "entered":
        notes.append(
            "dielectric_constant: target band unusable (status not entered); weight stays 0"
        )
    return profile, notes


def site_profile_from_yaml(path: Path) -> SiteProfile:
    data = load_yaml(path)
    dep = data.get("deposition_methods", {})
    tell = data.get("screen_cannot_tell_you", {})
    return SiteProfile(
        deposition_methods=list(dep.get("methods", [])) if dep.get("status") == "entered" else [],
        screen_cannot_tell_you=list(tell.get("items", []))
        if tell.get("status") == "entered"
        else [],
        glossary=dict((data.get("glossary") or {}).get("terms", {}) or {}),
    )


def default_paths() -> dict[str, Path]:
    return {
        "scoring_profile": CONFIG_DIR / "scoring_profiles" / "oxide_dielectric_thin_film.yaml",
        "site_profile": CONFIG_DIR / "site_profile.default.yaml",
        "hazard_policy": CONFIG_DIR / "hazard_policy.yaml",
        "reference_values": CONFIG_DIR / "reference_values.yaml",
    }
