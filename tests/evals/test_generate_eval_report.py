"""docs/EVAL.md is generated in full from results files, byte-stable, and honest about what is
missing."""

import json
from pathlib import Path

import yaml
from evals.cases import load_cases
from evals.execute import SampleBundleExecutor
from evals.judge import FakeJudge, write_judge_sample
from evals.preregistration import preregister
from evals.runner import run_suite, write_results
from evals.schema import JudgeVerdict
from scripts.generate_eval_report import build
from validation.report import run_validation
from validation.track_a import score_with_track_a

from tests.evals.test_cases_and_runner import ADVERSARIAL, NORMAL, write_cases


def test_report_says_what_is_missing_when_nothing_ran(tmp_path: Path) -> None:
    text = build(
        eval_results=tmp_path / "none",
        validation_json=tmp_path / "v.json",
        calibration_json=tmp_path / "c.json",
        prereg_path=tmp_path / "p.json",
        judge_sample=tmp_path / "j.md",
        scoring_tests=tmp_path / "no_tests",
    )
    assert "No eval results found" in text
    assert "No validation results found" in text
    assert "No pre-registration record" in text
    assert "No judge sample written yet" in text
    assert "tests/scoring absent" in text
    assert text.startswith("# Evaluation report\n")


def test_report_is_built_from_results_and_is_byte_stable(tmp_path: Path) -> None:
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    broken = {
        **NORMAL,
        "id": "A2",
        "title": "planted miss",
        "checks": [{"name": "ranked_near_top", "params": {"compositions": ["ThO2"], "within": 1}}],
    }
    cases = load_cases(write_cases(cases_dir, NORMAL, ADVERSARIAL, broken))
    results_dir = tmp_path / "results"
    write_results(run_suite(cases, SampleBundleExecutor(), FakeJudge(), suite="all"), results_dir)
    val_dir = tmp_path / "val"
    run_validation(score_with_track_a, scorer_name="track_a", out_dir=val_dir)
    prereg = tmp_path / "prereg.json"
    preregister(prereg, scorer_name="track_a")
    sample = tmp_path / "judge_sample.md"
    write_judge_sample(
        [("A1", 1, JudgeVerdict(item="caveat_presence", verdict="pass", reason="r", judge="fake"))],
        sample,
    )
    kwargs = dict(
        eval_results=results_dir,
        validation_json=val_dir / "validation.json",
        calibration_json=val_dir / "band_gap_calibration.json",
        prereg_path=prereg,
        judge_sample=sample,
        scoring_tests=tmp_path / "no_tests",
    )
    text = build(**kwargs)  # type: ignore[arg-type]
    assert text == build(**kwargs)  # type: ignore[arg-type]
    # Listing order and the required pair first.
    assert text.index("### A1:") < text.index("### F1:") < text.index("### A2:")
    assert "LLM02 Sensitive Information Disclosure" in text
    assert NORMAL["expectation"] in text
    # The planted miss is explained in one line with the check's detail.
    assert "- repeat 1, `ranked_near_top`: ThO2=None" in text
    # Validation rows, calibration, preregistration, judge.
    assert "Scorer `track_a`" in text
    assert "### Yim 2015 positives (10.1038/am.2015.57)" in text
    assert "Conflict tolerance:" in text and "tbmbj: n=6" in text
    assert "Current config sha matches the pre-registered one." in text
    assert "not yet graded by the owner" in text
    # Every number in the report traces to the JSON that was written.
    val = json.loads((val_dir / "validation.json").read_text())
    for t in val["yim"]["tables"]:
        assert f"| {t['table']} | {t['n_in_table']} | {t['n_ranked']} |" in text
        assert "| not run | not run |" in text
    assert val["yim_like"] is None
    assert "Yim-like configuration: not run" in text
    assert "## Directional tests" in text

    # A Yim-like block renders beside the default column, labeled, with its own config sha.
    like_tables = [dict(t, rho=0.5) for t in val["yim"]["tables"]]
    val["yim_like"] = {
        "label": "Yim-like configuration: planted",
        "weights": {"stability": 1.0, "band_gap": 1.0, "dielectric_constant": 1.0, "hazard": 0.0},
        "dielectric_target_band": [10.0, 30.0],
        "dielectric_target_band_status": "pending_verification",
        "config_sha": "b" * 64,
        "note": "planted",
        "tables": like_tables,
    }
    (val_dir / "validation.json").write_text(json.dumps(val))
    text2 = build(**kwargs)  # type: ignore[arg-type]
    assert "| Ranked (Yim-like) | rho (Yim-like) |" in text2
    assert "Yim-like configuration: planted" in text2
    assert "- weights: stability 1, band_gap 1, dielectric_constant 1, hazard 0" in text2
    assert "- dielectric target band: [10, 30] (status pending_verification)" in text2
    assert f"- config sha `{'b' * 12}` (default run `{val['scorer']['config_sha'][:12]}`)" in text2
    for t in val["yim"]["tables"]:
        rho = "n/a" if t["rho"] is None else f"{t['rho']:.3f}"
        assert (
            f"| {t['table']} | {t['n_in_table']} | {t['n_ranked']} | {rho} "
            f"| {t['n_ranked']} | 0.500 |"
        ) in text2


