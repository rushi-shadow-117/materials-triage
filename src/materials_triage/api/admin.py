"""Read-only configuration views and the two admin actions: validating and saving a scoring
profile, and requesting a source refresh. Every number shown here comes from the loaded config
objects the scorer itself uses."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import text

from materials_triage.adapters import egress
from materials_triage.adapters.base import Source
from materials_triage.cli import wiring
from materials_triage.config import schema as cs
from materials_triage.config.schema import CONFIG_DIR, CoreConfig, QuerySettings, resolve
from materials_triage.provenance.store import make_engine
from materials_triage.scoring.profile import (
    HazardPolicy,
    UnusableEntryError,
    load_hazard_policy,
    load_scoring_profile,
)
from materials_triage.settings import Settings

from .schemas import (
    HazardRow,
    LayerRow,
    ProfileSaved,
    ProfileSummary,
    ProfileValidation,
    SourceHealth,
    ValidationIssue,
    WeightBoundRow,
)

PROFILES_DIR = CONFIG_DIR / "scoring_profiles"
SOURCE_HOSTS = {
    "materials_project": "api.materialsproject.org",
    "openalex": "api.openalex.org",
    "pubchem": "pubchem.ncbi.nlm.nih.gov",
}
SNAPSHOT_SOURCES = ("jarvis_dft_3d", "expt_gap")


# ----------------------------------------------------------------------------- profiles


def profile_path(profile_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", profile_id):
        raise FileNotFoundError(f"no scoring profile {profile_id!r}")
    path = PROFILES_DIR / f"{profile_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no scoring profile {profile_id!r}")
    return path


def list_profiles() -> list[ProfileSummary]:
    default = cs.default_paths()["scoring_profile"]
    out = []
    for path in sorted(PROFILES_DIR.glob("*.yaml"), key=lambda p: (p != default, p.name)):
        prof, notes = cs.scoring_profile_from_yaml(path)
        data = cs.load_yaml(path)
        out.append(
            ProfileSummary(
                id=path.stem,
                name=prof.name,
                version=prof.version,
                description=data.get("description"),
                notes=notes,
            )
        )
    return out


# ----------------------------------------------------------------------------- layers


def _fmt(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, dict | list):
        return (
            ", ".join(
                f"{k}={v:g}" if isinstance(v, float) else f"{k}={v}" for k, v in value.items()
            )
            if isinstance(value, dict)
            else ", ".join(map(str, value))
        )
    return str(value.value) if hasattr(value, "value") else str(value)


def layer_rows(layers: wiring.Layers, query: QuerySettings | None = None) -> list[LayerRow]:
    """Each setting that reaches the scorer, by the layer that set it: core (code default),
    site (bounds and defaults), profile (YAML), query (the request), and the effective value
    after resolve(). `set_by` names the layer whose value survived."""
    q = query or QuerySettings(profile=layers.profile.name)
    effective, clamps = resolve(layers.core, layers.site, layers.profile, q)
    clamped = {c.setting for c in clamps}
    core_profile = cs.ScoringProfile.model_fields
    rows: list[LayerRow] = []

    def row(
        key: str,
        core: Any,
        site: Any,
        profile: Any,
        query_value: Any,
        eff: Any,
        set_by: str,
    ) -> None:
        rows.append(
            LayerRow(
                key=key,
                core=_fmt(core),
                site=_fmt(site),
                profile=_fmt(profile),
                query=_fmt(query_value),
                effective=_fmt(eff),
                set_by=set_by,
            )
        )

    default_weights = core_profile["weights"].default_factory()  # type: ignore[call-arg, misc]
    for name in cs.CRITERIA:
        qv = q.weights.get(name)
        bounds = layers.site.weight_bounds.get(name)
        set_by = (
            "site (clamp)"
            if f"weights.{name}" in clamped
            else "query"
            if qv is not None
            else "profile"
        )
        row(
            f"weights.{name}",
            default_weights.get(name),
            f"{bounds.min:g} to {bounds.max:g}" if bounds else None,
            layers.profile.weights.get(name),
            qv,
            effective.weights.get(name),
            set_by,
        )
    hb = layers.site.stability_cutoff_bounds
    row(
        "e_above_hull_max_mev",
        None,
        f"{hb.min:g} to {hb.max:g}" if hb else None,
        layers.profile.stability.cutoff_mev_per_atom,
        q.e_above_hull_max_mev,
        effective.stability_cutoff_mev,
        "site (clamp)"
        if "e_above_hull_max_mev" in clamped
        else "query"
        if q.e_above_hull_max_mev is not None
        else "profile",
    )
    for key, prof_value in (
        ("band_gap_min_ev", layers.profile.band_gap.hard_min_ev),
        ("band_gap_max_ev", layers.profile.band_gap.hard_max_ev),
        ("max_elements", layers.profile.simplicity.max_elements),
    ):
        qv = getattr(q, key)
        eff = qv if qv is not None else prof_value
        row(key, None, None, prof_value, qv, eff, "query" if qv is not None else "profile")
    row(
        "anion_policy",
        cs.SimplicitySettings.model_fields["anion_policy"].default,
        None,
        layers.profile.simplicity.anion_policy,
        None,
        layers.profile.simplicity.anion_policy,
        "profile",
    )
    row(
        "top_n",
        QuerySettings.model_fields["top_n"].default,
        f"max {layers.site.top_n_max}",
        None,
        q.top_n,
        effective.top_n,
        "site (clamp)" if "top_n" in clamped else "query",
    )
    row(
        "exclude_radioactive",
        True,
        f"locked={layers.site.radioactive_exclusion_locked}",
        None,
        q.exclude_radioactive,
        effective.exclude_radioactive,
        "site (lock)" if "exclude_radioactive" in clamped else "query",
    )
    for key in ("view", "verbosity", "terminology"):
        qv = getattr(q, key)
        row(
            key,
            None,
            getattr(layers.site, f"default_{key}"),
            None,
            qv,
            getattr(effective, key),
            "query" if qv is not None else "site",
        )
    row(
        "units",
        QuerySettings.model_fields["units"].default,
        None,
        None,
        q.units,
        effective.units,
        "query",
    )
    row(
        "band_gap.policy",
        cs.BandGapSettings.model_fields["policy"].default,
        None,
        layers.profile.band_gap.policy,
        None,
        layers.profile.band_gap.policy,
        "profile",
    )
    return rows


# ----------------------------------------------------------------------------- hazard, bounds


def hazard_rows(policy: HazardPolicy) -> list[HazardRow]:
    rows: list[HazardRow] = []
    for el in sorted(policy.radioactive_elements):
        rows.append(
            HazardRow(
                subject=el,
                kind="element",
                tier="exclude",
                reason="no stable isotope",
                source_ref=policy.radioactive_source_ref or "",
            )
        )
    for table in (policy.exclude_elements, policy.flag_elements, policy.acute_element_tiers):
        for el, entry in sorted(table.items()):
            rows.append(
                HazardRow(
                    subject=el,
                    kind="element",
                    tier=entry.tier,
                    reason=entry.reason or entry.flag_text,
                    source_ref=entry.source_ref,
                )
            )
    for comp, entry in sorted(policy.acute_compound_tiers.items()):
        rows.append(
            HazardRow(
                subject=comp,
                kind="compound",
                tier=entry.tier,
                reason=entry.reason,
                source_ref=entry.source_ref,
            )
        )
    for comp, ref in sorted(policy.process_hazard_classifications.items()):
        rows.append(
            HazardRow(
                subject=comp,
                kind="compound",
                tier="process_hazard (caveat)",
                reason="material-specific process hazard text",
                source_ref=ref,
            )
        )
    return rows


def weight_bound_rows(site: cs.SiteProfile, profile: cs.ScoringProfile) -> list[WeightBoundRow]:
    return [
        WeightBoundRow(
            criterion=c,
            min=site.weight_bounds[c].min,
            max=site.weight_bounds[c].max,
            profile_default=profile.weights.get(c, 0.0),
        )
        for c in cs.CRITERIA
    ]


# ----------------------------------------------------------------------------- validation


def validate_profile_yaml(text_yaml: str, site: cs.SiteProfile) -> ProfileValidation:
    """Load the YAML with the scorer's own loader, then check it against the site bounds and
    preview the clamps a default query would get. Nothing is saved."""
    issues: list[ValidationIssue] = []
    try:
        data = yaml.safe_load(text_yaml)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f"line {mark.line + 1}" if mark is not None else "document"
        issues.append(ValidationIssue(level="error", path=where, message=f"not valid YAML: {e}"))
        return ProfileValidation(
            ok=False, profile=None, version=None, issues=issues, clamp_preview=[]
        )
    if not isinstance(data, dict):
        issues.append(
            ValidationIssue(level="error", path="document", message="the file must be a mapping")
        )
        return ProfileValidation(
            ok=False, profile=None, version=None, issues=issues, clamp_preview=[]
        )
    name = str(data.get("profile") or "")
    version = str(data.get("version", "0"))
    if not re.fullmatch(r"[a-z0-9_]+", name):
        issues.append(
            ValidationIssue(
                level="error", path="profile", message="profile must be a lowercase identifier"
            )
        )
    with tempfile.NamedTemporaryFile(
        "w", suffix=".yaml", dir=PROFILES_DIR.parent, delete=True
    ) as f:
        f.write(text_yaml)
        f.flush()
        try:
            loaded = load_scoring_profile(Path(f.name))
        except UnusableEntryError as e:
            issues.append(ValidationIssue(level="error", path=e.path, message=str(e)))
            return ProfileValidation(
                ok=False, profile=name or None, version=version, issues=issues, clamp_preview=[]
            )
        except (ValueError, KeyError, TypeError) as e:
            issues.append(ValidationIssue(level="error", path="document", message=str(e)))
            return ProfileValidation(
                ok=False, profile=name or None, version=version, issues=issues, clamp_preview=[]
            )
    for note in loaded.notes:
        issues.append(ValidationIssue(level="warning", path="criteria", message=note))
    for crit, weight in loaded.profile.weights.items():
        bounds = site.weight_bounds.get(crit, cs.Bounds())
        if weight > bounds.max or weight < bounds.min:
            issues.append(
                ValidationIssue(
                    level="error",
                    path=f"weights.values.{crit}",
                    message=(
                        f"{weight:g} is outside the site bounds {bounds.min:g} to {bounds.max:g}"
                    ),
                )
            )
    cutoff = loaded.profile.stability.cutoff_mev_per_atom
    hb = site.stability_cutoff_bounds
    if cutoff is not None and hb is not None and not (hb.min <= cutoff <= hb.max):
        issues.append(
            ValidationIssue(
                level="warning",
                path="criteria.stability.cutoff_mev_per_atom",
                message=(
                    f"{cutoff:g} is outside the site bounds {hb.min:g} to {hb.max:g}; runs clamp it"
                ),
            )
        )
    _, clamps = resolve(CoreConfig(), site, loaded.profile, QuerySettings(profile=name or "p"))
    ok = not any(i.level == "error" for i in issues)
    return ProfileValidation(
        ok=ok, profile=name or None, version=version, issues=issues, clamp_preview=clamps
    )


def save_profile_yaml(text_yaml: str, validation: ProfileValidation) -> ProfileSaved:
    """Save a validated profile as a new file; existing files are never overwritten."""
    if not validation.ok or validation.profile is None:
        raise ValueError("the profile has validation errors; fix them before saving")
    stem = f"{validation.profile}_v{validation.version}".replace(".", "_")
    path = PROFILES_DIR / f"{stem}.yaml"
    if path.exists() or (PROFILES_DIR / f"{validation.profile}.yaml").read_text() == text_yaml:
        raise FileExistsError(f"{path.name} already exists; raise `version` in the file")
    path.write_text(text_yaml if text_yaml.endswith("\n") else text_yaml + "\n")
    return ProfileSaved(
        id=stem,
        file=str(path.relative_to(CONFIG_DIR.parent)),
        profile=validation.profile,
        version=validation.version or "0",
    )


# ----------------------------------------------------------------------------- health


def source_health(settings: Settings, fetch_source: str) -> list[SourceHealth]:
    allowed = egress.allowed_hosts(settings)
    rows: list[SourceHealth] = []
    counts: dict[str, int] = {}
    last: dict[str, str] = {}
    if fetch_source == "cassettes":
        for raw in wiring.cassette_fetch().by_key.values():
            counts[raw.call.source.value] = counts.get(raw.call.source.value, 0) + 1
    else:
        try:
            with make_engine(settings.database_url).connect() as conn:
                for src, n, at in conn.execute(
                    text(
                        "select source, count(*), max(fetched_at) from triage.fetch_events "
                        "group by source"
                    )
                ):
                    counts[str(src)] = int(n)
                    if at is not None:
                        last[str(src)] = at.isoformat()
        except Exception as e:  # noqa: BLE001 - the health page reports, never raises
            rows.append(
                SourceHealth(
                    source="postgres",
                    status=f"unreachable: {type(e).__name__}",
                    fetch_source=fetch_source,
                    last_fetch=None,
                    records=None,
                    allowed_host=None,
                )
            )
    for name, host in SOURCE_HOSTS.items():
        n = counts.get(name)
        rows.append(
            SourceHealth(
                source=name,
                status=("recorded" if fetch_source == "cassettes" else "stored")
                if n
                else "no records",
                fetch_source=fetch_source,
                last_fetch=last.get(name),
                records=n,
                allowed_host=host if host in allowed else None,
            )
        )
    for name in SNAPSHOT_SOURCES:
        rows.append(
            SourceHealth(
                source=name,
                status="pinned snapshot",
                fetch_source="snapshot",
                last_fetch=None,
                records=None,
                allowed_host=None,
            )
        )
    return rows


def hazard_policy() -> HazardPolicy:
    return load_hazard_policy(cs.default_paths()["hazard_policy"])


def valid_source(name: str) -> bool:
    try:
        Source(name)
    except ValueError:
        return False
    return name in SOURCE_HOSTS
