"""scripts/cold_run.sh prints PASS or FAIL for every step and exits non-zero on a failure
(owner decision on PR #18: a failed step printed nothing and the script exited 0)."""

from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "cold_run.sh"


def _bash(body: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", f"COLD_RUN_HELPERS_ONLY=1 source {SCRIPT}; {body}"],
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_failing_step_prints_fail_and_exits_non_zero() -> None:
    r = _bash('run_step "x. a step that fails" false; echo "not reached"')
    assert r.returncode == 1
    assert "x. a step that fails" in r.stdout and r.stdout.rstrip().endswith("FAIL")
    assert "not reached" not in r.stdout


def test_a_failure_inside_a_chained_step_is_still_a_fail() -> None:
    r = _bash('chained() { true && false && true; }; run_step "y. chained" chained')
    assert r.returncode == 1 and r.stdout.rstrip().endswith("FAIL")


def test_a_passing_step_prints_pass() -> None:
    r = _bash('run_step "z. a step that passes" true; echo done')
    assert r.returncode == 0 and "PASS" in r.stdout and r.stdout.rstrip().endswith("done")


def test_step_eight_runs_f1_on_the_scripted_model() -> None:
    text = SCRIPT.read_text()
    assert "--suite F1" in text and "F1: pass_rate=1.00" in text


def test_a_failing_line_before_a_passing_line_is_a_fail() -> None:
    r = _bash('two() { false; true; }; run_step "w. fails then passes" two')
    assert r.returncode == 1 and r.stdout.rstrip().endswith("FAIL")
