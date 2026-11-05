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


def test_template_rationale_renders_caveat_text_never_ids() -> None:
    """Human test session, item 6: the PI saw "Caveats: band_offsets_not_checked, ...". The
    template carries caveat tokens for the row's own caveats; the renderer fills their text.
    Uses the scored bundle, whose rows carry real caveats (the sample bundle's are placeholders)."""
    from pathlib import Path

    from materials_triage.records.bundle import CaveatId
    from materials_triage.render import caveats as caveats_mod
    from materials_triage.render.views import build

    scored = Path(__file__).resolve().parents[2] / "fixtures" / "bundles" / "scored_bundle.json"
    bundle = ProvenanceBundle.model_validate_json(scored.read_text())

    slots = rationale.template_only(bundle)
    checked, report = verify(bundle.model_copy(update={"rationale": slots, "evidence": []}))
    assert report.passed
    ids = {c.value for c in CaveatId}
    for slot in slots.values():
        assert not any(i in TOKEN_RE.sub("", slot.text) for i in ids), slot.text
    view = build(checked, caveats_mod.CaveatConfig.load(), units="eV", hide_ids=True)
    rows = [*view.rows, *view.excluded]
    assert rows and all(not any(i in r.rationale for i in ids) for r in rows)
    with_caveat = [
        r for r in view.rows if "{caveat:" in slots[f"candidate:{r.composition}:one_line"].text
    ]
    assert with_caveat, "the sample bundle has a row with its own caveat"
    for r in with_caveat:
        assert "caveat listed below" not in r.rationale  # filled with config text
    # profile-wide caveats never enter a row's rationale
    assert all("Band offsets to the substrate" not in r.rationale for r in view.rows)


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
        client=fake,
        bundle=bundle,
        effective=effective,
        budget=loop.Budget.from_core(CoreConfig(), "rationale"),
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
    budget = loop.Budget.from_core(CoreConfig(), "rationale")
    out = rationale.run_rationale(client=None, bundle=bundle, effective=effective, budget=budget)
    assert out.slots == rationale.template_only(bundle) and out.partial_reason is None
    exhausted = loop.Budget(max_tool_calls=0, max_tokens=1, max_seconds=1)
    out2 = rationale.run_rationale(
        client=llm.FakeLLM([]), bundle=bundle, effective=effective, budget=exhausted
    )
    assert out2.slots == rationale.template_only(bundle)
    assert out2.partial_reason is not None and "max_tool_calls" in out2.partial_reason


def test_slot_plan_asks_only_for_the_shown_rows(bundle: ProvenanceBundle) -> None:
    """Track H sweep: rows beyond top N keep their template text; the model is asked for the
    rows the views show and the overview."""
    ranked = bundle.ranked()
    assert len(ranked) > 2
    plan = rationale.slot_plan(bundle, 2)
    assert plan == [f"candidate:{c.composition}:one_line" for c in ranked[:2]] + [
        "summary:overview"
    ]
    assert rationale.slot_plan(bundle, None) == rationale.slot_plan(bundle)


def test_redacted_view_says_not_scored_when_a_value_exists(bundle: ProvenanceBundle) -> None:
    """Track H sweep: the model wrote "dielectric constant is missing" beside k = 18.7 because
    the criterion, unscored while its band is pending, was marked "(missing)"."""
    from materials_triage.records.bundle import CriterionScore

    hfo2 = next(c for c in bundle.candidates if c.composition == "HfO2")
    assert hfo2.score is not None
    crits = [
        cs.model_copy(update={"missing": True, "missing_reason": "target band not entered"})
        if cs.criterion == "dielectric_constant"
        else cs
        for cs in hfo2.score.criteria
    ]
    assert any(
        isinstance(c, CriterionScore) and c.raw_value is not None
        for c in crits
        if c.criterion == "dielectric_constant"
    )
    row = hfo2.model_copy(update={"score": hfo2.score.model_copy(update={"criteria": crits})})
    b = bundle.model_copy(
        update={"candidates": [row if c.composition == "HfO2" else c for c in bundle.candidates]}
    )
    text = rationale.redacted_view(b, rationale.slot_plan(b, 3))
    line = next(
        ln for ln in text.splitlines() if "{criterion:dielectric_constant}" in ln and "HfO2" in ln
    )
    assert "not scored: target band not entered" in line and "(missing" not in line
