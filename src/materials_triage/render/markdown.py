"""Markdown renderers for the two views. Templates hold words only; the view models hold
every number as a display string. A bundle from an LLM run renders only after verification."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from materials_triage.config.schema import SiteProfile, Terminology, Units
from materials_triage.records.bundle import ProvenanceBundle
from materials_triage.render import glossary
from materials_triage.render.caveats import CaveatConfig
from materials_triage.render.views import build

TEMPLATES = Path(__file__).parent / "templates"
ENV = Environment(
    loader=FileSystemLoader(str(TEMPLATES)),
    undefined=StrictUndefined,
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)


class UnverifiedBundleError(ValueError):
    pass


def options_from_bundle(bundle: ProvenanceBundle, site: SiteProfile) -> tuple[str, str]:
    """(units, terminology) the run was confirmed with; site defaults fill None."""
    settings = bundle.criteria.effective_settings
    units = settings.get("units") or Units.EV.value
    terminology = settings.get("terminology") or site.default_terminology.value
    return str(units), str(terminology)


def render(
    bundle: ProvenanceBundle,
    *,
    view: str,
    site: SiteProfile,
    caveats: CaveatConfig | None = None,
) -> str:
    if view not in ("pi_summary", "audit"):
        raise ValueError(f"unknown view {view!r}")
    if bundle.run.model_version is not None and bundle.verifier is None:
        raise UnverifiedBundleError("an LLM run must pass the verifier before rendering")
    units, terminology = options_from_bundle(bundle, site)
    run_view = build(bundle, caveats or CaveatConfig.load(), units=units)
    text = ENV.get_template(f"{view}.md.j2").render(
        bundle=bundle, run=bundle.run, criteria=bundle.criteria, view=run_view, units=units
    )
    if terminology == Terminology.GENERAL.value:
        text = glossary.apply(text, site.glossary)
    return text


def render_pi_summary(
    bundle: ProvenanceBundle, site: SiteProfile, caveats: CaveatConfig | None = None
) -> str:
    return render(bundle, view="pi_summary", site=site, caveats=caveats)


def render_audit(
    bundle: ProvenanceBundle, site: SiteProfile, caveats: CaveatConfig | None = None
) -> str:
    return render(bundle, view="audit", site=site, caveats=caveats)
