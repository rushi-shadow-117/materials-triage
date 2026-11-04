"""A narrow LLM judge for two things structure cannot decide: whether the PI view states the
caveats the bundle carries, and whether it reads at summary level. Rubric: evals/judge_rubric.md.

The judge never scores, ranks, or checks numbers. Each verdict carries a reason. The fake
judge is the default (CI); the Anthropic judge runs when EVAL_LLM=anthropic and a key is set.
A declined request is recorded as the verdict judge_declined, not hidden behind a fallback.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal, Protocol

import yaml
from pydantic import BaseModel

from evals.schema import JudgeItem, JudgeVerdict
from materials_triage.records.bundle import ProvenanceBundle

ROOT = Path(__file__).resolve().parents[1]
RUBRIC = ROOT / "evals" / "judge_rubric.md"
JUDGE_CONFIG = ROOT / "evals" / "judge.yaml"
SAMPLE_PATH = ROOT / "evals" / "judge_sample.md"


class JudgeOutput(BaseModel):
    verdict: Literal["pass", "fail"]
    reason: str


class Judge(Protocol):
    name: str

    def judge(self, item: JudgeItem, rendered: str, bundle: ProvenanceBundle) -> JudgeVerdict: ...


def caveat_terms(bundle: ProvenanceBundle) -> list[str]:
    """Caveat ids on ranked candidates, as words the rendered text would have to carry."""
    ids = {str(cv.id) for c in bundle.ranked() for cv in c.caveats}
    return sorted(ids)


class FakeJudge:
    """Deterministic rules standing in for the model so CI runs without a key. It is a stand-in
    for the rubric, not the rubric: the owner grades the real judge's sample."""

    name = "fake"

    def judge(self, item: JudgeItem, rendered: str, bundle: ProvenanceBundle) -> JudgeVerdict:
        text = rendered.lower()
        if item == "caveat_presence":
            terms = caveat_terms(bundle)
            missing = [t for t in terms if t.replace("_", " ") not in text and t not in text]
            ok = "caveat" in text and not missing
            reason = (
                "caveat section present and every caveat id named"
                if ok
                else f"missing: {missing or 'caveat section'}"
            )
            return JudgeVerdict(
                item=item, verdict="pass" if ok else "fail", reason=reason, judge=self.name
            )
        words = len(re.findall(r"\w+", rendered))
        per_candidate = words / max(1, len(bundle.ranked()))
        record_ids = len(re.findall(r"\bmp-\d+\b|\bW\d{6,}\b|\bCID \d+\b", rendered))
        ok = per_candidate <= 80 and record_ids == 0
        reason = f"{per_candidate:.0f} words per candidate, {record_ids} record ids" + (
            "" if ok else " (audit-level detail in a PI view)"
        )
        return JudgeVerdict(
            item=item, verdict="pass" if ok else "fail", reason=reason, judge=self.name
        )


class NoJudge:
    """For graded saved bundles: no judge call is made; each item is recorded as declined."""

    name = "none"

    def judge(self, item: JudgeItem, rendered: str, bundle: ProvenanceBundle) -> JudgeVerdict:
        return JudgeVerdict(
            item=item,
            verdict="judge_declined",
            reason="saved bundle graded without a judge call (owner rule: no unapproved calls)",
            judge=self.name,
        )


class AnthropicJudge:
    name = "anthropic"

    def __init__(self) -> None:
        from materials_triage.agent.llm import anthropic_sdk
        from materials_triage.settings import Settings

        cfg = yaml.safe_load(JUDGE_CONFIG.read_text())
        self.model = str(cfg["model"])
        effort = str(cfg.get("effort", "low"))
        if effort not in ("low", "medium", "high"):
            raise ValueError(f"judge effort must be low, medium, or high, not {effort!r}")
        self.effort: Literal["low", "medium", "high"] = effort  # type: ignore[assignment]
        self.max_tokens = int(cfg.get("max_tokens", 1024))
        self.name = self.model
        self.rubric = RUBRIC.read_text()
        self.client = anthropic_sdk(Settings())  # keyed from .env, behind the egress check

    def judge(self, item: JudgeItem, rendered: str, bundle: ProvenanceBundle) -> JudgeVerdict:
        terms = caveat_terms(bundle)
        prompt = (
            f"Rubric item: {item}\n\n"
            f"Caveat ids the bundle carries on ranked candidates: {terms}\n\n"
            f"Rendered PI view:\n<view>\n{rendered}\n</view>\n\n"
            "Decide pass or fail for this item only and give one sentence of reason."
        )
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self.rubric,
            output_format=JudgeOutput,
            output_config={"effort": self.effort},
            messages=[{"role": "user", "content": prompt}],
        )
        if response.stop_reason == "refusal" or response.parsed_output is None:
            detail = (
                getattr(response.stop_details, "category", None) if response.stop_details else None
            )
            return JudgeVerdict(
                item=item,
                verdict="judge_declined",
                reason=f"stop_reason={response.stop_reason} category={detail}",
                judge=self.name,
            )
        out = response.parsed_output
        return JudgeVerdict(item=item, verdict=out.verdict, reason=out.reason, judge=self.name)


def make_judge() -> Judge:
    if os.environ.get("EVAL_LLM", "fake").lower() == "anthropic":
        return AnthropicJudge()
    return FakeJudge()


# ----------------------------------------------------------------------------- owner grading


SAMPLE_HEADER = (
    "# Judge sample for owner grading\n\n"
    "Generated by `uv run python -m evals judge-sample`. Fill the `owner_grade` column with "
    "`pass` or `fail` for each row (leave `judge_declined` rows blank), then run "
    "`uv run python -m evals agreement` to report the agreement rate.\n\n"
    "| case | repeat | item | judge | verdict | reason | owner_grade |\n"
    "|---|---|---|---|---|---|---|\n"
)


def write_judge_sample(rows: list[tuple[str, int, JudgeVerdict]], path: Path = SAMPLE_PATH) -> None:
    lines = [SAMPLE_HEADER]
    for case_id, repeat, v in rows:
        reason = v.reason.replace("|", "/").replace("\n", " ")
        lines.append(
            f"| {case_id} | {repeat} | {v.item} | {v.judge} | {v.verdict} | {reason} |  |\n"
        )
    path.write_text("".join(lines))


def agreement_rate(path: Path = SAMPLE_PATH) -> dict[str, Any]:
    """Rows the owner graded, and the share where the owner's grade equals the verdict."""
    graded = agreed = total = 0
    for line in path.read_text().splitlines():
        if not line.startswith("| ") or line.startswith("| case") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 7:
            continue
        total += 1
        verdict, grade = cells[4], cells[6]
        if verdict == "judge_declined" or grade == "":
            continue
        graded += 1
        agreed += int(grade == verdict)
    return {
        "rows": total,
        "graded": graded,
        "agreed": agreed,
        "agreement_rate": None if graded == 0 else agreed / graded,
    }
