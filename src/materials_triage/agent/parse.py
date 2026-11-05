"""Parse and confirm: the request becomes QuerySettings, or a fixed refusal.

The model fills ParsedRequest; code builds QuerySettings (profile is a CLI choice), runs
`resolve`, and reports every default it applied and every clamp. An out-of-scope category
ends the run with the matching CoreConfig refusal text; nothing is fetched. No-LLM mode reads
the same QuerySettings from a criteria file.
"""

from __future__ import annotations

import dataclasses
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError
from pymatgen.core.periodic_table import Element

from materials_triage.adapters.common import try_reduced_formula
from materials_triage.config.limits import split_candidate_text
from materials_triage.config.schema import (
    Clamp,
    CoreConfig,
    EffectiveConfig,
    QuerySettings,
    ScoringProfile,
    SiteProfile,
    resolve,
    unavailable_properties,
)
from materials_triage.records.bundle import UNRESOLVED_REASON as UNRESOLVED_REASON

from . import loop, prompts
from .llm import LLMClient
from .tools import PARSE_REQUEST, OutOfScope, ParsedRequest, weights_dict

DEFAULTS: dict[str, Any] = {
    "mode": "discovery",
    "top_n": 10,
    "exclude_radioactive": True,
    "units": "eV",
}


@dataclass
class ParseOutcome:
    """Either a refusal or a resolved query, never both."""

    parsed_by: str  # llm | criteria_file
    refusal: str | None = None
    category: OutOfScope | None = None
    query: QuerySettings | None = None
    effective: EffectiveConfig | None = None
    clamps: list[Clamp] = field(default_factory=list)
    defaults_applied: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    requested_properties: list[str] = field(default_factory=list)  # as the request named them
    unresolved_candidates: list[str] = field(default_factory=list)
    unavailable_properties: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.refusal is None and self.query is not None and not self.missing_required


class CandidateListError(ValueError):
    pass


def name_table(synonyms: dict[str, list[str]] | None) -> dict[str, str]:
    """Lowercased formula keys and names from the profile's synonym table, to the formula:
    "hafnia" and "hfo2" both map to HfO2. The table is FDE-owned config; nothing is guessed."""
    table: dict[str, str] = {}
    for formula, names in (synonyms or {}).items():
        for key in (formula, *names):
            table.setdefault(" ".join(str(key).lower().split()), formula)
    return table


_SYMBOL = re.compile(r"[A-Z][a-z]?")
_FORMULA_CHARS = re.compile(r"[A-Za-z0-9().]+")


def strict_formula(text: str) -> str | None:
    """The reduced formula of a typed formula whose every symbol is a real element. Pymatgen
    alone reads unknown capitals as placeholder species ("SAPPHIRE" parses), so a typed
    entry must also tokenize into element symbols with no stray lowercase letter."""
    s = text.strip()
    if not _FORMULA_CHARS.fullmatch(s) or re.search(r"(?<![A-Z])[a-z]", s):
        return None
    symbols = _SYMBOL.findall(s)
    if not symbols or not all(Element.is_valid_symbol(x) for x in symbols):
        return None
    return try_reduced_formula(s)


def match_candidate(text: str, table: dict[str, str]) -> str | None:
    """A typed entry as a reduced formula: the synonym table first, case-insensitively (so
    "HFO2" is HfO2, not HO2F), then a strict formula parse; None when neither matches."""
    hit = table.get(" ".join(text.lower().split()))
    if hit is not None:
        return try_reduced_formula(hit)
    return strict_formula(text)


def split_candidates(
    formulas: list[str], synonyms: dict[str, list[str]] | None = None
) -> tuple[list[str], list[str]]:
    """(reduced formulas, entries that matched no formula or known name), in input order."""
    table = name_table(synonyms)
    out: list[str] = []
    bad: list[str] = []
    for f in formulas:
        reduced = match_candidate(f, table)
        if reduced is None:
            if f not in bad:
                bad.append(f)
        elif reduced not in out:
            out.append(reduced)
    return out, bad


def nothing_matched(names: list[str]) -> str:
    return (
        "None of these matched a chemical formula or a known name: "
        + ", ".join(names)
        + ". Check the spelling or use a formula such as HfO2."
    )


