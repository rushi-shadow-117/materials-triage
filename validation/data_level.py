"""Data-level Yim comparison, paired by structure: Spearman between Yim's figure of merit and
(PBE gap x e_total) read from our records for the same structures. No scoring policy: no
weights, no normalization, no exclusions.

Pairing: each Yim row names an ICSD id. The row pairs with the Materials Project polymorph
whose recorded database ids carry that ICSD id; when none does, with the MP polymorph of the
same reduced composition and the row's space group number (lowest hull first when several);
otherwise the row is unpaired and listed with the reason. A paired row without a PBE gap or
an e_total on that polymorph is listed too and left out of rho.

Values: the gap is the Materials Project PBE gap on the paired polymorph (one source for every
row); e_total is the MP DFPT total dielectric constant on it. The experimental median from
the expt_gap snapshot is shown as a separate column where the composition has one, and a
second rho over those rows uses it in place of the PBE gap. Nothing is filled. Owner request
2026-11-03.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from materials_triage.records import Polymorph
from materials_triage.scoring.polymorphs import mp_polymorphs
from validation.groups import LoadedGroup
from validation.spearman import spearman
from validation.yim import YimGroundTruth, YimRow

PBE_KEY = "mp_summary"
E_TOTAL_KEY = "e_total"

DEFINITION = (
    "Spearman rho between Yim's figure of merit and (PBE gap x e_total) from our records, "
    "paired by structure, no scoring policy. Pairing: the Yim row's ICSD id against the MP "
    "polymorph's recorded database ids; else the same reduced composition and the row's space "
    "group number; else unpaired. Gap: Materials Project PBE on the paired polymorph, one "
    "source for every row. e_total: MP DFPT total dielectric constant on it. The experimental "
    "median (expt_gap snapshot) is a separate column where present, with its own rho over "
    "those rows. Rows without both values are listed and left out; nothing is filled."
)


@dataclass(frozen=True)
class RowPoint:
    name_as_printed: str
    composition: str
    icsd: str
    yim_spacegroup: int | None
    mp_id: str
    mp_spacegroup: int | None
    match: str  # icsd | composition_spacegroup
    yim_best_fom: float
    pbe_gap_ev: float
    e_total: float
    product: float
    experimental_median_ev: float | None
    experimental_product: float | None


@dataclass(frozen=True)
class UnpairedRow:
    name_as_printed: str
    composition: str
    icsd: str
    yim_spacegroup: int | None
    mp_id: str | None  # set when a structure matched but a value is missing
    reason: str


@dataclass(frozen=True)
class DataLevelTable:
    table: int
    n_rows: int
    n_paired: int
    rho_pbe: float | None
    reason_pbe: str | None
    n_experimental: int
    rho_experimental: float | None
    reason_experimental: str | None
    points: list[RowPoint]
    unpaired: list[UnpairedRow]


@dataclass(frozen=True)
class DataLevelReport:
    definition: str
    tables: list[DataLevelTable]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _value(p: Polymorph, field: dict[str, Any], key: str) -> float | None:
    v = field.get(key)
    return None if v is None else v.value


def match_polymorph(row: YimRow, lg: LoadedGroup) -> tuple[Polymorph | None, str]:
    """The MP polymorph for a Yim row, with how it matched or why it did not."""
    polys = mp_polymorphs(lg.group)
    try:
        icsd = int(row.icsd)
    except ValueError:
        icsd = None
    if icsd is not None:
        for p in polys:
            if icsd in p.ids.icsd:
                return p, "icsd"
    if row.spacegroup_number is None:
        return None, "ICSD id not among the recorded MP ids; fixture row has no space group"
    for p in polys:
        if p.spacegroup_number == row.spacegroup_number:
            return p, "composition_spacegroup"
    return None, (
        "ICSD id not among the recorded MP ids; no MP polymorph with space group "
        f"{row.spacegroup_number}"
    )


def row_point(row: YimRow, lg: LoadedGroup | None) -> RowPoint | UnpairedRow:
    def unpaired(reason: str, mp_id: str | None = None) -> UnpairedRow:
        return UnpairedRow(
            name_as_printed=row.name_as_printed,
            composition=row.composition,
            icsd=row.icsd,
            yim_spacegroup=row.spacegroup_number,
            mp_id=mp_id,
            reason=reason,
        )

    if lg is None:
        return unpaired("composition not loaded")
    p, how = match_polymorph(row, lg)
    if p is None:
        return unpaired(how)
    gap = _value(p, p.band_gap, PBE_KEY)
    e_total = _value(p, p.dielectric, E_TOTAL_KEY)
    missing = [name for name, v in (("PBE gap", gap), ("e_total", e_total)) if v is None]
    if missing or gap is None or e_total is None:
        return unpaired(f"matched by {how}; missing {' and '.join(missing)}", p.ids.mp)
    agg = lg.group.experimental_gaps
    exp = None if agg is None else agg.median
    assert p.ids.mp is not None
    return RowPoint(
        name_as_printed=row.name_as_printed,
        composition=row.composition,
        icsd=row.icsd,
        yim_spacegroup=row.spacegroup_number,
        mp_id=p.ids.mp,
        mp_spacegroup=p.spacegroup_number,
        match=how,
        yim_best_fom=row.f_fom,
        pbe_gap_ev=gap,
        e_total=e_total,
        product=gap * e_total,
        experimental_median_ev=exp,
        experimental_product=None if exp is None else exp * e_total,
    )


def data_level_table(
    groups: dict[str, LoadedGroup], gt: YimGroundTruth, table: int
) -> DataLevelTable:
    rows = [r for r in gt.rows if r.table == table]
    points: list[RowPoint] = []
    unpaired: list[UnpairedRow] = []
    for row in rows:
        point = row_point(row, groups.get(row.composition))
        if isinstance(point, RowPoint):
            points.append(point)
        else:
            unpaired.append(point)
    pbe = spearman([p.yim_best_fom for p in points], [p.product for p in points])
    with_exp = [p for p in points if p.experimental_product is not None]
    exp = spearman(
        [p.yim_best_fom for p in with_exp], [p.experimental_product or 0.0 for p in with_exp]
    )
    return DataLevelTable(
        table=table,
        n_rows=len(rows),
        n_paired=len(points),
        rho_pbe=pbe.rho,
        reason_pbe=pbe.reason,
        n_experimental=len(with_exp),
        rho_experimental=exp.rho,
        reason_experimental=exp.reason,
        points=points,
        unpaired=unpaired,
    )


def data_level_report(groups: dict[str, LoadedGroup], gt: YimGroundTruth) -> DataLevelReport:
    return DataLevelReport(
        definition=DEFINITION,
        tables=[data_level_table(groups, gt, t) for t in gt.tables()],
    )
