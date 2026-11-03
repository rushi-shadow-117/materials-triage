"""The data-level Yim correlation: gap x e_total from the records, no scoring policy."""

from __future__ import annotations

import pytest
from validation.data_level import DataPoint, data_level_report, data_point
from validation.groups import LoadedGroup, load_groups, load_snapshots
from validation.yim import load_yim

from materials_triage.scoring.polymorphs import select_scored


@pytest.fixture(scope="module")
def yim_groups() -> dict[str, LoadedGroup]:
    gt = load_yim()
    return load_groups(gt.compositions(), snapshots=load_snapshots())


def test_every_table_row_is_paired_or_listed(yim_groups: dict[str, LoadedGroup]) -> None:
    gt = load_yim()
    rep = data_level_report(yim_groups, gt)
    assert {t.table for t in rep.tables} == {1, 2, 3}
    assert "no scoring policy" in rep.definition
    for t in rep.tables:
        assert t.n_paired + len(t.unpaired) == t.n_in_table
        assert t.n_paired == len(t.points)
        assert t.rho is None or -1.0 <= t.rho <= 1.0
        for p in t.points:
            assert p.product == pytest.approx(p.gap_ev * p.e_total)
            assert p.gap_source in ("experimental", "tbmbj", "pbe")
            assert p.mp_id is not None
        for u in t.unpaired:
            assert u["missing"] in ("e_total", "gap", "gap and e_total", "not loaded")
    # Yim's compositions carry MP DFPT data for most entries; the metric is not vacuous.
    assert sum(t.n_paired for t in rep.tables) >= 20


def test_point_takes_the_recorded_values_without_policy(
    yim_groups: dict[str, LoadedGroup],
) -> None:
    baseline = load_groups(["HfO2"], snapshots=load_snapshots())
    lg = baseline["HfO2"]
    point = data_point("HfO2", 1.0, lg)
    assert isinstance(point, DataPoint)
    agg = lg.group.experimental_gaps
    assert agg is not None and point.gap_ev == agg.median and point.gap_source == "experimental"
    scored = select_scored(lg.group)
    assert scored is not None
    e_total = scored.dielectric["e_total"].value
    assert e_total is not None and point.e_total == e_total and point.mp_id == scored.ids.mp
    # A composition outside the expt_gap snapshot falls back to a computed gap, in order.
    computed = [
        p
        for t in data_level_report(yim_groups, load_yim()).tables
        for p in t.points
        if p.gap_source != "experimental"
    ]
    assert computed, "no Yim composition used a computed gap"
    for p in computed:
        poly = next(q for q in yim_groups[p.composition].group.polymorphs if q.ids.mp == p.mp_id)
        key = "jarvis_tbmbj" if p.gap_source == "tbmbj" else "mp_summary"
        assert poly.band_gap[key].value == p.gap_ev
        if p.gap_source == "pbe":
            tb = poly.band_gap.get("jarvis_tbmbj")
            assert tb is None or tb.value is None