def normalize_candidates(
    formulas: list[str], synonyms: dict[str, list[str]] | None = None
) -> list[str]:
    """Strict form for typed answers (CLI confirmation): any unmatched entry raises."""
    out, bad = split_candidates(formulas, synonyms)
    if bad:
        raise CandidateListError("Not a chemical formula or a known name: " + ", ".join(bad) + ".")
    return out


def to_query_settings(
    parsed: ParsedRequest, *, profile: str, synonyms: dict[str, list[str]] | None = None
) -> tuple[QuerySettings, list[str], list[str]]:
    """QuerySettings from the model's output, the defaults applied, and the candidate names that
    are not chemical formulas (reported as not found; the run proceeds with the rest). Raises
    only when names were given and none resolves."""
    defaults: list[str] = []
    values: dict[str, Any] = {"profile": profile}
    for key, default in DEFAULTS.items():
        given = getattr(parsed, key)
        if given is None:
            values[key] = default
            defaults.append(f"{key}={default}")
        else:
            values[key] = given
    resolved, unresolved = split_candidates(parsed.candidate_list, synonyms)
    if unresolved and not resolved:
        # back to the model as a tool error, so it can ask or correct; never a Python list
        raise CandidateListError(nothing_matched(unresolved))
    values["candidate_list"] = resolved
    values["weights"] = weights_dict(parsed.weights)
    values["extra_anchors"] = normalize_candidates(parsed.extra_anchors, synonyms)
    for key in (
        "band_gap_min_ev",
        "band_gap_max_ev",
        "max_elements",
        "evidence_tier_min",
        "e_above_hull_max_mev",
        "verbosity",
        "terminology",
        "view",
    ):
        values[key] = getattr(parsed, key)
    return QuerySettings.model_validate(values), defaults, unresolved


def resolve_outcome(
    query: QuerySettings,
    *,
    parsed_by: str,
    core: CoreConfig,
    site: SiteProfile,
    profile: ScoringProfile,
    defaults: list[str],
    missing: list[str],
    unresolved: list[str] | None = None,
    unavailable: list[str] | None = None,
) -> ParseOutcome:
    effective, clamps = resolve(core, site, profile, query)
    defaults = list(defaults)
    for key in ("verbosity", "terminology", "view"):
        entry = f"{key}={getattr(effective, key).value}"
        if getattr(query, key) is None and entry not in defaults:
            defaults.append(entry)
    missing = list(missing)
    if (
        query.mode == "candidate_list"
        and not query.candidate_list
        and "candidate_list" not in missing
    ):
        missing.append("candidate_list")
    return ParseOutcome(
        parsed_by=parsed_by,
        query=query,
        effective=effective,
        clamps=clamps,
        defaults_applied=defaults,
        missing_required=missing,
        unresolved_candidates=list(unresolved or []),
        unavailable_properties=list(unavailable or []),
    )


CLARIFY_FIELDS = ["application", "chemistry", "property preference"]


def underspecified(parsed: ParsedRequest, query: QuerySettings) -> bool:
    """A discovery request that names no chemistry (candidates, elements, or a class such as
    oxides) and no property preference (a requested property or any property setting) is
    not run; the researcher is asked first, whatever the model chose (Track G, C1). A request
    that states only output settings (view, verbosity, terminology, units, top_n) is a
    follow-up on an earlier search and is not stopped by this rule."""
    if query.mode != "discovery" or query.candidate_list or query.extra_anchors:
        return False
    if parsed.requested_chemistry or parsed.requested_properties:
        return False
    property_settings = (
        query.weights,
        query.band_gap_min_ev,
        query.band_gap_max_ev,
        query.e_above_hull_max_mev,
        query.max_elements,
        query.evidence_tier_min,
    )
    if any(v not in (None, {}, []) for v in property_settings):
        return False
    output_settings = (
        parsed.view,
        parsed.verbosity,
        parsed.terminology,
        parsed.units,
        parsed.top_n,
    )
    return all(v is None for v in output_settings)


