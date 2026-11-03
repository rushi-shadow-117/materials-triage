"""The data-level Yim correlation: rows paired by structure, PBE gap x e_total from the
records, experimental median as a separate column, no scoring policy."""

from __future__ import annotations

import pytest
from validation.data_level import (
    RowPoint,
    UnpairedRow,
    data_level_report,
    match_polymorph,
    row_point,
)
from validation.groups import LoadedGroup, load_groups, load_snapshots
from validation.yim import YimRow, load_yim

from materials_triage.scoring.polymorphs import mp_polymorphs


@pytest.fixture(scope="module")
def yim_groups() -> dict[str, LoadedGroup]:
    gt = load_yim()
    return load_groups(gt.compositions(), snapshots=load_snapshots())


def test_every_row_is_paired_by_structure_or_listed(yim_groups: dict[str, LoadedGroup]) -> None:
    gt = load_yim()
    rep = data_level_report(yim_groups, gt)
    assert {t.table for t in rep.tables} == {1, 2, 3}
    assert "paired by structure" in rep.definition and "no scoring policy" in rep.definition
    for t in rep.tables:
        assert t.n_rows == sum(1 for r in gt.rows if r.table == t.table)
        assert t.n_paired + len(t.unpaired) == t.n_rows and t.n_paired == len(t.points)
        assert t.n_experimental == sum(1 for p in t.points if p.experimental_product is not None)
        for rho in (t.rho_pbe, t.rho_experimental):
            assert rho is None or -1.0 <= rho <= 1.0
        for p in t.points:
            assert p.match in ("icsd", "composition_spacegroup")
            assert p.product == pytest.approx(p.pbe_gap_ev * p.e_total)
            poly = next(
                q for q in yim_groups[p.composition].group.polymorphs if q.ids.mp == p.mp_id
            )
            assert poly.band_gap["mp_summary"].value == p.pbe_gap_ev
            assert poly.dielectric["e_total"].value == p.e_total
            if p.match == "icsd":
                assert int(p.icsd) in poly.ids.icsd
            else:
                assert poly.spacegroup_number == p.yim_spacegroup
            agg = yim_groups[p.composition].group.experimental_gaps
            assert p.experimental_median_ev == (None if agg is None else agg.median)
        for u in t.unpaired:
            assert u.reason
    paired = sum(t.n_paired for t in rep.tables)
    by_icsd = sum(1 for t in rep.tables for p in t.points if p.match == "icsd")
    assert paired >= 20 and by_icsd >= 1, (paired, by_icsd)


def test_match_order_icsd_then_composition_spacegroup(yim_groups: dict[str, LoadedGroup]) -> None:
    lg = yim_groups["BeO"]
    polys = mp_polymorphs(lg.group)
    with_icsd = next(p for p in polys if p.ids.icsd)
    row = YimRow(
        name_as_printed="x",
        formula="BeO",
        composition="BeO",
        phase_prefix=None,
        icsd=str(with_icsd.ids.icsd[0]),
        spacegroup_number=None,
        kappa=1.0,
        band_gap_ev=None,
        f_fom=1.0,
        table=1,
    )
    p, how = match_polymorph(row, lg)
    assert p is with_icsd and how == "icsd"
    no_icsd = YimRow(
        **{**row.__dict__, "icsd": "0", "spacegroup_number": with_icsd.spacegroup_number}
    )
    p, how = match_polymorph(no_icsd, lg)
    assert p is not None and how == "composition_spacegroup"
    assert p.spacegroup_number == with_icsd.spacegroup_number
    nothing = YimRow(**{**row.__dict__, "icsd": "0", "spacegroup_number": None})
    p, how = match_polymorph(nothing, lg)
    assert p is None and "no space group" in how
    assert isinstance(row_point(nothing, lg), UnpairedRow)
    assert isinstance(row_point(nothing, None), UnpairedRow)
    assert row_point(nothing, None).reason == "composition not loaded"
    point = row_point(row, lg)
    if isinstance(point, RowPoint):
        assert point.mp_id == with_icsd.ids.mp
    else:
        assert point.mp_id == with_icsd.ids.mp and "missing" in point.reason