def test_case_yaml_round_trip_keeps_expectation_verbatim(tmp_path: Path) -> None:
    text = "Expect HfO2, Al2O3, ZrO2 near the top; SiO2 shown as the anchor.\n  Second line."
    (tmp_path / "A9.yaml").write_text(yaml.safe_dump({**NORMAL, "id": "A9", "expectation": text}))
    assert load_cases(tmp_path)[0].expectation == text


def test_live_results_lead_with_denominators_and_the_scripted_suite_is_labelled(
    tmp_path: Path,
) -> None:
    # review F06: the headline was a scripted-model count with a scripted judge
    import json

    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    cases = load_cases(write_cases(cases_dir, NORMAL, ADVERSARIAL))
    results_dir = tmp_path / "results"
    write_results(run_suite(cases, SampleBundleExecutor(), FakeJudge(), suite="all"), results_dir)
    live_dir = results_dir / "live"
    path = write_results(
        run_suite(cases, SampleBundleExecutor(), FakeJudge(), suite="F1"), live_dir
    )
    data = json.loads(path.read_text())
    data["executor"] = "pipeline:live:cassettes, claude-haiku-5-5, 2026-11-05"
    path.write_text(json.dumps(data))
    (live_dir / "notes.yaml").write_text(
        f"{path.stem}:\n  model: claude-haiku-5-5\n  date: 2026-11-05\n  headline: true\n"
        "  note: test\n"
    )
    text = build(
        eval_results=results_dir,
        validation_json=tmp_path / "none.json",
        calibration_json=tmp_path / "none.json",
        prereg_path=tmp_path / "none.json",
        judge_sample=tmp_path / "none.md",
        scoring_tests=tmp_path / "no_tests",
    )
    assert text.index("## Live model") < text.index("## Regression harness (scripted model)")
    assert "on claude-haiku-5-5, 2026-11-05:" in text
    assert "repeat(s) in total" in text and "attack success 0 of" in text


def test_scripted_misses_carry_their_owner_reviewed_explanation(tmp_path: Path) -> None:
    # owner decision on PR #18: the A1 and G1 misses stay on record with the explanation
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    cases = load_cases(write_cases(cases_dir, NORMAL, ADVERSARIAL))
    results_dir = tmp_path / "results"
    write_results(run_suite(cases, SampleBundleExecutor(), FakeJudge(), suite="all"), results_dir)
    (results_dir / "scripted_notes.yaml").write_text("A1: kept as pre-registered; ZrO2 note\n")
    text = build(
        eval_results=results_dir,
        validation_json=tmp_path / "none.json",
        calibration_json=tmp_path / "none.json",
        prereg_path=tmp_path / "none.json",
        judge_sample=tmp_path / "none.md",
        scoring_tests=tmp_path / "no_tests",
    )
    harness = text[text.index("## Regression harness (scripted model)") :]
    assert "Known misses (owner-reviewed):" in harness
    assert "- A1: kept as pre-registered; ZrO2 note" in harness
