"""The rationale writer: text-only slots over a redacted view of the bundle.

Code issues the slot ids and the view the model sees, in which every number, formula, rank,
source, and count is already a template token. The model writes prose around those tokens;
the verifier strips anything else. Without an LLM the slots hold token-only template text.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from pydantic import BaseModel

from materials_triage.config.schema import EffectiveConfig
from materials_triage.records.bundle import (
    Anchor,
    Candidate,
    DecisionLogEntry,
    ProvenanceBundle,
    RationaleSlot,
)
from materials_triage.render.caveats import row_specific
from materials_triage.render.tokens import CRITERION_LABELS

from . import loop, prompts
from .llm import LLMClient
from .tools import WRITE_RATIONALE, WriteRationale

ONE_LINE = "one_line"
OVERVIEW = "summary:overview"


def slot_plan(bundle: ProvenanceBundle) -> list[str]:
    """One slot per ranked candidate, in rank order, then the run overview."""
    return [f"candidate:{c.composition}:{ONE_LINE}" for c in bundle.ranked()] + [OVERVIEW]


def template_only(bundle: ProvenanceBundle) -> dict[str, RationaleSlot]:
    """No-LLM rationale: tokens only, so the text is verified by construction."""
    slots: dict[str, RationaleSlot] = {}
    for c in bundle.ranked():
        slot = f"candidate:{c.composition}:{ONE_LINE}"
        parts = [f"{{formula:{c.composition}}} ranks {{rank:{c.composition}}}"]
        if c.score is not None:
            scored = [
                f"{{criterion:{cs.criterion}}} {{value:{c.composition}:{cs.criterion}}}"
                for cs in c.score.criteria
                if cs.weight > 0 and cs.raw_unit is not None
            ]
            if scored:
                parts.append("on " + ", ".join(scored))
        text = " ".join(parts) + "."
        own = row_specific(c.caveats)
        if own:
            # caveat tokens: the renderer fills each with its config text; the verifier checks
            # only that the row carries the caveat, so no caveat id reaches the reader
            text += " " + " ".join(f"{{caveat:{c.composition}:{cv.id.value}}}" for cv in own)
        slots[slot] = RationaleSlot(slot=slot, text=text, verified=True)
    ranked = bundle.ranked()
    overview = (
        f"Ranked {len(ranked)} of {len(bundle.candidates)} candidates; "
        f"{len(bundle.excluded())} excluded by rule."
    )
    slots[OVERVIEW] = RationaleSlot(slot=OVERVIEW, text=overview, verified=True)
    return slots


def _row_view(row: Candidate | Anchor, bundle: ProvenanceBundle) -> list[str]:
    comp = row.composition
    lines = [f"  material: {{formula:{comp}}}", f"  rank: {{rank:{comp}}}"]
    if row.score is not None:
        for cs in row.score.criteria:
            if cs.weight <= 0 and cs.raw_unit is None:
                continue
            lines.append(
                f"  {{criterion:{cs.criterion}}}: {{value:{comp}:{cs.criterion}}}"
                f" from {{source:{comp}:{cs.criterion}}}" + (" (missing)" if cs.missing else "")
            )
        if row.score.band_gap_source:
            lines.append(f"  band gap source: {{source:{comp}:band_gap}}")
    lines.append(
        f"  polymorphs: {{count:{comp}:polymorphs}} known, ground state {{spacegroup:{comp}}}"
    )
    lines.append(f"  hazard: {{ghs:{comp}}}")
    lines.append(
        f"  literature: {{count:{comp}:hits}} abstracts read of {{count:{comp}:matched}} matched"
    )
    labels = sorted(e.label.value for e in bundle.evidence if e.composition == comp and e.verified)
    lines.append("  evidence labels: " + (", ".join(labels) if labels else "none verified"))
    lines.append("  flags: " + (", ".join(f.value for f in row.flags) or "none"))
    lines.append("  caveats: " + (", ".join(c.id.value for c in row.caveats) or "none"))
    if isinstance(row, Candidate) and row.excluded is not None:
        lines.append(f"  excluded: {row.excluded.rule.value}")
    return lines


def redacted_view(bundle: ProvenanceBundle, slots: list[str]) -> str:
    """What the model sees: slot ids and token-only facts. No raw numbers."""
    all_rows: list[Candidate | Anchor] = [*bundle.candidates, *bundle.anchors]
    rows = {r.composition: r for r in all_rows}
    lines = ["slots to fill: " + ", ".join(slots), "criteria: " + ", ".join(CRITERION_LABELS), ""]
    for slot in slots:
        bits = slot.split(":")
        if len(bits) == 3 and bits[1] in rows:
            lines.append(f"slot {slot}")
            lines.extend(_row_view(rows[bits[1]], bundle))
            lines.append("")
    lines.append(f"slot {OVERVIEW}")
    lines.append(
        "  ranked candidates: " + ", ".join(f"{{formula:{c.composition}}}" for c in bundle.ranked())
    )
    lines.append(
        "  excluded: "
        + (
            ", ".join(
                f"{{formula:{c.composition}}} ({c.excluded.rule.value})"
                for c in bundle.excluded()
                if c.excluded
            )
            or "none"
        )
    )
    lines.append(
        "  anchors: "
        + (
            ", ".join(
                f"{{formula:{a.composition}}} {{rank:{a.composition}}}" for a in bundle.anchors
            )
            or "none"
        )
    )
    if bundle.run.partial:
        lines.append("  run is partial: " + "; ".join(bundle.run.partial_reasons))
    return "\n".join(lines)


@dataclass
class RationaleResult:
    slots: dict[str, RationaleSlot] = field(default_factory=dict)
    entries: list[DecisionLogEntry] = field(default_factory=list)
    partial_reason: str | None = None
    dropped_slots: list[str] = field(default_factory=list)


def make_handler(plan: list[str]) -> loop.Handler:
    allowed = set(plan)

    def handler(parsed: BaseModel) -> loop.ToolOutcome:
        assert isinstance(parsed, WriteRationale)
        given = [s.slot for s in parsed.slots]
        extras = [s for s in given if s not in allowed]
        kept = [s for s in parsed.slots if s.slot in allowed]
        return loop.ToolOutcome(
            json.dumps({"accepted": [s.slot for s in kept], "dropped": extras}),
            data=kept,
            log_detail={
                "slots": [s.slot for s in kept],
                "dropped": extras,
                "chars": sum(len(s.text) for s in kept),
            },
        )

    return handler


def run_rationale(
    *,
    client: LLMClient | None,
    bundle: ProvenanceBundle,
    effective: EffectiveConfig,
    budget: loop.Budget,
) -> RationaleResult:
    """Slots from the model where it answered, template text everywhere else."""
    plan = slot_plan(bundle)
    fallback = template_only(bundle)
    out = RationaleResult(slots=dict(fallback))
    if client is None:
        return out
    result = loop.run_step(
        client=client,
        step="rationale",
        system=prompts.system_prompt("rationale", effective),
        user_text=prompts.data_block(redacted_view(bundle, plan)),
        tool=WRITE_RATIONALE,
        handler=make_handler(plan),
        budget=budget,
    )
    out.entries = result.entries
    if result.status == loop.StepStatus.BUDGET:
        out.partial_reason = f"rationale not written: {result.reason}"
        return out
    if not result.ok or result.outcome is None:
        out.partial_reason = f"rationale not written: {result.reason}"
        return out
    written = result.outcome.data
    for item in written:
        out.slots[item.slot] = RationaleSlot(slot=item.slot, text=item.text, verified=False)
    out.dropped_slots = list(result.outcome.log_detail.get("dropped", []))
    return out
