"""Write docs/EVAL.md from the results files. The script writes the whole file; nothing in it is
typed by hand, and every number comes from a JSON file that code wrote.

Usage:
    uv run python scripts/generate_eval_report.py [--out docs/EVAL.md]

Inputs (each optional; a missing one is reported as missing, never invented):
    evals/results/*.json                 suite results from `python -m evals run`
    validation/results/validation.json   from `python -m validation run`
    validation/results/band_gap_calibration.json
    evals/preregistration.json           from `python -m evals prereg`
    evals/judge_sample.md                owner-graded judge sample
    tests/scoring/                       Track A's directional tests, run through pytest
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.judge import SAMPLE_PATH, agreement_rate  # noqa: E402
from evals.preregistration import PREREG_PATH, compare  # noqa: E402
from evals.runner import RESULTS_DIR as EVAL_RESULTS  # noqa: E402
from validation.report import CALIBRATION_JSON, VALIDATION_JSON  # noqa: E402

DEFAULT_OUT = ROOT / "docs" / "EVAL.md"
SCORING_TESTS = ROOT / "tests" / "scoring"


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.0f}%"


def _num(x: float | None, digits: int = 3) -> str:
    return "n/a" if x is None else f"{x:.{digits}f}"


def _table_note(t: dict[str, Any]) -> str:
    note = t["reason"] or ""
    if t["excluded"]:
        note = (
            (note + "; " if note else "")
            + "excluded: "
            + ", ".join(f"{e['composition']} ({e['rule']})" for e in t["excluded"])
        )
    if t["absent"]:
        note = (note + "; " if note else "") + "absent: " + ", ".join(t["absent"])
    return note


def _load(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    data: dict[str, Any] = json.loads(path.read_text())
    return data


# ----------------------------------------------------------------------------- eval cases


def case_sections(suites: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    if not suites:
        return ["No eval results found. Run `uv run python -m evals run`.", ""]
    seen: set[str] = set()
    for suite in suites:
        out += [
            f"Suite `{suite['suite']}`: {suite['passed_cases']} of {suite['total_cases']} cases "
            f"passed. Executor `{suite['executor']}`, judge `{suite['judge']}`, "
            f"commit `{suite['git_commit'] or 'unknown'}`, "
            f"config sha `{suite['config_sha'][:12]}`.",
            "",
            "| Case | Kind | OWASP | Pass rate | Task completion | Attack success "
            "| Repeats | Run ids |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for c in suite["cases"]:
            owasp = "" if c["owasp"] is None else f"{c['owasp']['id']} {c['owasp']['name']}"
            out.append(
                f"| {c['case_id']} | {c['kind']} | {owasp} | {_pct(c['pass_rate'])} | "
                f"{_pct(c['task_completion_rate'])} | {_pct(c['attack_success_rate'])} | "
                f"{len(c['repeats'])} | {', '.join(c['run_ids'])} |"
            )
        out.append("")
        for c in suite["cases"]:
            if c["case_id"] in seen:
                continue
            seen.add(c["case_id"])
            out += [f"### {c['case_id']}: {c['title']}", "", f"Expectation: {c['expectation']}", ""]
            failing = [
                (r["repeat"], ch) for r in c["repeats"] for ch in r["checks"] if not ch["passed"]
            ]
            errors = [(r["repeat"], e) for r in c["repeats"] for e in r["errors"]]
            n_checks = sum(len(r["checks"]) for r in c["repeats"])
            if not failing and not errors:
                out.append(
                    f"Observed: all {n_checks} checks passed across {len(c['repeats'])} repeat(s)."
                )
            else:
                out.append(f"Observed: {len(failing)} failing check(s), {len(errors)} error(s).")
                out.append("")
                out.append("Misses:")
                for rep, ch in failing:
                    out.append(f"- repeat {rep}, `{ch['name']}`: {ch['detail']}")
                for rep, e in errors:
                    out.append(f"- repeat {rep}, error: {e}")
            verdicts = [(r["repeat"], v) for r in c["repeats"] for v in r["judge"]]
            if verdicts:
                out.append("")
                out.append("Judge:")
                for rep, v in verdicts:
                    out.append(
                        f"- repeat {rep}, {v['item']}: {v['verdict']} ({v['judge']}): {v['reason']}"
                    )
            out.append("")
    return out


# ----------------------------------------------------------------------------- validation


def validation_sections(val: dict[str, Any] | None, cal: dict[str, Any] | None) -> list[str]:
    out: list[str] = []
    if val is None:
        out += ["No validation results found. Run `uv run python -m validation run`.", ""]
    else:
        s = val["scorer"]
        out += [
            f"Scorer `{s['name']}`, profile `{s['profile_name']}` "
            f"version `{s['profile_version']}`, config sha `{s['config_sha'][:12]}`, "
            f"commit `{val['inputs']['git_commit'] or 'unknown'}`.",
        ]
        yim = val["yim"]
        like = val.get("yim_like")
        like_tables = {} if like is None else {t["table"]: t for t in like["tables"]}
        out += [
            "",
            f"### Yim 2015 positives ({yim['doi']})",
            "",
            f"Polymorph rule: {yim['polymorph_rule']}. Fixture sha `{yim['fixture_sha256'][:12]}`.",
            "",
            "Spearman rho is the scorer's rank against the Yim figure-of-merit order within each "
            "table. The default column is the profile as entered; the Yim-like column is the "
            "second configuration described below the table.",
            "",
            "| Table | In table | Ranked (default) | rho (default) "
            "| Ranked (Yim-like) | rho (Yim-like) | Note |",
            "|---|---|---|---|---|---|---|",
        ]
        for t in yim["tables"]:
            note = _table_note(t)
            lt = like_tables.get(t["table"])
            if lt is None:
                like_cells = "| not run | not run "
            else:
                like_cells = f"| {lt['n_ranked']} | {_num(lt['rho'])} "
                if lt["excluded"] != t["excluded"] or lt["absent"] != t["absent"]:
                    note = (note + "; " if note else "") + "Yim-like " + _table_note(lt)
            out.append(
                f"| {t['table']} | {t['n_in_table']} | {t['n_ranked']} "
                f"| {_num(t['rho'])} {like_cells}| {note} |"
            )
        out.append("")
        if like is None:
            out.append(
                "Yim-like configuration: not run (the scorer in use takes no weight overrides)."
            )
        else:
            weights = ", ".join(f"{k} {v:g}" for k, v in like["weights"].items())
            band = like["dielectric_target_band"]
            band_text = (
                "none" if band is None else f"[{band[0]:g}, {band[1]:g}]"
            ) + f" (status {like['dielectric_target_band_status']})"
            out += [
                f"Yim-like configuration: {like['label']}",
                "",
                f"- weights: {weights}",
                f"- dielectric target band: {band_text}",
                f"- config sha `{like['config_sha'][:12]}` (default run `{s['config_sha'][:12]}`)",
            ]
        out += ["", "Negatives (must be excluded or flagged with the rule shown):", ""]
        for n in yim["negatives"]:
            rule = n["rule"] or (", ".join(n["flags"]) if n["flags"] else "none")
            out.append(f"- {n['composition']}: {n['status']} ({rule})")
        out += ["", 'Evidence tier "no abstract" (kept in the correlation, listed here):', ""]
        if not yim["no_abstract"]:
            out.append("- none")
        for r in yim["no_abstract"]:
            where = (
                f"rank {r['rank']}" if r["rank"] is not None else f"excluded: {r['excluded_rule']}"
            )
            out.append(f"- {r['composition']}: {r['state']}, {where}")
        rc = val["recall"]
        out += [
            "",
            f"### Known-dielectric recall at K={rc['k']}",
            "",
            f"Known list ({rc['source']}): {', '.join(rc['known'])}. Recall {_pct(rc['recall'])}.",
            "",
        ]
        for h in rc["hits"]:
            out.append(f"- {h['composition']}: rank {h['rank']}")
        for m in rc["misses"]:
            out.append(f"- {m['composition']}: miss, {m['why']}")
        out += ["", "### Negative controls", ""]
        for name, block in val["negative_controls"].items():
            out.append(f"{name}: all handled = {block['all_handled']}")
            for o in block["named"]:
                rule = o["rule"] or (", ".join(o["flags"]) if o["flags"] else "none")
                out.append(f"- {o['composition']}: {o['status']} ({rule})")
            for o in block["theoretical_only"]:
                out.append(
                    f"- {o['composition']} (no observed polymorph): {o['status']} "
                    f"({o['rule'] or ', '.join(o['flags']) or 'none'})"
                )
            out.append("")
    if cal is None:
        out += ["No calibration results found.", ""]
    else:
        out += ["### Band gap calibration (recorded oxides, experimental median as reference)", ""]
        for m in (cal["tbmbj"], cal["pbe"]):
            out.append(
                f"- {m['method']}: n={m['n']}, MAE {_num(m['mae'])} eV; without a pair: "
                f"{', '.join(m['without_pair']) or 'none'}"
            )
            for p in m["pairs"]:
                out.append(
                    f"  - {p['composition']} ({p['mp_id']}): computed {p['computed']:.3f}, "
                    f"experimental median {p['experimental_median']:.3f} "
                    f"(n={p['experimental_n']}), error {p['abs_error']:.3f}"
                )
        out += [
            "",
            f"Conflict tolerance: {_num(cal['conflict_tolerance_ev'])} eV. {cal['derivation']}. "
            f"Data sha `{cal['data_sha256'][:12]}`.",
            "",
        ]
    return out


def preregistration_section(pre: dict[str, Any] | None) -> list[str]:
    if pre is None:
        return [
            "No pre-registration record. Run `uv run python -m evals prereg` before validation.",
            "",
        ]
    out = [
        f"Pre-registered {pre['recorded_at']} for scorer `{pre['scorer']}` at commit "
        f"`{pre['preregistered_commit'] or 'unknown'}`: "
        f"config sha `{pre['preregistered_config_sha'][:12]}`.",
    ]
    if pre["config_tuned_after_preregistration"]:
        out.append(
            "Config was tuned after pre-registration: "
            f"current sha `{pre['current_config_sha'][:12]}`; "
            f"files changed: {', '.join(pre['config_files_changed']) or 'none listed'}."
        )
    else:
        out.append("Current config sha matches the pre-registered one.")
    out.append("Data unchanged since pre-registration: " + str(pre["data_unchanged"]) + ".")
    return out + [""]


def judge_section(path: Path) -> list[str]:
    if not path.exists():
        return ["No judge sample written yet (`uv run python -m evals judge-sample`).", ""]
    a = agreement_rate(path)
    if a["graded"] == 0:
        return [f"Judge sample has {a['rows']} rows; not yet graded by the owner.", ""]
    return [
        f"Owner graded {a['graded']} of {a['rows']} judge verdicts; agreement "
        f"{_pct(a['agreement_rate'])} ({a['agreed']} agreed).",
        "",
    ]


def directional_section(tests_dir: Path) -> list[str]:
    if not tests_dir.exists():
        return [
            "Track A's directional tests are not on this branch yet (tests/scoring absent).",
            "",
        ]
    with tempfile.TemporaryDirectory() as tmp:
        junit = Path(tmp) / "scoring.xml"
        subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(tests_dir), f"--junitxml={junit}"],
            check=False,
            capture_output=True,
            cwd=ROOT,
        )
        if not junit.exists():
            return ["Could not run tests/scoring.", ""]
        root = ET.parse(junit).getroot()
        suites = [root] if root.tag == "testsuite" else list(root)
        tests = sum(int(s.get("tests", 0)) for s in suites)
        failures = sum(int(s.get("failures", 0)) + int(s.get("errors", 0)) for s in suites)
        skipped = sum(int(s.get("skipped", 0)) for s in suites)
        names = sorted(tc.get("name", "") for s in suites for tc in s.iter("testcase"))
    out = [
        f"Track A's directional tests (tests/scoring): {tests - failures - skipped} passed, "
        f"{failures} failed, {skipped} skipped of {tests}. "
        "Not duplicated here; named for reference:",
        "",
    ]
    out += [f"- {n}" for n in names]
    return out + [""]


# ----------------------------------------------------------------------------- assemble


def build(
    *,
    eval_results: Path = EVAL_RESULTS,
    validation_json: Path = VALIDATION_JSON,
    calibration_json: Path = CALIBRATION_JSON,
    prereg_path: Path = PREREG_PATH,
    judge_sample: Path = SAMPLE_PATH,
    scoring_tests: Path = SCORING_TESTS,
) -> str:
    suites = [json.loads(p.read_text()) for p in sorted(eval_results.glob("*.json"))]
    lines = [
        "# Evaluation report",
        "",
        "Generated by `scripts/generate_eval_report.py` from results files written by code. "
        "Do not edit; re-run the script.",
        "",
        "## Eval cases",
        "",
        *case_sections(suites),
        "## Validation",
        "",
        *validation_sections(_load(validation_json), _load(calibration_json)),
        "## Pre-registration",
        "",
        *preregistration_section(compare(prereg_path)),
        "## Judge agreement",
        "",
        *judge_section(judge_sample),
        "## Directional tests",
        "",
        *directional_section(scoring_tests),
    ]
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()
    out = Path(args.out)
    out.write_text(build())
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
