"""Load case files. One YAML per query under evals/cases/. The brief's required pair, A1 and
F1, come first in every listing; the rest follow in id order (letter, then number)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from evals.schema import Case

ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = ROOT / "evals" / "cases"
REQUIRED_PAIR = ("A1", "F1")


def _id_key(case_id: str) -> tuple[str, int, str]:
    m = re.fullmatch(r"([A-Z]+)(\d+)([a-z]?)", case_id)
    if m is None:
        return (case_id, 0, "")
    return (m.group(1), int(m.group(2)), m.group(3))


def order_cases(cases: list[Case]) -> list[Case]:
    by_id = {c.id: c for c in cases}
    first = [by_id[i] for i in REQUIRED_PAIR if i in by_id]
    rest = sorted((c for c in cases if c.id not in REQUIRED_PAIR), key=lambda c: _id_key(c.id))
    return first + rest


def load_cases(directory: Path = CASES_DIR) -> list[Case]:
    cases: list[Case] = []
    for path in sorted(directory.glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        case = Case.model_validate(data)
        if case.id != path.stem:
            raise ValueError(f"{path.name}: id {case.id!r} does not match the file name")
        cases.append(case)
    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate case ids: {ids}")
    return order_cases(cases)


def select(cases: list[Case], suite: str) -> list[Case]:
    """'all', a group letter, one case id, or a comma list of ids (in case order)."""
    if suite == "all":
        return cases
    if "," in suite:
        wanted = [s.strip() for s in suite.split(",") if s.strip()]
        unknown = sorted(set(wanted) - {c.id for c in cases})
        if unknown:
            raise KeyError(f"no case {unknown}")
        return [c for c in cases if c.id in wanted]
    if len(suite) == 1 and suite.isalpha():
        return [c for c in cases if c.group == suite.upper()]
    chosen = [c for c in cases if c.id == suite]
    if not chosen:
        raise KeyError(f"no case or group {suite!r}")
    return chosen
