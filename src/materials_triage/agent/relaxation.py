"""Threshold relaxation: code enumerates the choices, the model picks, the researcher decides.

When fewer candidates than top_n survive the hard filters, code lists the admissible
relaxations of a query threshold (band_gap_min_ev, band_gap_max_ev, max_elements, and the
hull cutoff e_above_hull_max_mev within site bounds) with the exact new value and how many
candidates it adds, counted by re-scoring the already-fetched groups; or it states that none
is admissible. The model may only pick a
choice id and phrase it without digits. Nothing is applied until the researcher approves,
and an approved relaxation is a new query (new config sha, new run).
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import BaseModel
from pymatgen.core.composition import Composition

from materials_triage.config.schema import QuerySettings, SiteProfile
from materials_triage.records.bundle import (
    Candidate,
    DecisionLogEntry,
    ExclusionRule,
    ProvenanceBundle,
)

from . import loop, prompts
from .llm import LLMClient
from .tools import PROPOSE_RELAXATION, ProposeRelaxation

MAX_CHOICES_PER_SETTING = 3
MAX_RESCORES_PER_SETTING = 8  # bounded work: each try re-scores every fetched group


@dataclass(frozen=True)
class Relaxation:
    choice_id: str
    setting: str
    current: float | int | None
    proposed: float | int
    adds: int
    admits: tuple[str, ...]

    def describe(self) -> str:
        verb = "lowering" if self.setting == "band_gap_min_ev" else "raising"
        return f"{verb} {self.setting} to {self.proposed:g} adds {self.adds}"


def _raw(candidate: Candidate, criterion: str) -> float | None:
    if candidate.score is None:
        return None
    for cs in candidate.score.criteria:
        if cs.criterion == criterion:
            return cs.raw_value
    return None


# The ranked compositions a query would produce over the already-fetched groups.
Rescore = Callable[[QuerySettings], list[str]]


def _proposals(
    candidates: list[Candidate], query: QuerySettings, site: SiteProfile, cutoff_mev: float | None
) -> dict[str, list[float | int]]:
    """Per setting, the values nearest the current one that would admit an excluded row,
    nearest first. Only thresholds the query sets (or the effective hull cutoff) relax, and
    the hull cutoff never past the site maximum."""
    out: dict[str, set[float | int]] = {}
    hull_max = site.stability_cutoff_bounds.max if site.stability_cutoff_bounds else None
    for c in candidates:
        if c.excluded is None:
            continue
        gap = _raw(c, "band_gap")
        if gap is not None and query.band_gap_min_ev is not None and gap < query.band_gap_min_ev:
            out.setdefault("band_gap_min_ev", set()).add(math.floor(gap * 100) / 100)
        if gap is not None and query.band_gap_max_ev is not None and gap > query.band_gap_max_ev:
            out.setdefault("band_gap_max_ev", set()).add(math.ceil(gap * 100) / 100)
        hull = _raw(c, "stability")
        if hull is not None and cutoff_mev is not None:
            mev = math.ceil(hull * 1000.0 * 10) / 10
            if mev > cutoff_mev and (hull_max is None or mev <= hull_max):
                out.setdefault("e_above_hull_max_mev", set()).add(mev)
        if c.excluded.rule is ExclusionRule.SIMPLICITY_MAX_ELEMENTS:
            n = len(Composition(c.composition).elements)
            out.setdefault("max_elements", set()).add(n)
    ordered: dict[str, list[float | int]] = {}
    for setting, values in out.items():
        lowering = setting in ("band_gap_min_ev",)
        ordered[setting] = sorted(values, reverse=lowering)[:MAX_RESCORES_PER_SETTING]
    return ordered


def enumerate_or_explain(
    candidates: list[Candidate],
    query: QuerySettings,
    *,
    site: SiteProfile,
    cutoff_mev: float | None,
    rescore: Rescore,
) -> tuple[list[Relaxation], str | None]:
    """Every proposal carries the number of candidates it adds, counted by re-scoring the
    already-fetched groups under the relaxed setting (never estimated). When no proposal adds
    a candidate, the second value states why; the caller logs it."""
    before = set(rescore(query))
    choices: list[Relaxation] = []
    proposals = _proposals(candidates, query, site, cutoff_mev)
    for setting in sorted(proposals):
        current = cutoff_mev if setting == "e_above_hull_max_mev" else getattr(query, setting)
        previous: tuple[str, ...] = ()
        n = 0
        for value in proposals[setting]:
            after = rescore(query.model_copy(update={setting: value}))
            added = tuple(sorted(set(after) - before))
            if not added or added == previous:  # a value that admits nothing new is no choice
                continue
            previous = added
            n += 1
            choices.append(
                Relaxation(
                    choice_id=f"{setting}:{n}",
                    setting=setting,
                    current=current,
                    proposed=value,
                    adds=len(added),
                    admits=added,
                )
            )
            if n >= MAX_CHOICES_PER_SETTING:
                break
    if choices:
        return choices, None
    if not proposals:
        return [], (
            "no relaxation is admissible within site bounds: no query threshold or hull cutoff "
            "inside the site bounds would admit an excluded candidate"
        )
    return [], (
        "no relaxation is admissible within site bounds: relaxing each threshold admits no "
        "candidate once the other rules are applied"
    )


def log_summary(choices: list[Relaxation], statement: str | None) -> str:
    if statement is not None:
        return statement
    return f"relaxations available (code, not applied): {len(choices)}; " + "; ".join(
        c.describe() for c in choices
    )


def relaxations_from_bundle(bundle: ProvenanceBundle) -> list[Relaxation]:
    """The proposals the pipeline computed and logged (step "relaxation")."""
    for entry in bundle.decision_log:
        if entry.step == "relaxation":
            return [
                Relaxation(
                    choice_id=str(d["choice_id"]),
                    setting=str(d["setting"]),
                    current=d["current"],
                    proposed=d["proposed"],
                    adds=int(d["adds"]),
                    admits=tuple(d["admits"]),
                )
                for d in entry.detail.get("choices", [])
            ]
    return []


def apply_relaxation(query: QuerySettings, choice: Relaxation) -> QuerySettings:
    """A new QuerySettings; the caller runs resolve() again (new config sha, new run)."""
    return query.model_copy(update={choice.setting: choice.proposed})


def data_view(choices: list[Relaxation], request_text: str) -> str:
    lines = [f"researcher's request: {request_text}", "computed relaxations:"]
    for r in choices:
        lines.append(
            f"  id {r.choice_id}: {r.setting} from {r.current} to {r.proposed:g}; "
            f"adds {r.adds} candidate(s): {', '.join(r.admits)}"
        )
    return "\n".join(lines)


@dataclass
class RelaxResult:
    choice: Relaxation | None = None
    explanation: str | None = None
    entries: list[DecisionLogEntry] = field(default_factory=list)
    reason: str | None = None


def make_handler(choices: list[Relaxation]) -> loop.Handler:
    by_id = {c.choice_id: c for c in choices}

    def handler(parsed: BaseModel) -> loop.ToolOutcome:
        assert isinstance(parsed, ProposeRelaxation)
        if parsed.choice_id not in by_id:
            return loop.ToolOutcome(
                f"unknown choice_id {parsed.choice_id!r}; choose one of {sorted(by_id)}",
                is_error=True,
            )
        if any(ch.isdigit() for ch in parsed.explanation):
            return loop.ToolOutcome("explanation must contain no digits", is_error=True)
        return loop.ToolOutcome(
            json.dumps({"chosen": parsed.choice_id}),
            data=by_id[parsed.choice_id],
            log_detail={"choice_id": parsed.choice_id},
        )

    return handler


def run_relax(
    *,
    client: LLMClient,
    choices: list[Relaxation],
    request_text: str,
    budget: loop.Budget,
) -> RelaxResult:
    if not choices:
        return RelaxResult(reason="no admissible relaxation")
    result = loop.run_step(
        client=client,
        step="relax",
        system=prompts.system_prompt("relax"),
        user_text=prompts.data_block(data_view(choices, request_text)),
        tool=PROPOSE_RELAXATION,
        handler=make_handler(choices),
        budget=budget,
    )
    out = RelaxResult(entries=result.entries)
    if result.ok and isinstance(result.tool_input, ProposeRelaxation) and result.outcome:
        out.choice = result.outcome.data
        out.explanation = result.tool_input.explanation
    else:
        out.reason = result.reason
    return out
