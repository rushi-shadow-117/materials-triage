"""Parse-and-confirm on the terminal: show what was parsed, every default and clamp, ask for
anything required that is missing, then wait for y/n unless --yes."""

from __future__ import annotations

from collections.abc import Callable

import typer

from materials_triage.agent.parse import ParseOutcome, normalize_candidates
from materials_triage.config.schema import QuerySettings

Prompt = Callable[[str], str]


def describe(outcome: ParseOutcome) -> str:
    q = outcome.query
    if q is None:
        return outcome.refusal or "nothing parsed"
    lines = ["Parsed criteria:"]
    lines.append(f"  profile: {q.profile}")
    lines.append(f"  mode: {q.mode}")
    if q.candidate_list:
        lines.append(f"  candidates: {', '.join(q.candidate_list)}")
    lines.append(f"  top_n: {q.top_n}")
    for key in ("band_gap_min_ev", "band_gap_max_ev", "max_elements", "evidence_tier_min"):
        value = getattr(q, key)
        lines.append(f"  {key}: {'not set' if value is None else value}")
    lines.append(f"  weights: {q.weights or 'profile defaults'}")
    lines.append(f"  exclude_radioactive: {q.exclude_radioactive}")
    if outcome.effective is not None:
        e = outcome.effective
        lines.append(
            f"  verbosity={e.verbosity.value} terminology={e.terminology.value} "
            f"units={e.units.value} view={e.view.value}"
        )
    lines.append("Defaults applied: " + ("; ".join(outcome.defaults_applied) or "none"))
    lines.append(
        "Clamps: "
        + (
            "; ".join(
                f"{c.setting} requested {c.requested}, applied {c.applied} ({c.bound})"
                for c in outcome.clamps
            )
            or "none"
        )
    )
    if outcome.missing_required:
        lines.append("Missing required: " + ", ".join(outcome.missing_required))
    return "\n".join(lines)


def fill_missing(query: QuerySettings, missing: list[str], prompt: Prompt) -> QuerySettings:
    """Ask for each missing required field. Only candidate_list is required today."""
    updates: dict[str, object] = {}
    for field in missing:
        if field == "candidate_list":
            answer = prompt("Formulas to rank, comma separated")
            updates[field] = normalize_candidates([f for f in answer.split(",") if f.strip()])
        else:
            updates[field] = prompt(f"Value for {field}")
    return query.model_copy(update=updates)


def confirm(text: str, *, yes: bool, prompt: Prompt | None = None) -> bool:
    typer.echo(text)
    if yes:
        return True
    ask = prompt or (lambda q: typer.prompt(q, default="n"))
    return ask("Proceed? [y/n]").strip().lower() in ("y", "yes")
