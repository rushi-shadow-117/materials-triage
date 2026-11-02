"""Yim et al. 2015 ground truth, read from fixtures/validation/yim2015.yaml.

The paper lists polymorphs (one row per ICSD entry); the scorer ranks composition groups. The
owner's rule (2026-11-02): one entry per composition per table, ordered by its highest f_fom in
that table. Formulas are reduced with pymatgen so "c-BeO" and "BeO" are the same group; the
phase prefix is kept as data. Numbers are the paper's and are only parsed, never changed.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

from materials_triage.adapters.common import reduced_formula

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "fixtures" / "validation" / "yim2015.yaml"


@dataclass(frozen=True)
class YimRow:
    name_as_printed: str
    formula: str
    composition: str  # reduced formula (pymatgen)
    phase_prefix: str | None
    icsd: str
    spacegroup_number: int | None
    kappa: float
    band_gap_ev: float | None  # None where the fixture's column is awaiting re-entry
    f_fom: float
    table: int


@dataclass(frozen=True)
class YimGroundTruth:
    rows: tuple[YimRow, ...]
    negatives: tuple[str, ...]  # reduced formulas
    citation: str
    doi: str
    fixture_sha256: str

    def tables(self) -> list[int]:
        return sorted({r.table for r in self.rows})

    def compositions(self) -> list[str]:
        return sorted({r.composition for r in self.rows})

    def table_order(self, table: int) -> list[tuple[str, float]]:
        """(composition, best f_fom) for one table, best first; ties broken by composition."""
        best: dict[str, float] = {}
        for r in self.rows:
            if r.table != table:
                continue
            if r.composition not in best or r.f_fom > best[r.composition]:
                best[r.composition] = r.f_fom
        return sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))


def _opt_float(x: object) -> float | None:
    return None if x is None else float(str(x))


def _opt_int(x: object) -> int | None:
    return None if x is None else int(str(x))


def load_yim(path: Path = DEFAULT_PATH) -> YimGroundTruth:
    text = path.read_text()
    data = yaml.safe_load(text)
    if data.get("schema_version") != 0 or data.get("status") != "entered":
        raise ValueError(f"{path} is not an entered schema_version 0 fixture")
    rows = tuple(
        YimRow(
            name_as_printed=str(p["name_as_printed"]),
            formula=str(p["formula"]),
            composition=reduced_formula(str(p["formula"])),
            phase_prefix=None if p.get("phase_prefix") is None else str(p["phase_prefix"]),
            icsd=str(p["icsd"]),
            spacegroup_number=_opt_int(p.get("spacegroup_number")),
            kappa=float(str(p["kappa"])),
            band_gap_ev=_opt_float(p.get("band_gap_ev")),
            f_fom=float(str(p["f_fom"])),
            table=int(p["table"]),
        )
        for p in data["positives"]
    )
    negatives = tuple(reduced_formula(f) for f in data["negatives"]["compositions"])
    return YimGroundTruth(
        rows=rows,
        negatives=negatives,
        citation=str(data["source"]["citation"]),
        doi=str(data["source"]["doi"]),
        fixture_sha256=hashlib.sha256(text.encode()).hexdigest(),
    )
