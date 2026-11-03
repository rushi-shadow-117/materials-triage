"""Data-level Yim comparison: Spearman between Yim's figure of merit and best-available gap
times e_total, computed from our records for the same compositions. No scoring policy: no
weights, no normalization, no exclusions.

best-available gap: the experimental median when the composition has one in the expt_gap
snapshot, else the JARVIS TBmBJ gap, else the Materials Project PBE gap, read from the
polymorph used. e_total: the Materials Project DFPT total dielectric constant on that same
polymorph. The polymorph is the one the scorer selects (ground state among MP polymorphs no
adapter rule excludes); when it carries no e_total, the lowest-hull MP polymorph that has one.
A composition without both values is listed as unpaired and left out of rho. Nothing is
filled. Owner request 2026-11-02.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from materials_triage.records import Polymorph
from materials_triage.scoring.polymorphs import mp_polymorphs, select_scored
from validation.groups import LoadedGroup
from validation.spearman import spearman
from validation.yim import YimGroundTruth

COMPUTED_GAP_ORDER = (("tbmbj", "jarvis_tbmbj"), ("pbe", "mp_summary"))
E_TOTAL_KEY = "e_total"

DEFINITION = (
    "Spearman rho between Yim's figure of merit and (best-available gap x e_total) from our "
    "records, no scoring policy. Gap: experimental median (expt_gap snapshot) when present, "
    "else JARVIS TBmBJ, else Materials Project PBE, on the polymorph used. e_total: Materials "
    "Project DFPT total dielectric constant on that polymorph. Polymorph: the scorer's selected "
    "ground state, else the lowest-hull MP polymorph carrying e_total. Compositions without "
    "both values are listed and left out; nothing is filled."
)


@dataclass(frozen=True)
class DataPoint:
    composition: str
    yim_best_fom: float
    gap_ev: float
    gap_source: str  # experimental | tbmbj | pbe
    e_total: float
    mp_id: str | None
    product: float


@dataclass(frozen=True)
class DataLevelTable:
    table: int
    n_in_table: int
    n_paired: int
    rho: float | None
    reason: str | None
    points: list[DataPoint]
    unpaired: list[dict[str, str]]  # composition, missing


@dataclass(frozen=True)
class DataLevelReport:
    definition: str
    tables: list[DataLevelTable]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _e_total(p: Polymorph) -> float | None:
    v = p.dielectric.get(E_TOTAL_KEY)
    return None if v is None else v.value


def _polymorph_with_e_total(lg: LoadedGroup) -> Polymorph | None:
    scored = select_scored(lg.group)
    if scored is not None and _e_total(scored) is not None:
        return scored
    return next((p for p in mp_polymorphs(lg.group) if _e_total(p) is not None), None)


def _gap(lg: LoadedGroup, p: Polymorph) -> tuple[float, str] | None:
    agg = lg.group.experimental_gaps
    if agg is not None:
        return agg.median, "experimental"
    for label, key in COMPUTED_GAP_ORDER:
        v = p.band_gap.get(key)
        if v is not None and v.value is not None:
            return v.value, label
    return None


def data_point(composition: str, fom: float, lg: LoadedGroup) -> DataPoint | dict[str, str]:
    """A point, or the reason there is none."""
    p = _polymorph_with_e_total(lg)
    if p is None:
        first = select_scored(lg.group) or next(iter(mp_polymorphs(lg.group)), None)
        has_gap = first is not None and _gap(lg, first) is not None
        missing = "e_total" if has_gap else "gap and e_total"
        return {"composition": composition, "missing": missing}
    gap = _gap(lg, p)
    if gap is None:
        return {"composition": composition, "missing": "gap"}
    e_total = _e_total(p)
    assert e_total is not None
    return DataPoint(
        composition=composition,
        yim_best_fom=fom,
        gap_ev=gap[0],
        gap_source=gap[1],
        e_total=e_total,
        mp_id=p.ids.mp,
        product=gap[0] * e_total,
    )


def data_level_table(
    groups: dict[str, LoadedGroup], gt: YimGroundTruth, table: int
) -> DataLevelTable:
    order = gt.table_order(table)
    points: list[DataPoint] = []
    unpaired: list[dict[str, str]] = []
    for comp, fom in order:
        lg = groups.get(comp)
        if lg is None:
            unpaired.append({"composition": comp, "missing": "not loaded"})
            continue
        point = data_point(comp, fom, lg)
        if isinstance(point, DataPoint):
            points.append(point)
        else:
            unpaired.append(point)
    res = spearman([p.yim_best_fom for p in points], [p.product for p in points])
    return DataLevelTable(
        table=table,
        n_in_table=len(order),
        n_paired=len(points),
        rho=res.rho,
        reason=res.reason,
        points=points,
        unpaired=unpaired,
    )


def data_level_report(groups: dict[str, LoadedGroup], gt: YimGroundTruth) -> DataLevelReport:
    return DataLevelReport(
        definition=DEFINITION,
        tables=[data_level_table(groups, gt, t) for t in gt.tables()],
    )
