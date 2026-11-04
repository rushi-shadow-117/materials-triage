"""uv run python -m evals run [--suite all|A|F|A1] [--repeats G1=5 ...] [--out DIR]
uv run python -m evals prereg
uv run python -m evals judge-sample [--suite all]
uv run python -m evals agreement"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from evals import costs
from evals.cases import load_cases, select
from evals.execute import ROOT, Executor, PipelineExecutor, SampleBundleExecutor, injected_fetch
from evals.judge import SAMPLE_PATH, agreement_rate, make_judge, write_judge_sample
from evals.preregistration import PREREG_PATH, preregister
from evals.runner import RESULTS_DIR, parse_repeats, run_suite, write_results
from evals.schema import Case


def live_estimate_ok(cases: list[Case], executor: PipelineExecutor, *, judge_live: bool) -> bool:
    """Print the expected and worst-case API calls per case; refuse when the expected total
    exceeds EVAL_MAX_LIVE_CALLS. Nothing is sent before this check."""
    from materials_triage.cli import wiring

    settings = executor.settings()
    cache = wiring.make_cache(settings)
    fetch = wiring.CassetteFetch()
    total_expected = total_worst = 0
    print(
        f"live eval: model {settings.llm_model}, classify cap {costs.max_classify_calls()} per case"
    )
    for case in cases:
        injected: dict[str, Any] = {}
        if case.injected_fixture and case.injected_into:
            base, call = injected_fetch(
                fetch, fixture=ROOT / case.injected_fixture, composition=case.injected_into
            )
            injected[case.injected_into] = base(call)
        layers = executor.layers_for(case)
        expected, worst = costs.estimate(
            case,
            fetch=fetch,
            cache=cache,
            model=settings.llm_model,
            anchors=list(layers.profile.anchors),
            injected=injected,
            judge_live=judge_live,
        )
        executor.worst_calls[case.id] = worst
        total_expected += expected
        total_worst += worst
        print(f"  {case.id}: expected {expected} calls, worst case {worst}")
    limit = costs.max_live_calls()
    print(f"  total: expected {total_expected}, worst case {total_worst}; limit {limit}")
    if total_expected > limit:
        print(f"refused: expected {total_expected} calls exceeds EVAL_MAX_LIVE_CALLS={limit}")
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="evals")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="run cases, write results JSON")
    js = sub.add_parser("judge-sample", help="write evals/judge_sample.md for owner grading")
    for p in (run, js):
        p.add_argument("--suite", default="all")
        p.add_argument("--repeats", nargs="*", default=[], help="ID=N overrides")
        p.add_argument(
            "--executor",
            choices=["pipeline", "sample"],
            default="pipeline",
            help="pipeline: Track B's pipeline end to end; sample: the sample bundle",
        )
        p.add_argument(
            "--llm",
            choices=["fake", "live", "none"],
            default="fake",
            help="fake: scripted model (CI); live: the configured provider; none: no LLM steps",
        )
        p.add_argument(
            "--fetch",
            choices=["cassettes", "store"],
            default="cassettes",
            help="cassettes: recorded files; store: the seeded store with FETCH_MODE=replay",
        )
    run.add_argument("--out", default=str(RESULTS_DIR))
    saved = sub.add_parser("score-saved", help="grade a saved live bundle; no API call")
    saved.add_argument("--case", required=True)
    saved.add_argument("--bundle", required=True)
    saved.add_argument("--label", required=True, help="executor label, e.g. model and date")
    saved.add_argument("--out", default=str(RESULTS_DIR / "live"))
    pre = sub.add_parser("prereg", help="record the scoring config sha before validation runs")
    pre.add_argument("--scorer", default="track_a")
    pre.add_argument("--label", default="initial (Track E)", help="name of this entry")
    sub.add_parser("agreement", help="report owner agreement with the judge sample")
    args = ap.parse_args(argv)

    if args.cmd == "prereg":
        rec = preregister(scorer_name=args.scorer, label=args.label)
        print(
            f"pre-registered config sha {rec['config_sha'][:12]} "
            f"at {rec['recorded_at']} -> {PREREG_PATH}"
        )
        return 0
    if args.cmd == "score-saved":
        from evals.execute import SavedBundleExecutor
        from evals.judge import NoJudge

        chosen = select(load_cases(), args.case)
        ex = SavedBundleExecutor({args.case: Path(args.bundle)}, label=args.label)
        result = run_suite(chosen, ex, NoJudge(), suite=f"{args.case}_saved")
        path = write_results(result, Path(args.out))
        print(f"{result.passed_cases} of {result.total_cases} cases passed -> {path}")
        return 0
    if args.cmd == "agreement":
        if not SAMPLE_PATH.exists():
            print(f"no judge sample at {SAMPLE_PATH}; run `python -m evals judge-sample` first")
            return 1
        print(json.dumps(agreement_rate(), indent=1))
        return 0

    cases = select(load_cases(), args.suite)
    executor: Executor
    if args.executor == "sample":
        executor = SampleBundleExecutor()
    else:
        executor = PipelineExecutor(llm=args.llm, fetch_source=args.fetch)
    judge = make_judge()
    if (
        args.llm == "live"
        and isinstance(executor, PipelineExecutor)
        and not live_estimate_ok(cases, executor, judge_live=judge.name != "fake")
    ):
        return 2
    result = run_suite(
        cases, executor, judge, suite=args.suite, repeats=parse_repeats(args.repeats)
    )
    if args.cmd == "judge-sample":
        rows = [(c.case_id, r.repeat, v) for c in result.cases for r in c.repeats for v in r.judge]
        write_judge_sample(rows)
        print(f"wrote {len(rows)} verdicts for grading")
        return 0
    path = write_results(result, Path(args.out))
    for c in result.cases:
        extra = (
            ""
            if c.kind == "normal"
            else f" task={c.task_completion_rate} attack={c.attack_success_rate}"
        )
        if c.skipped:
            print(f"{c.case_id}: skipped ({c.skipped[:60]}...)")
            continue
        rate = "n/a" if c.pass_rate is None else f"{c.pass_rate:.2f}"
        ident = "" if c.repeats_identical is None else f" identical={c.repeats_identical}"
        print(f"{c.case_id}: pass_rate={rate} repeats={len(c.repeats)}{ident}{extra}")
    print(f"{result.passed_cases} of {result.total_cases} cases passed -> {path}")
    # A miss is a finding in the results, not a failed command: exit 0 once the suite ran.
    return 0


if __name__ == "__main__":
    sys.exit(main())
