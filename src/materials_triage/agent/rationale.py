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
    Flag,
    ProvenanceBundle,
    RationaleSlot,
)
from materials_triage.render.tokens import CRITERION_LABELS

from . import loop, prompts
from .llm import LLMClient
from .tools import WRITE_RATIONALE, WriteRationale

ONE_LINE = "one_line"
OVERVIEW = "summary:overview"


def slot_plan(bundle: ProvenanceBundle, top_n: int | None = None) -> list[str]:
    """One slot per shown ranked candidate (the top N the views display), in rank order, then
    the run overview. Rows beyond top N keep their template text: a discovery run ranks
    thousands of rows, and asking the model for all of them built a 1.15M-token prompt."""
    ranked = bundle.ranked()
    shown = ranked[:top_n] if top_n is not None and top_n > 0 else ranked
    return [f"candidate:{c.composition}:{ONE_LINE}" for c in shown] + [OVERVIEW]


def template_only(bundle: ProvenanceBundle) -> dict[str, RationaleSlot]:
    """No-LLM rationale: tokens only, so the text is verified by construction."""
    slots: dict[str, RationaleSlot] = {}
    rows: list[Candidate | Anchor] = [*bundle.ranked()]
    ranked_keys = {c.composition for c in rows}
    rows += [a for a in bundle.anchors if a.composition not in ranked_keys]
    for c in rows:
        slot = f"candidate:{c.composition}:{ONE_LINE}"
        # an anchor's rank token reads "would place 11th of 12, between ..."
        verb = "" if isinstance(c, Anchor) else " ranks"
        parts = [f"{{formula:{c.composition}}}{verb} {{rank:{c.composition}}}"]
        if c.score is not None:
            scored = [
                f"{{criterion:{cs.criterion}}} {{value:{c.composition}:{cs.criterion}}}"
                for cs in c.score.criteria
                if cs.weight > 0 and cs.raw_unit is not None
            ]
            if scored:
                parts.append("on " + ", ".join(scored))
        # criterion values only: the row's caveats have their own column (Key caveat) and the
        # audit list, and repeating their text here made the Why cell restate them
        text = " ".join(parts) + "."
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
            if cs.missing and cs.raw_value is not None:
                # a value exists but the criterion is not scored (a pending target band):
                # say so, never "missing" beside a value the page shows (Track H sweep)
                state = f" (not scored: {cs.missing_reason or 'not configured'})"
            elif cs.missing:
                state = f" (missing: {cs.missing_reason or 'no value'})"
            else:
                state = ""
            lines.append(
                f"  {{criterion:{cs.criterion}}}: {{value:{comp}:{cs.criterion}}}"
                f" from {{source:{comp}:{cs.criterion}}}" + state
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
    shown = {s.split(":")[1] for s in slots if s.count(":") == 2}
    checked = [c for c in bundle.ranked() if Flag.ENRICHMENT_MISSING not in c.flags]
    lines.append(
        "  ranked candidates shown: "
        + ", ".join(
            f"{{formula:{c.composition}}}" for c in bundle.ranked() if c.composition in shown
        )
    )
    if len(checked) < len(bundle.ranked()):
        # no digits reach the model; the counts are on the page, written by code
        lines.append(
            "  note: some ranked rows were scored on summary data only (hazard and structure "
            "not checked); do not describe placements among them or compare the shortlist "
            "against them"
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
    plan = slot_plan(bundle, effective.top_n)
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
        out.partial_reason = f"rationale not written: {loop.plain_reason(result.reason)}"
        return out
    written = result.outcome.data
    for item in written:
        out.slots[item.slot] = RationaleSlot(slot=item.slot, text=item.text, verified=False)
    out.dropped_slots = list(result.outcome.log_detail.get("dropped", []))
    return out
