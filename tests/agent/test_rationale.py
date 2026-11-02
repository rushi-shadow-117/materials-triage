"""The rationale writer sees tokens, writes prose, and the verifier has the last word."""

from __future__ import annotations

import re

from materials_triage.agent import llm, loop, rationale
from materials_triage.config.schema import CoreConfig, EffectiveConfig
from materials_triage.records.bundle import ProvenanceBundle
from materials_triage.render.tokens import TOKEN_RE
from materials_triage.verify.verifier import verify


def test_slot_plan_follows_rank_order_and_ends_with_the_overview(bundle: ProvenanceBundle) -> None:
    plan = rationale.slot_plan(bundle)
    assert plan[0] == "candidate:Al2O3:one_line" and plan[-1] == rationale.OVERVIEW
    assert len(plan) == len(bundle.ranked()) + 1


def test_template_only_slots_pass_the_verifier(bundle: ProvenanceBundle) -> None:
    slots = rationale.template_only(bundle)
    checked, report = verify(bundle.model_copy(update={"rationale": slots, "evidence": []}))
    assert report.passed and all(s.verified for s in checked.rationale.values())
    assert "{formula:HfO2} ranks {rank:HfO2}" in slots["candidate:HfO2:one_line"].text
    assert "band_offsets_not_checked" in slots["candidate:HfO2:one_line"].text


def test_redacted_view_carries_no_raw_numbers(bundle: ProvenanceBundle) -> None:
    view = rationale.redacted_view(bundle, rationale.slot_plan(bundle))
    # slot ids and tokens name compositions (Al2O3); nothing else may carry a digit
    stripped = re.sub(r"(candidate|anchor):[^\s,]+", "", TOKEN_RE.sub("", view))
    assert re.search(r"\d", stripped) is None, stripped
    assert "{value:HfO2:band_gap}" in view and "{ghs:HfO2}" in view
    assert "slot summary:overview" in view and "{formula:ThO2} (hazard.radioactive_exclude)" in view


def test_model_slots_replace_template_text_and_extras_are_dropped(
    bundle: ProvenanceBundle, effective: EffectiveConfig
) -> None:
    fake = llm.FakeLLM(
        [
            {
                "expect_tool": "write_rationale",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "write_rationale",
                        "input": {
                            "slots": [
                                {
                                    "slot": "candidate:HfO2:one_line",
                                    "text": "{formula:HfO2} leads on {criterion:stability}.",
                                },
                                {
                                    "slot": "candidate:PbO:one_line",
                                    "text": "{formula:PbO} is not here.",
                                },
                            ]
                        },
                    }
                ],
            }
        ]
    )
    out = rationale.run_rationale(
        client=fake, bundle=bundle, effective=effective, budget=loop.Budget.from_core(CoreConfig())
    )
    assert (
        out.slots["candidate:HfO2:one_line"].text
        == "{formula:HfO2} leads on {criterion:stability}."
    )
    assert out.slots["candidate:HfO2:one_line"].verified is False
    assert "candidate:PbO:one_line" not in out.slots and out.dropped_slots == [
        "candidate:PbO:one_line"
    ]
    assert out.slots["candidate:ZrO2:one_line"].text.startswith("{formula:ZrO2} ranks")
    detail = out.entries[-1].detail
    assert detail["slots"] == ["candidate:HfO2:one_line"] and "leads on" not in str(detail)
    assert "DATA" in (fake.requests[0].turns[0].text or "")


def test_no_llm_and_failed_step_fall_back_to_template_text(
    bundle: ProvenanceBundle, effective: EffectiveConfig
) -> None:
    budget = loop.Budget.from_core(CoreConfig())
    out = rationale.run_rationale(client=None, bundle=bundle, effective=effective, budget=budget)
    assert out.slots == rationale.template_only(bundle) and out.partial_reason is None
    exhausted = loop.Budget(max_tool_calls=0, max_tokens=1, max_seconds=1)
    out2 = rationale.run_rationale(
        client=llm.FakeLLM([]), bundle=bundle, effective=effective, budget=exhausted
    )
    assert out2.slots == rationale.template_only(bundle)
    assert out2.partial_reason is not None and "max_tool_calls" in out2.partial_reason
