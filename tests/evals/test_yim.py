"""The Yim fixture loads, collapses polymorphs by the owner's rule, and carries its erratum."""

from pathlib import Path

import yaml
from validation.yim import DEFAULT_PATH, load_yim

RAW = yaml.safe_load(Path(DEFAULT_PATH).read_text())


def test_no_gap_duplicates_the_space_group() -> None:
    """Guard for the 2026-11-02 erratum: Tables 2 and 3 had the space group in the gap column."""
    for row in RAW["positives"]:
        gap, sg = row.get("band_gap_ev"), row.get("spacegroup_number")
        if gap is not None and sg is not None:
            assert str(gap) != str(sg), row
    assert any(e["affects"].startswith("band_gap_ev") for e in RAW["data_errata"])


def test_table_one_gaps_are_present_and_plausible() -> None:
    for row in RAW["positives"]:
        if row["table"] == 1:
            assert row["band_gap_ev"] is not None
            assert 0.0 < float(row["band_gap_ev"]) < 15.0, row


def test_loader_reduces_formulas_and_keeps_phase_prefix() -> None:
    gt = load_yim()
    assert len(gt.rows) == len(RAW["positives"]) == 74
    assert len(gt.compositions()) == 46
    c_beo = [r for r in gt.rows if r.name_as_printed == "c-BeO"]
    assert c_beo and c_beo[0].composition == "BeO" and c_beo[0].phase_prefix == "c"
    assert {r.composition for r in gt.rows if r.formula == "AlO(OH)"} == {"AlHO2"}
    assert gt.negatives == ("BeO", "TiCdO3", "Ta2Cd2O7", "HfPbO3", "ZrPbO3")
    assert gt.tables() == [1, 2, 3]
    assert gt.doi == "10.1038/am.2015.57" and len(gt.fixture_sha256) == 64


def test_table_order_takes_the_best_fom_per_composition() -> None:
    gt = load_yim()
    t2 = dict(gt.table_order(2))
    # NbOCl3 appears twice in Table 2 (1176 and 815); the best polymorph represents it.
    assert t2["NbCl3O"] == 1176.0
    assert gt.table_order(2)[0] == ("BeO", 2780.0)
    for table in gt.tables():
        order = gt.table_order(table)
        foms = [f for _, f in order]
        assert foms == sorted(foms, reverse=True)
        assert len({c for c, _ in order}) == len(order)
    assert len(gt.table_order(1)) == 11
    assert len(gt.table_order(2)) == 24
    assert len(gt.table_order(3)) == 23
