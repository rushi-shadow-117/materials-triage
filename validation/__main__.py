"""uv run python -m validation run [--out DIR]"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

from validation.report import RESULTS_DIR, run_validation


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="validation")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="score the validation sets and write results JSON")
    run.add_argument("--out", default=str(RESULTS_DIR))
    args = ap.parse_args(argv)
    if args.cmd == "run":
        if importlib.util.find_spec("materials_triage.scoring.scorer") is not None:
            # Wired in Track E step 12, after the rebase on Track A.
            raise SystemExit("Track A scorer present; wire validation.report to it")
        from validation.stand_in import score_stand_in

        report = run_validation(score_stand_in, scorer_name="stand_in", out_dir=Path(args.out))
        yim = report["yim"]
        for t in yim["tables"]:
            print(
                f"table {t['table']}: ranked {t['n_ranked']} of {t['n_in_table']}, rho={t['rho']}"
            )
        print("recall:", report["recall"]["recall"], "misses:", report["recall"]["misses"])
        print("wrote", Path(args.out) / "validation.json")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
