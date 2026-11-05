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

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.judge import SAMPLE_PATH, agreement_rate  # noqa: E402
from evals.preregistration import PREREG_PATH, compare  # noqa: E402
from evals.runner import RESULTS_DIR as EVAL_RESULTS  # noqa: E402
from validation.report import CALIBRATION_JSON, VALIDATION_JSON  # noqa: E402

DEFAULT_OUT = ROOT / "docs" / "EVAL.md"
SCORING_TESTS = ROOT / "tests" / "scoring"


DETERMINISM_NOTE = (
    "Determinism covers the prompts, the data, and the scoring: the same settings give "
    "byte-identical prompts, the same recorded data gives the same values, and the scorer "
    "ranks the same inputs the same way with ties broken by composition. Live evidence "
    "labels can vary between runs on a cold classifier cache, because the model labels each "
    "abstract; the cache keeps them fixed once read, and `materials-triage diff` attributes "
    "a rank change from a label to the model."
)


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


def headline_lines(
    live_named: list[tuple[str, dict[str, Any]]], notes: dict[str, Any]
) -> list[str]:
    """The live results marked headline in notes.yaml, as counts with their denominators."""
    out: list[str] = []
    for name, suite in live_named:
        if not (notes.get(name) or {}).get("headline"):
            continue
        cases = [c for c in suite["cases"] if not c.get("skipped")]
        repeats = sum(len(c["repeats"]) for c in cases)
        line = (
            f"- {suite['suite']} on {suite['executor'].split(', ', 1)[-1]}: "
            f"{suite['passed_cases']} of {suite['total_cases']} cases passed "
            f"({repeats} repeat(s) in total), commit `{suite['git_commit'][:7]}`"
        )
        attacks = [c for c in cases if c.get("kind") == "adversarial"]
        if attacks:
            hit = sum(1 for c in attacks for r in c["repeats"] if r.get("attack_succeeded"))
            line += f"; attack success {hit} of {sum(len(c['repeats']) for c in attacks)}"
        out.append(line + ".")
    return out


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
            "| Repeats | Repeats identical | Run ids |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for c in suite["cases"]:
            owasp = "" if c["owasp"] is None else f"{c['owasp']['id']} {c['owasp']['name']}"
            if c.get("skipped"):
                out.append(
                    f"| {c['case_id']} | {c['kind']} | {owasp} | skipped | n/a | n/a | 0 | n/a | |"
                )
                continue
            ident = c.get("repeats_identical")
            out.append(
                f"| {c['case_id']} | {c['kind']} | {owasp} | {_pct(c['pass_rate'])} | "
                f"{_pct(c['task_completion_rate'])} | {_pct(c['attack_success_rate'])} | "
                f"{len(c['repeats'])} | {'n/a' if ident is None else ('yes' if ident else 'no')} "
                f"| {', '.join(c['run_ids'])} |"
            )
        skipped = [c for c in suite["cases"] if c.get("skipped")]
        if skipped:
            out.append("")
            out.append(f"Skipped: {len(skipped)} case(s) the harness cannot run; reasons below.")
        out.append("")
        for c in suite["cases"]:
            if c["case_id"] in seen:
                continue
            seen.add(c["case_id"])
            out += [f"### {c['case_id']}: {c['title']}", "", f"Expectation: {c['expectation']}", ""]
            if c.get("skipped"):
                out += [f"Not run: {c['skipped']}", ""]
                continue
            if c.get("repeats_identical") is not None:
                out.append(
                    "Repeats identical in ranks, exclusions and prompt hash: "
                    + ("yes" if c["repeats_identical"] else "no")
                    + "."
                )
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
            "second configuration described below the table; the two data-level columns are "
            "Yim's figure of merit against gap x e_total from our records, paired by structure "
            "with no scoring policy, defined below the table: PBE gap on every paired row, and "
            "the experimental median over the rows that have one.",
            "",
            "| Table | Compositions in table | Ranked (default) | rho (default) "
            "| Ranked (Yim-like) | rho (Yim-like) | Paired rows (data-level) "
            "| rho (data-level, PBE) | Rows with experimental | rho (data-level, experimental) "
            "| Note |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        data_tables = {t["table"]: t for t in val.get("data_level", {}).get("tables", [])}
        for t in yim["tables"]:
            note = _table_note(t)
            lt = like_tables.get(t["table"])
            if lt is None:
                like_cells = "| not run | not run "
            else:
                like_cells = f"| {lt['n_ranked']} | {_num(lt['rho'])} "
                if lt["excluded"] != t["excluded"] or lt["absent"] != t["absent"]:
                    note = (note + "; " if note else "") + "Yim-like " + _table_note(lt)
            dl = data_tables.get(t["table"])
            data_cells = (
                "| not run | not run | not run | not run "
                if dl is None
                else (
                    f"| {dl['n_paired']} of {dl['n_rows']} | {_num(dl['rho_pbe'])} "
                    f"| {dl['n_experimental']} | {_num(dl['rho_experimental'])} "
                )
            )
            out.append(
                f"| {t['table']} | {t['n_in_table']} | {t['n_ranked']} "
                f"| {_num(t['rho'])} {like_cells}{data_cells}| {note} |"
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
                like["label"],
                "",
                f"- weights: {weights}",
                f"- dielectric target band: {band_text}",
                f"- config sha `{like['config_sha'][:12]}` (default run `{s['config_sha'][:12]}`)",
            ]
        dl_report = val.get("data_level")
        out.append("")
        if dl_report is None:
            out.append("Data-level correlation: not run.")
        else:
            out += [f"Data-level correlation: {dl_report['definition']}", ""]
            for dt in dl_report["tables"]:
                by_icsd = sum(1 for p in dt["points"] if p["match"] == "icsd")
                by_sg = dt["n_paired"] - by_icsd
                out.append(
                    f"- table {dt['table']}: {dt['n_paired']} of {dt['n_rows']} rows paired "
                    f"({by_icsd} by ICSD id, {by_sg} by composition and space group); "
                    f"rho (PBE) {_num(dt['rho_pbe'])}"
                    + (f" ({dt['reason_pbe']})" if dt["reason_pbe"] else "")
                    + f"; rows with an experimental median: {dt['n_experimental']}, "
                    f"rho (experimental) {_num(dt['rho_experimental'])}"
                    + (f" ({dt['reason_experimental']})" if dt["reason_experimental"] else "")
                )
                for u in dt["unpaired"]:
                    where = f" ({u['mp_id']})" if u["mp_id"] else ""
                    out.append(
                        f"  - unpaired: {u['name_as_printed']} ICSD {u['icsd']}{where}: "
                        f"{u['reason']}"
                    )
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
    history = pre.get("history") or []
    out = ["| Entry | Recorded | Commit | Config sha |", "|---|---|---|---|"]
    for h in history:
        out.append(
            f"| {h['label']} | {h['recorded_at']} | `{(h['git_commit'] or 'unknown')[:12]}` | "
            f"`{h['config_sha'][:12]}` |"
        )
    out += [
        "",
        f"Compared below against the latest entry, {pre.get('label', 'initial')}: pre-registered "
        f"{pre['recorded_at']} for scorer `{pre['scorer']}` at commit "
        f"`{pre['preregistered_commit'] or 'unknown'}`: "
        f"config sha `{pre['preregistered_config_sha'][:12]}`.",
        "The pre-registered sha is the config resolved with the default query. The run shas in "
        "the validation section include each run's query (candidate list, top_n, weight "
        "overrides), so they differ from it by design; only the comparison below says whether "
        "the config changed.",
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
    live_named = [
        (p.stem, json.loads(p.read_text())) for p in sorted((eval_results / "live").glob("*.json"))
    ]
    live = [d for _, d in live_named]
    notes_path = eval_results / "live" / "notes.yaml"
    live_notes = yaml.safe_load(notes_path.read_text()) if notes_path.exists() else {}
    lines = [
        "# Evaluation report",
        "",
        "Generated by `scripts/generate_eval_report.py` from results files written by code. "
        "Do not edit; re-run the script.",
        "",
        DETERMINISM_NOTE,
        "",
        "## Live model",
        "",
        *(
            [
                "Cases run with the configured provider (not the scripted model) on recorded "
                "data, judged by the judge named in each results file. Each count below gives "
                "its denominator; one repeat per case unless stated.",
                "",
                *headline_lines(live_named, live_notes or {}),
                "",
                *[
                    f"- `{name}`: {n['model']}, {n['date']}. {n['note']}"
                    for name, n in sorted(
                        (live_notes or {}).items(), key=lambda kv: not kv[1].get("headline")
                    )
                ],
                "",
                *case_sections(
                    [
                        d
                        for _, d in sorted(
                            live_named,
                            key=lambda nd: (
                                not ((live_notes or {}).get(nd[0]) or {}).get("headline")
                            ),
                        )
                    ]
                ),
            ]
            if live
            else ["No live-model results committed.", ""]
        ),
        "## Regression harness (scripted model)",
        "",
        "The full case list on a scripted model with fixed replies and a scripted judge. It "
        "checks that the pipeline, the guardrails in code, and the views behave as specified; "
        "it does not measure the live model.",
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
