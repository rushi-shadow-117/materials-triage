"""Relaxations are enumerated by code with exact values and re-scored counts; the model only
picks, and when none is admissible the code says so."""

from __future__ import annotations

import math

from materials_triage.agent import llm, loop, relaxation
from materials_triage.config.schema import Bounds, CoreConfig, QuerySettings, SiteProfile
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


SITE = SiteProfile(stability_cutoff_bounds=Bounds(min=0.0, max=94.0))


def _rescorer(bundle: ProvenanceBundle) -> relaxation.Rescore:
    """Stand-in for re-scoring the fetched groups: ranked rows stay ranked, a row excluded by
    the gap minimum ranks once its gap meets the query's minimum, other exclusions stay."""

    def rescore(q: QuerySettings) -> list[str]:
        out = []
        for c in bundle.candidates:
            gap = _gap(bundle, c.composition)
            rule = c.excluded.rule if c.excluded else None
            if rule not in (None, ExclusionRule.BAND_GAP_HARD_MIN):
                continue
            gated = rule is ExclusionRule.BAND_GAP_HARD_MIN
            if gated and q.band_gap_min_ev is not None and gap < q.band_gap_min_ev:
                continue
            out.append(c.composition)
        return out

    return rescore


def test_every_proposal_adds_the_count_a_rescore_gives(bundle: ProvenanceBundle) -> None:
    b = _with_gap_exclusions(bundle)
    query = QuerySettings(profile="p", band_gap_min_ev=6.0, max_elements=2)
    choices, statement = relaxation.enumerate_or_explain(
        b.candidates, query, site=SITE, cutoff_mev=None, rescore=_rescorer(b)
    )
    assert statement is None
    gaps = sorted(((_gap(b, c), c) for c in ("HfO2", "ZrO2", "TiO2")), reverse=True)
    mins = [r for r in choices if r.setting == "band_gap_min_ev"]
    assert [r.proposed for r in mins] == [math.floor(g * 100) / 100 for g, _ in gaps]
    assert [r.adds for r in mins] == [1, 2, 3]
    assert mins[0].admits == (gaps[0][1],) and mins[0].current == 6.0
    assert mins[0].describe() == f"lowering band_gap_min_ev to {mins[0].proposed:g} adds 1"
    # BaTiO3 stays excluded under the stand-in, so raising max_elements adds nothing: no proposal
    assert not [r for r in choices if r.setting == "max_elements"]
    summary = relaxation.log_summary(choices, statement)
    assert summary.startswith("relaxations available (code, not applied): 3;") and "adds" in summary
    applied = relaxation.apply_relaxation(query, mins[1])
    assert applied.band_gap_min_ev == mins[1].proposed and query.band_gap_min_ev == 6.0


def test_no_admissible_relaxation_is_stated(bundle: ProvenanceBundle) -> None:
    choices, statement = relaxation.enumerate_or_explain(
        bundle.candidates,
        QuerySettings(profile="p"),
        site=SITE,
        cutoff_mev=None,
        rescore=_rescorer(bundle),
    )
    assert choices == [] and statement is not None
    assert statement.startswith("no relaxation is admissible within site bounds")


def test_hull_relaxation_stays_inside_the_site_bounds(bundle: ProvenanceBundle) -> None:
    b = bundle.model_copy(deep=True)
    target = next(c for c in b.candidates if c.composition == "HfO2")
    target.rank = None
    target.excluded = Exclusion(rule=ExclusionRule.STABILITY_CUTOFF, detail="above 0")
    assert target.score is not None
    stab = next(c for c in target.score.criteria if c.criterion == "stability")
    stab.raw_value = 0.0123
    far = next(c for c in b.candidates if c.composition == "ZrO2")
    far.rank = None
    far.excluded = Exclusion(rule=ExclusionRule.STABILITY_CUTOFF, detail="above 0")
    assert far.score is not None
    next(c for c in far.score.criteria if c.criterion == "stability").raw_value = 0.2

    def rescore(q: QuerySettings) -> list[str]:
        cut = q.e_above_hull_max_mev if q.e_above_hull_max_mev is not None else 0.0
        return ["HfO2"] if cut >= 12.3 else []

    choices, _ = relaxation.enumerate_or_explain(
        b.candidates, QuerySettings(profile="p"), site=SITE, cutoff_mev=0.0, rescore=rescore
    )
    assert [(r.setting, r.proposed, r.adds) for r in choices] == [("e_above_hull_max_mev", 12.3, 1)]
    assert choices[0].describe() == "raising e_above_hull_max_mev to 12.3 adds 1"


def test_model_picks_by_id_and_may_not_write_digits(bundle: ProvenanceBundle) -> None:
    b = _with_gap_exclusions(bundle)
    choices, _ = relaxation.enumerate_or_explain(
        b.candidates,
        QuerySettings(profile="p", band_gap_min_ev=6.0),
        site=SITE,
        cutoff_mev=None,
        rescore=_rescorer(b),
    )

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
        budget=loop.Budget.from_core(CoreConfig(), "relax"),
    )
    assert out.choice == choices[0]
    assert out.explanation == "Lower the gap floor slightly to admit the next oxide."
    errors = [t.tool_results[0].content for r in fake.requests for t in r.turns if t.tool_results]
    assert any("unknown choice_id" in e for e in errors) and any("no digits" in e for e in errors)
    assert "DATA" in (fake.requests[0].turns[0].text or "")
    assert relaxation.run_relax(
        client=fake,
        choices=[],
        request_text="x",
        budget=loop.Budget.from_core(CoreConfig(), "relax"),
    ).reason
