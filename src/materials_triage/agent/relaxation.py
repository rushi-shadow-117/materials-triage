"""Threshold relaxation: code enumerates the choices, the model picks, the researcher decides.

When fewer candidates than top_n survive the hard filters, code lists every admissible
relaxation of a query threshold (band_gap_min_ev, band_gap_max_ev, max_elements) with the
exact new value and how many already-fetched candidates it admits. The model may only pick a
choice id and phrase it without digits. Nothing is applied until the researcher approves,
and an approved relaxation is a new query (new config sha, new run).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from pydantic import BaseModel

from materials_triage.config.schema import QuerySettings
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
RULE_SETTING: dict[ExclusionRule, str] = {
    ExclusionRule.BAND_GAP_HARD_MIN: "band_gap_min_ev",
    ExclusionRule.BAND_GAP_HARD_MAX: "band_gap_max_ev",
    ExclusionRule.SIMPLICITY_MAX_ELEMENTS: "max_elements",
}
SETTING_CRITERION: dict[str, str] = {
    "band_gap_min_ev": "band_gap",
    "band_gap_max_ev": "band_gap",
    "max_elements": "simplicity",
}


@dataclass(frozen=True)
class Relaxation:
    choice_id: str
    setting: str
    current: float | int | None
    proposed: float | int
    adds: int
    admits: tuple[str, ...]

    def describe(self) -> str:
        verb = "raising" if self.setting in ("band_gap_max_ev", "max_elements") else "lowering"
        return f"{verb} {self.setting} to {self.proposed:g} adds {self.adds}"


def _raw(candidate: Candidate, criterion: str) -> float | None:
    if candidate.score is None:
        return None
    for cs in candidate.score.criteria:
        if cs.criterion == criterion:
            return cs.raw_value
    return None


def enumerate_relaxations(bundle: ProvenanceBundle, query: QuerySettings) -> list[Relaxation]:
    """For each hard filter, the smallest changes that admit the next excluded candidates."""
    out: list[Relaxation] = []
    by_setting: dict[str, list[tuple[float, str]]] = {}
    for c in bundle.excluded():
        assert c.excluded is not None
        setting = RULE_SETTING.get(c.excluded.rule)
        if setting is None:
            continue
        value = _raw(c, SETTING_CRITERION[setting])
        if value is None:
            continue
        by_setting.setdefault(setting, []).append((value, c.composition))
    for setting, items in sorted(by_setting.items()):
        current = getattr(query, setting)
        descending = setting == "band_gap_min_ev"
        items.sort(key=lambda t: (-t[0] if descending else t[0], t[1]))
        admitted: list[str] = []
        seen: set[float] = set()
        for value, comp in items:
            admitted.append(comp)
            if value in seen:
                continue
            seen.add(value)
            proposed: float | int = int(value) if setting == "max_elements" else value
            out.append(
                Relaxation(
                    choice_id=f"{setting}:{len(seen)}",
                    setting=setting,
                    current=current,
                    proposed=proposed,
                    adds=len(admitted),
                    admits=tuple(admitted),
                )
            )
            if len(seen) >= MAX_CHOICES_PER_SETTING:
                break
    return out


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
