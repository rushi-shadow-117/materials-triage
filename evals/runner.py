"""Run cases with repeats, apply checks and the judge, write results JSON.

Structural outcome per repeat: every `checks` entry passes. Adversarial cases also report
task completion (all `task_completion` checks pass) and attack success (any `defenses`
check passes). Results are written in listing order (A1, F1 first) with every check's detail.
"""

from __future__ import annotations

import json
from pathlib import Path

from evals.cases import order_cases
from evals.checks import run_check
from evals.execute import Executor, effective_config_sha
from evals.judge import Judge
from evals.preregistration import compare, git_commit
from evals.schema import (
    Case,
    CaseResult,
    JudgeVerdict,
    Observation,
    RepeatResult,
    SuiteResult,
)

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "evals" / "results"


def judge_observation(case: Case, obs: Observation, judge: Judge) -> list[JudgeVerdict]:
    if not case.judge or obs.bundle is None:
        return []
    rendered = obs.rendered.get("pi_summary")
    if rendered is None:
        return [
            JudgeVerdict(
                item=item,
                verdict="judge_declined",
                reason="no pi_summary view rendered",
                judge=judge.name,
            )
            for item in case.judge
        ]
    return [judge.judge(item, rendered, obs.bundle) for item in case.judge]


def run_repeat(
    case: Case, repeat: int, executor: Executor, judge: Judge
) -> tuple[RepeatResult, Observation | None]:
    try:
        obs = executor.run(case, repeat)
    except Exception as e:  # noqa: BLE001 - an executor crash is a failed repeat, reported
        return (
            RepeatResult(
                repeat=repeat,
                run_id=f"error-{case.id}-{repeat}",
                passed=False,
                checks=[],
                errors=[f"{type(e).__name__}: {e}"],
            ),
            None,
        )
    checks = [run_check(spec, obs) for spec in case.checks]
    passed = all(c.passed for c in checks)
    task = attack = None
    if case.kind == "adversarial":
        task_checks = [run_check(spec, obs) for spec in case.task_completion]
        defense_checks = [run_check(spec, obs) for spec in case.defenses]
        task = all(c.passed for c in task_checks) if task_checks else None
        attack = any(not c.passed for c in defense_checks)
        checks += [c.model_copy(update={"name": f"task_completion:{c.name}"}) for c in task_checks]
        checks += [c.model_copy(update={"name": f"defense:{c.name}"}) for c in defense_checks]
        passed = passed and not attack and (task is not False)
    return RepeatResult(
        repeat=repeat,
        run_id=obs.run_id,
        passed=passed,
        checks=checks,
        task_completed=task,
        attack_succeeded=attack,
        judge=judge_observation(case, obs, judge),
        errors=obs.errors,
    ), obs


def _rate(values: list[bool | None]) -> float | None:
    known = [v for v in values if v is not None]
    return None if not known else sum(1 for v in known if v) / len(known)


def run_case(
    case: Case, executor: Executor, judge: Judge, repeats: int | None = None
) -> CaseResult:
    if case.skip_reason is not None:
        return CaseResult(
            case_id=case.id,
            group=case.group,
            kind=case.kind,
            title=case.title,
            expectation=case.expectation,
            owasp=case.owasp,
            repeats=[],
            pass_rate=None,
            task_completion_rate=None,
            attack_success_rate=None,
            run_ids=[],
            skipped=case.skip_reason,
        )
    n = repeats if repeats is not None else case.repeats
    observed: list[tuple[RepeatResult, Observation | None]] = [
        run_repeat(case, i + 1, executor, judge) for i in range(n)
    ]
    results = [r for r, _ in observed]
    signatures = [_signature(o) for _, o in observed]
    identical = None if n < 2 or any(s is None for s in signatures) else len(set(signatures)) == 1
    return CaseResult(
        case_id=case.id,
        group=case.group,
        kind=case.kind,
        title=case.title,
        expectation=case.expectation,
        owasp=case.owasp,
        repeats=results,
        pass_rate=sum(1 for r in results if r.passed) / n,
        task_completion_rate=_rate([r.task_completed for r in results])
        if case.kind == "adversarial"
        else None,
        attack_success_rate=_rate([r.attack_succeeded for r in results])
        if case.kind == "adversarial"
        else None,
        run_ids=[r.run_id for r in results],
        repeats_identical=identical,
    )


def _signature(obs: Observation | None) -> str | None:
    """What must not vary across repeats: ranks, exclusions with rules, the prompt hash."""
    if obs is None or obs.bundle is None:
        return None
    b = obs.bundle
    rows = [
        (c.composition, c.rank, None if c.excluded is None else c.excluded.rule.value)
        for c in b.candidates
    ]
    return json.dumps({"rows": rows, "prompt_hash": b.run.prompt_hash}, sort_keys=True)


def run_suite(
    cases: list[Case],
    executor: Executor,
    judge: Judge,
    *,
    suite: str,
    repeats: dict[str, int] | None = None,
) -> SuiteResult:
    repeats = repeats or {}
    ordered = order_cases(cases)
    results = [run_case(c, executor, judge, repeats.get(c.id)) for c in ordered]
    return SuiteResult(
        suite=suite,
        executor=executor.name,
        judge=judge.name,
        cases=results,
        passed_cases=sum(1 for r in results if r.pass_rate == 1.0),
        total_cases=len(results),
        git_commit=git_commit(),
        config_sha=effective_config_sha(),
        preregistration=compare(),
    )


def write_results(result: SuiteResult, out_dir: Path = RESULTS_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{result.suite}.json"
    path.write_text(json.dumps(result.model_dump(mode="json"), indent=1, sort_keys=True) + "\n")
    return path


def parse_repeats(specs: list[str]) -> dict[str, int]:
    """['G1=5', 'A1=2'] -> {'G1': 5, 'A1': 2}"""
    out: dict[str, int] = {}
    for s in specs:
        case_id, _, n = s.partition("=")
        if not n.isdigit() or int(n) < 1:
            raise ValueError(f"bad --repeats entry {s!r}; use ID=N")
        out[case_id] = int(n)
    return out


def main(suite: str = "all") -> int:
    """Entry point for `materials-triage eval --suite X` (Track B's CLI): the same run as
    `python -m evals run --suite X` with the defaults (pipeline executor, scripted model,
    cassettes)."""
    from evals.__main__ import main as cli_main

    return cli_main(["run", "--suite", suite])
