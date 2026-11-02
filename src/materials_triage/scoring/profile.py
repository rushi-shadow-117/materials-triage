"""Strict config loaders for the scorer.

The frozen `config.schema` loaders return None for unusable values and keep going, which is
right for the admin console. The scorer is stricter: a criterion that carries weight must
rest on `entered` entries, or loading fails with the entry named (`UnusableEntryError`).
Optional values with status `open` (the band gap conflict tolerance) load as None with a
note that the scorer writes onto every row they would have affected. Nothing here scores.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pydantic import Field

from materials_triage.config import schema as cs
from materials_triage.records import MissingReason, Provenance, ReferenceValue, Strict, Value

ENTERED = "entered"


class UnusableEntryError(ValueError):
    def __init__(self, path: str, status: Any, why: str) -> None:
        super().__init__(f"{path}: status {status!r} is not usable ({why})")
        self.path = path
        self.status = status


def _status(section: dict[str, Any] | None) -> Any:
    return None if section is None else section.get("status")


def _require_entered(section: dict[str, Any] | None, path: str, why: str) -> dict[str, Any]:
    if section is None or _status(section) != ENTERED:
        raise UnusableEntryError(path, _status(section), why)
    return section


# ----------------------------------------------------------------------------- scoring profile


@dataclass
class LoadedProfile:
    profile: cs.ScoringProfile
    evidence_tiers: dict[str, float]
    notes: list[str] = field(default_factory=list)
    source_refs: dict[str, str] = field(default_factory=dict)  # criterion -> config path
    standing_caveats: dict[str, str] = field(default_factory=dict)  # caveat id -> config path


def load_scoring_profile(path: Path) -> LoadedProfile:
    """Build the frozen `ScoringProfile` from a config file, refusing any weighted criterion
    whose entries are not `entered`."""
    data = cs.load_yaml(path)
    crit: dict[str, Any] = data.get("criteria", {})
    rel = f"{path.parent.name}/{path.name}"
    notes: list[str] = []
    refs: dict[str, str] = {}

    weights_section = _require_entered(
        data.get("weights"), f"{rel}#weights", "weights drive totals"
    )
    weights = {k: float(v) for k, v in weights_section["values"].items()}
    unknown = set(weights) - set(cs.CRITERIA)
    if unknown:
        raise UnusableEntryError(f"{rel}#weights", ENTERED, f"unknown criteria {sorted(unknown)}")
    for c in cs.CRITERIA:
        weights.setdefault(c, 0.0)

    def section(name: str) -> dict[str, Any]:
        sec = crit.get(name)
        if weights[name] > 0:
            sec = _require_entered(sec, f"{rel}#criteria.{name}", f"weight {weights[name]} > 0")
        refs[name] = f"{rel}#criteria.{name}"
        return sec or {}

    stab = section("stability")
    gap = section("band_gap")
    haz = section("hazard")
    simp = section("simplicity")
    evid = section("evidence")
    diel = section("dielectric_constant")
    section("deposition_method")
    section("cost")
    del haz  # the hazard policy file is loaded separately; the section only says it applies

    if gap.get("conflict_tolerance_ev") is None:
        notes.append(
            "band_gap.conflict_tolerance_ev is not set (status "
            f"{gap.get('conflict_tolerance_status', 'open')}); experimental and TBmBJ gaps are "
            "shown side by side but not compared"
        )
    target_band = None
    if _status(diel) == ENTERED and diel.get("target_band"):
        target_band = (float(diel["target_band"][0]), float(diel["target_band"][1]))
    elif weights["dielectric_constant"] > 0:
        raise UnusableEntryError(
            f"{rel}#criteria.dielectric_constant", _status(diel), "target band needed for weight"
        )
    else:
        notes.append(
            f"dielectric_constant target band unusable (status {_status(diel)}); weight stays 0"
        )
    anchors = data.get("anchors") or {}
    sens = data.get("sensitivity") or {}
    syn = data.get("synonyms") or {}
    profile = cs.ScoringProfile(
        name=str(data.get("profile", path.stem)),
        version=str(data.get("version", "0")),
        weights=weights,
        stability=cs.StabilitySettings(
            cutoff_mev_per_atom=_float_or_none(stab.get("cutoff_mev_per_atom")),
            near_cutoff_band_mev_per_atom=_float_or_none(stab.get("near_cutoff_band_mev_per_atom")),
            hull=str(stab.get("hull", "GGA_GGA+U_R2SCAN")).replace("mixed_", ""),
        ),
        band_gap=cs.BandGapSettings(
            policy=cs.BandGapPolicy(gap.get("policy", "best_available")),
            source_order=list(gap.get("source_order", ["experimental", "tbmbj", "pbe"])),
            soft_preference_start_ev=_float_or_none(gap.get("soft_preference_start_ev")),
            hard_min_ev=_float_or_none(gap.get("hard_min_ev")),
            hard_max_ev=_float_or_none(gap.get("hard_max_ev")),
            aggregate=cs.Aggregate(gap.get("aggregate_when_several_experimental_values", "median")),
            conflict_tolerance_ev=_float_or_none(gap.get("conflict_tolerance_ev")),
            on_conflict=cs.OnConflict(gap.get("on_conflict", "next_source")),
        ),
        dielectric_constant=cs.DielectricSettings(
            weight=weights["dielectric_constant"], target_band=target_band
        ),
        simplicity=cs.SimplicitySettings(
            max_elements=int(simp.get("max_elements", 3)),
            anion_policy=simp.get("anion_policy", "strict_oxide"),
            ternary_penalty=bool(simp.get("ternary_penalty", True)),
            ternary_penalty_size=_float_or_none(simp.get("ternary_penalty_size")),
        ),
        anchors=list(anchors.get("compositions", [])) if _status(anchors) == ENTERED else ["SiO2"],
        synonyms={k: list(v) for k, v in (syn.get("terms") or {}).items()}
        if _status(syn) == ENTERED
        else {},
        sensitivity_perturbation=float(sens.get("perturbation", 0.2))
        if _status(sens) == ENTERED
        else 0.2,
    )
    if weights["stability"] > 0 and profile.stability.cutoff_mev_per_atom is None:
        raise UnusableEntryError(f"{rel}#criteria.stability", ENTERED, "cutoff missing")
    tiers = {str(k): float(v) for k, v in (evid.get("tiers") or {}).items()}
    if weights["evidence"] > 0 and not tiers:
        raise UnusableEntryError(f"{rel}#criteria.evidence", _status(evid), "tiers missing")
    standing = {}
    if gap.get("standing_caveat"):
        standing["band_offsets_not_checked"] = f"{rel}#criteria.band_gap.standing_caveat"
    if stab.get("caveat"):
        standing["stability_cutoff_hull_mismatch"] = f"{rel}#criteria.stability.caveat"
    return LoadedProfile(
        profile=profile,
        evidence_tiers=tiers,
        notes=notes,
        source_refs=refs,
        standing_caveats=standing,
    )


def _float_or_none(x: Any) -> float | None:
    return None if x is None else float(x)


# ----------------------------------------------------------------------------- site profile


def load_site_profile(path: Path) -> cs.SiteProfile:
    """Everything the admin entered, including weight bounds and defaults."""
    data = cs.load_yaml(path)
    dep = data.get("deposition_methods") or {}
    tell = data.get("screen_cannot_tell_you") or {}
    wb = data.get("weight_bounds") or {}
    defaults = data.get("defaults") or {}
    bounds = {c: cs.Bounds() for c in cs.CRITERIA}
    if _status(wb) == ENTERED:
        for name, b in (wb.get("bounds") or {}).items():
            if name not in cs.CRITERIA:
                raise UnusableEntryError(f"{path.name}#weight_bounds", ENTERED, f"unknown {name}")
            bounds[name] = cs.Bounds(min=float(b["min"]), max=float(b["max"]))
    kw: dict[str, Any] = {}
    if _status(defaults) == ENTERED:
        for key in (
            "top_n_max",
            "default_view",
            "default_verbosity",
            "default_terminology",
            "radioactive_exclusion_locked",
            "exclude_non_commercial",
        ):
            if key in defaults:
                kw[key] = defaults[key]
    return cs.SiteProfile(
        name=str(data.get("name", "default")),
        weight_bounds=bounds,
        deposition_methods=list(dep.get("methods", [])) if _status(dep) == ENTERED else [],
        screen_cannot_tell_you=list(tell.get("items", [])) if _status(tell) == ENTERED else [],
        glossary=dict((data.get("glossary") or {}).get("terms", {}) or {}),
        **kw,
    )


def echa_attribution(path: Path) -> tuple[str, str] | None:
    """(text, config path) of the entered ECHA attribution line, if any."""
    data = cs.load_yaml(path)
    echa = (data.get("attribution") or {}).get("echa")
    if not isinstance(echa, dict) or _status(echa) != ENTERED:
        return None
    return str(echa["text"]), f"{path.name}#attribution.echa"


# ----------------------------------------------------------------------------- hazard policy


class TierEntry(Strict):
    element: str | None = None
    composition: str | None = None
    tier: str  # exclude | flag | unknown
    reason: str | None = None
    flag_text: str | None = None
    source_ref: str


class HazardPolicy(Strict):
    version: str
    exclude_elements: dict[str, TierEntry] = Field(default_factory=dict)
    flag_elements: dict[str, TierEntry] = Field(default_factory=dict)
    radioactive_elements: frozenset[str] = frozenset()
    radioactive_source_ref: str | None = None
    acute_exclude_codes: frozenset[str] = frozenset()
    acute_flag_codes: frozenset[str] = frozenset()
    acute_source_ref: str | None = None
    acute_compound_tiers: dict[str, TierEntry] = Field(default_factory=dict)
    acute_element_tiers: dict[str, TierEntry] = Field(default_factory=dict)
    process_hazard_template: str | None = None
    process_hazard_classifications: dict[str, str] = Field(default_factory=dict)  # comp -> ref
    unknown_rule_ref: str | None = None


def load_hazard_policy(path: Path) -> HazardPolicy:
    """Only `entered` rules apply. Every rule carries the config path that holds its source."""
    data = cs.load_yaml(path)
    tiers = data.get("tiers") or {}
    name = path.name

    def entered(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        return [e for e in (items or []) if e.get("status") == ENTERED]

    exclude = {
        e["element"]: TierEntry(
            element=e["element"],
            tier="exclude",
            reason=e.get("reason"),
            source_ref=f"{name}#tiers.exclude.{e['element']}",
        )
        for e in entered((tiers.get("exclude") or {}).get("entries"))
    }
    flag = {
        e["element"]: TierEntry(
            element=e["element"],
            tier="flag",
            reason=e.get("reason"),
            flag_text=e.get("flag_text"),
            source_ref=f"{name}#tiers.flag.{e['element']}",
        )
        for e in entered((tiers.get("flag") or {}).get("entries"))
    }
    radio = tiers.get("radioactive_exclude") or {}
    radioactive = (
        frozenset(str(x) for x in radio.get("elements", []))
        if _status(radio) == ENTERED
        else frozenset()
    )
    acute = tiers.get("acute_toxicity") or {}
    acute_ok = _status(acute) == ENTERED
    rule = acute.get("rule") or {}
    compound_tiers = {}
    element_tiers = {}
    if acute_ok:
        for e in entered(acute.get("compound_tiers")):
            compound_tiers[e["composition"]] = TierEntry(
                composition=e["composition"],
                tier=e["tier"],
                reason=e.get("note"),
                source_ref=f"{name}#tiers.acute_toxicity.compound_tiers.{e['composition']}",
            )
        for e in entered(acute.get("element_tiers")):
            element_tiers[e["element"]] = TierEntry(
                element=e["element"],
                tier=e["tier"],
                reason=e.get("reason"),
                source_ref=f"{name}#tiers.acute_toxicity.element_tiers.{e['element']}",
            )
    proc = tiers.get("process_hazard") or {}
    template = proc.get("caveat_template") or {}
    classifications = {
        e["composition"]: f"{name}#tiers.process_hazard.material_classifications.{e['composition']}"
        for e in entered(proc.get("material_classifications"))
    }
    unknown = data.get("unknown_hazard_rule") or {}
    return HazardPolicy(
        version=str(data.get("schema_version", 0)),
        exclude_elements=exclude,
        flag_elements=flag,
        radioactive_elements=radioactive,
        radioactive_source_ref=f"{name}#tiers.radioactive_exclude" if radioactive else None,
        acute_exclude_codes=frozenset(rule.get("exclude_if_any", [])) if acute_ok else frozenset(),
        acute_flag_codes=frozenset(rule.get("flag_if_any", [])) if acute_ok else frozenset(),
        acute_source_ref=f"{name}#tiers.acute_toxicity" if acute_ok else None,
        acute_compound_tiers=compound_tiers,
        acute_element_tiers=element_tiers,
        process_hazard_template=str(template["text"])
        if _status(template) == ENTERED and template.get("text")
        else None,
        process_hazard_classifications=classifications,
        unknown_rule_ref=f"{name}#unknown_hazard_rule" if _status(unknown) == ENTERED else None,
    )


# ----------------------------------------------------------------------------- reference values


@dataclass
class LoadedReferenceValues:
    entered: list[ReferenceValue]
    pending: list[ReferenceValue]  # shown as missing with their status; never scored


def load_reference_values(path: Path) -> LoadedReferenceValues:
    """Owner-entered values become records with source `config`. The raw hash is the file's
    sha256 and the timestamp is the entry's `entered_on`, so the provenance is deterministic."""
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    data = cs.load_yaml(path)
    entered: list[ReferenceValue] = []
    pending: list[ReferenceValue] = []
    for e in data.get("entries") or []:
        on = e.get("entered_on")
        when = (
            datetime(on.year, on.month, on.day, tzinfo=UTC)
            if isinstance(on, date)
            else datetime.fromisoformat(str(on)).replace(tzinfo=UTC)
        )
        src = e.get("source") or {}
        prov = Provenance(
            source="config",
            source_record_id=f"{path.name}#{e['id']}",
            raw_response_id=None,
            raw_sha256=sha,
            fetched_at=when,
            source_version=f"schema{data.get('schema_version', 0)}",
            url=src.get("url"),
            license=None,
        )
        usable = e.get("status") == ENTERED
        value = None
        if e.get("value") is not None and usable:
            value = Value[float](
                value=float(e["value"]), unit="eV", method="reference", provenance=prov
            )
        elif e.get("value") is not None:
            value = Value[float](
                value=None,
                unit="eV",
                method="reference",
                missing_reason=MissingReason.PENDING_VERIFICATION,
                provenance=prov,
            )
        rv = ReferenceValue(
            entry_id=str(e["id"]),
            composition=str(e["composition"]),
            property=str(e["property"]),
            value=value,
            value_range=tuple(float(x) for x in e["value_range"]) if e.get("value_range") else None,  # type: ignore[arg-type]
            form=str(e.get("form", "")),
            status=str(e.get("status")),
            citation=str(src.get("citation", "")),
            url=src.get("url"),
            provenance=prov,
        )
        (entered if usable else pending).append(rv)
    return LoadedReferenceValues(entered=entered, pending=pending)
