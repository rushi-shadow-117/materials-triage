"""The model calls a confirmed run may make, computed before it runs.

Classification is one call per abstract for the top candidates (at most
`max_abstracts_per_candidate` each); the rationale is one call. The classify and rationale
step budgets are the hard cap: the loop stops a step at its budget. Classifier cache hits make
the real count lower; the estimate never assumes a hit.
"""

from __future__ import annotations

from dataclasses import dataclass

from materials_triage.agent import llm_status
from materials_triage.config.schema import CoreConfig, EffectiveConfig, QuerySettings


@dataclass(frozen=True)
class CallEstimate:
    classify: int
    rationale: int
    total: int
    cap: int
    basis: str


def estimate(
    *,
    query: QuerySettings,
    effective: EffectiveConfig,
    core: CoreConfig,
    classify_mode: str,
) -> CallEstimate:
    if not llm_status.available():
        return CallEstimate(0, 0, 0, 0, llm_status.note() or "no model")
    per = core.max_abstracts_per_candidate
    if query.mode == "candidate_list":
        considered = min(len(query.candidate_list), effective.top_n)
        who = f"{considered} of {len(query.candidate_list)} listed candidates"
    else:
        considered = effective.top_n
        who = f"the top {considered} discovery candidates"
    classify_cap = core.step_budgets["classify"].max_tool_calls
    rationale_cap = core.step_budgets["rationale"].max_tool_calls
    if classify_mode == "cache_only":
        classify, classify_cap = 0, 0
        basis = "classification reads the cache only (CLASSIFY_MODE=cache_only); one rationale call"
    else:
        classify = min(considered * per, classify_cap)
        basis = (
            f"up to {per} abstracts each for {who}, one call per abstract, "
            "fewer when the classifier cache already holds a label; one rationale call"
        )
    return CallEstimate(
        classify=classify,
        rationale=1,
        total=classify + 1,
        cap=classify_cap + rationale_cap,
        basis=basis,
    )
