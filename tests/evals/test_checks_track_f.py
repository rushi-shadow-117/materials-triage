"""Checks added in Track F: rank within a fraction, exclusion-only rows, per-run anchors,
and the G3 diff causes."""

from evals.checks import run_check
from evals.schema import CheckSpec

from materials_triage.records.bundle import Anchor
from tests.evals.bundles import summary
from tests.evals.test_checks import _score, clean_observation


def _run(name: str, **params: object) -> tuple[bool, str]:
    r = run_check(CheckSpec(name=name, params=params), clean_observation())
    return r.passed, r.detail


def test_ranked_within_a_fraction_of_the_ranked_count() -> None:
    assert _run("ranked_near_top", compositions=["HfO2"], within_fraction=0.5)[0]
    passed, detail = _run("ranked_near_top", compositions=["ZrO2"], within_fraction=0.5)
    assert not passed and "limit 2 of 4" in detail
    assert _run("ranked_near_top", compositions=["ZrO2"], within=3)[0]


def test_only_in_exclusions() -> None:
    assert _run("only_in_exclusions", composition="ThO2", rule="hazard.radioactive_exclude")[0]
    assert not _run("only_in_exclusions", composition="ThO2", rule="band_gap.hard_max")[0]
    assert not _run("only_in_exclusions", composition="HfO2")[0]
    assert not _run("only_in_exclusions", composition="Unobtainium")[0]


def test_per_run_anchor_may_also_rank() -> None:
    obs = clean_observation()
    assert obs.bundle is not None
    obs.bundle.anchors.append(
        Anchor(composition="HfO2", group=summary("HfO2"), score=_score(0.8), would_rank=2, out_of=4)
    )
    strict = run_check(
        CheckSpec(name="anchor_shown_with_would_rank", params={"composition": "HfO2"}), obs
    )
    loose = run_check(
        CheckSpec(
            name="anchor_shown_with_would_rank",
            params={"composition": "HfO2", "may_also_rank": True},
        ),
        obs,
    )
    assert not strict.passed and loose.passed


def test_diff_causes_only() -> None:
    obs = clean_observation()
    assert not run_check(
        CheckSpec(name="diff_causes_only", params={"allowed": ["config"]}), obs
    ).passed
    obs.diff = {"changes": [{"composition": "HfO2", "causes": ["config"]}]}
    assert run_check(CheckSpec(name="diff_causes_only", params={"allowed": ["config"]}), obs).passed
    obs.diff = {"changes": [{"composition": "HfO2", "causes": ["config", "data"]}]}
    r = run_check(CheckSpec(name="diff_causes_only", params={"allowed": ["config"]}), obs)
    assert not r.passed and "data" in r.detail