def make_handler(
    *, core: CoreConfig, site: SiteProfile, profile: ScoringProfile, cli_profile: str
) -> loop.Handler:
    def handler(parsed_model: BaseModel) -> loop.ToolOutcome:
        assert isinstance(parsed_model, ParsedRequest)
        parsed = parsed_model
        if parsed.out_of_scope is not None:
            text = getattr(core.refusals, parsed.out_of_scope.value)
            outcome = ParseOutcome(parsed_by="llm", refusal=text, category=parsed.out_of_scope)
            return loop.ToolOutcome(
                json.dumps({"refused": parsed.out_of_scope.value}),
                data=outcome,
                log_detail={"out_of_scope": parsed.out_of_scope.value},
            )
        try:
            query, defaults, unresolved = to_query_settings(
                parsed, profile=cli_profile, synonyms=profile.synonyms
            )
        except CandidateListError as e:
            return loop.ToolOutcome(str(e), is_error=True)
        try:
            outcome = resolve_outcome(
                query,
                parsed_by="llm",
                core=core,
                site=site,
                profile=profile,
                defaults=defaults,
                missing=list(
                    dict.fromkeys(
                        [
                            *parsed.missing_required,
                            *(CLARIFY_FIELDS if underspecified(parsed, query) else []),
                        ]
                    )
                ),
                unresolved=unresolved,
                unavailable=unavailable_properties(parsed.requested_properties),
            )
        except ValueError as e:
            return loop.ToolOutcome(str(e), is_error=True)
        outcome = dataclasses.replace(
            outcome, requested_properties=list(parsed.requested_properties)
        )
        content = {
            "clamps": [c.model_dump() for c in outcome.clamps],
            "defaults_applied": outcome.defaults_applied,
            "missing_required": outcome.missing_required,
            "unresolved_candidates": outcome.unresolved_candidates,
            "unavailable_properties": outcome.unavailable_properties,
        }
        return loop.ToolOutcome(
            json.dumps(content),
            data=outcome,
            log_detail={
                "mode": query.mode,
                "candidates": len(query.candidate_list),
                "clamps": len(outcome.clamps),
                "defaults_applied": outcome.defaults_applied,
                "missing_required": outcome.missing_required,
            },
        )

    return handler


def run_parse(
    *,
    client: LLMClient,
    request_text: str,
    core: CoreConfig,
    site: SiteProfile,
    profile: ScoringProfile,
    cli_profile: str,
    budget: loop.Budget,
) -> loop.StepResult:
    return loop.run_step(
        client=client,
        step="parse",
        system=prompts.system_prompt("parse"),
        user_text=f"Request from the researcher:\n{request_text}",
        tool=PARSE_REQUEST,
        handler=make_handler(core=core, site=site, profile=profile, cli_profile=cli_profile),
        budget=budget,
    )


def parse_from_settings(
    raw: dict[str, Any],
    *,
    core: CoreConfig,
    site: SiteProfile,
    profile: ScoringProfile,
    cli_profile: str,
    parsed_by: str = "form",
) -> ParseOutcome:
    """Settings a person typed (a criteria file, or the web confirm form) validated as
    QuerySettings and resolved. Candidate names that are not formulas are reported as
    unresolved; the run proceeds with the rest."""
    raw = dict(raw)
    raw.setdefault("profile", cli_profile)
    unresolved: list[str] = []
    # typed text is split by the one splitter in code (config/limits.py), never the browser
    for text_key, list_key in (
        ("candidate_text", "candidate_list"),
        ("extra_anchors_text", "extra_anchors"),
    ):
        if text_key in raw:
            text = raw.pop(text_key)
            raw[list_key] = split_candidate_text(str(text)) if text is not None else []
    if "candidate_list" in raw:
        # never fails the whole list: unmatched entries are reported, and a list with none
        # left is a missing candidate_list the confirm form asks for
        resolved, unresolved = split_candidates(
            [str(c) for c in raw["candidate_list"]], profile.synonyms
        )
        raw["candidate_list"] = resolved
    try:
        query = QuerySettings.model_validate(raw)
    except ValidationError as e:
        raise ValueError(str(e)) from None
    return resolve_outcome(
        query,
        parsed_by=parsed_by,
        core=core,
        site=site,
        profile=profile,
        defaults=[],
        missing=[],
        unresolved=unresolved,
    )


def parse_from_file(
    path: Path, *, core: CoreConfig, site: SiteProfile, profile: ScoringProfile, cli_profile: str
) -> ParseOutcome:
    """No-LLM mode: a YAML or JSON criteria file validated as QuerySettings."""
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must hold a mapping of query settings")
    try:
        return parse_from_settings(
            raw,
            core=core,
            site=site,
            profile=profile,
            cli_profile=cli_profile,
            parsed_by="criteria_file",
        )
    except ValueError as e:
        raise ValueError(f"{path}: {e}") from None
