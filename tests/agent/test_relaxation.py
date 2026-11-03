"""Relaxations are enumerated by code with exact values and counts; the model only picks."""

from __future__ import annotations

from materials_triage.agent import llm, loop, relaxation
from materials_triage.config.schema import CoreConfig, QuerySettings
from materials_triage.records.bundle import Exclusion, ExclusionRule, ProvenanceBundle


def _with_gap_exclusions(bundle: ProvenanceBundle) -> ProvenanceBundle:
    """Pretend band_gap_min_ev=6.0 excluded three candidates by their scored gaps."""
    out = bundle.model_copy(deep=True)
    for c in out.candidates:
        if c.composition in ("HfO2", "ZrO2", "TiO2"):
            c.rank = None
            c.excluded = Exclusion(rule=ExclusionRule.BAND_GAP_HARD_MIN, detail="below 6.0 eV")
        if c.composition == "BaTiO3":
            c.rank = None
            c.excluded = Exclusion(rule=ExclusionRule.SIMPLICITY_MAX_ELEMENTS, detail="3 elements")
    return out


def _gap(bundle: ProvenanceBundle, comp: str) -> float:
    c = next(c for c in bundle.candidates if c.composition == comp)
    assert c.score is not None
    return next(cs.raw_value for cs in c.score.criteria if cs.criterion == "band_gap") or 0.0


def test_enumeration_gives_exact_values_and_cumulative_counts(bundle: ProvenanceBundle) -> None:
    b = _with_gap_exclusions(bundle)
    query = QuerySettings(profile="p", band_gap_min_ev=6.0, max_elements=2)
    choices = relaxation.enumerate_relaxations(b, query)
    gaps = sorted(((_gap(b, c), c) for c in ("HfO2", "ZrO2", "TiO2")), reverse=True)
    by_setting = {}
    for r in choices:
        by_setting.setdefault(r.setting, []).append(r)
    mins = by_setting["band_gap_min_ev"]
    assert [r.proposed for r in mins] == [g for g, _ in gaps]
    assert [r.adds for r in mins] == [1, 2, 3]
    assert mins[0].admits == (gaps[0][1],) and mins[0].current == 6.0
    assert mins[0].describe() == f"lowering band_gap_min_ev to {gaps[0][0]:g} adds 1"
    elements = by_setting["max_elements"]
    assert len(elements) == 1 and elements[0].proposed == 3 and elements[0].adds == 1
    assert elements[0].describe() == "raising max_elements to 3 adds 1"
    applied = relaxation.apply_relaxation(query, mins[1])
    assert applied.band_gap_min_ev == gaps[1][0] and applied.max_elements == 2
    assert query.band_gap_min_ev == 6.0


def test_nothing_to_relax_without_threshold_exclusions(bundle: ProvenanceBundle) -> None:
    assert relaxation.enumerate_relaxations(bundle, QuerySettings(profile="p")) == []


def test_model_picks_by_id_and_may_not_write_digits(bundle: ProvenanceBundle) -> None:
    b = _with_gap_exclusions(bundle)
    choices = relaxation.enumerate_relaxations(b, QuerySettings(profile="p", band_gap_min_ev=6.0))

    def call(choice_id: str, explanation: str) -> dict:  # type: ignore[type-arg]
        return {
            "expect_tool": "propose_relaxation",
            "content": [
                {
                    "type": "tool_use",
                    "name": "propose_relaxation",
                    "input": {"choice_id": choice_id, "explanation": explanation},
                }
            ],
        }

    fake = llm.FakeLLM(
        [
            call("band_gap_min_ev:9", "no such id"),
            call("band_gap_min_ev:1", "Lower the gap floor to 5.5 eV."),
            call("band_gap_min_ev:1", "Lower the gap floor slightly to admit the next oxide."),
        ]
    )
    out = relaxation.run_relax(
        client=fake,
        choices=choices,
        request_text="wide gap oxides",
        budget=loop.Budget.from_core(CoreConfig()),
    )
    assert out.choice == choices[0]
    assert out.explanation == "Lower the gap floor slightly to admit the next oxide."
    errors = [t.tool_results[0].content for r in fake.requests for t in r.turns if t.tool_results]
    assert any("unknown choice_id" in e for e in errors) and any("no digits" in e for e in errors)
    assert "DATA" in (fake.requests[0].turns[0].text or "")
    assert relaxation.run_relax(
        client=fake, choices=[], request_text="x", budget=loop.Budget.from_core(CoreConfig())
    ).reason
