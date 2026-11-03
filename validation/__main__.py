"""uv run python -m validation run [--out DIR]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from validation import track_a
from validation.report import RESULTS_DIR, YimLikeRun, run_validation


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="validation")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="score the validation sets and write results JSON")
    run.add_argument("--out", default=str(RESULTS_DIR))
    args = ap.parse_args(argv)
    if args.cmd == "run":
        report = run_validation(
            track_a.score_with_track_a,
            scorer_name="track_a",
            out_dir=Path(args.out),
            yim_like=YimLikeRun(
                score=track_a.score_with_track_a_yim_like,
                description=track_a.yim_like_description(),
            ),
        )
        print("scorer:", report["scorer"]["name"])
        yim = report["yim"]
        like = report["yim_like"]
        like_tables = {} if like is None else {t["table"]: t for t in like["tables"]}
        data_tables = {t["table"]: t for t in report["data_level"]["tables"]}
        for t in yim["tables"]:
            line = (
                f"table {t['table']}: ranked {t['n_ranked']} of {t['n_in_table']}, rho={t['rho']}"
            )
            lt = like_tables.get(t["table"])
            if lt is not None:
                line += f"; Yim-like: ranked {lt['n_ranked']}, rho={lt['rho']}"
            dl = data_tables.get(t["table"])
            if dl is not None:
                line += f"; data-level: paired {dl['n_paired']}, rho={dl['rho']}"
            print(line)
        print("recall:", report["recall"]["recall"], "misses:", report["recall"]["misses"])
        print("wrote", Path(args.out) / "validation.json")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
