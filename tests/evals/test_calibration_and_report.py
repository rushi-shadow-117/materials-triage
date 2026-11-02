"""Band gap calibration on the recorded oxides, and the stand-in validation run end to end."""

import json
from pathlib import Path

import pytest
from validation.calibration import calibrate
from validation.groups import LoadedGroup, Snapshots, load_groups, load_snapshots
from validation.report import run_validation
from validation.stand_in import NOTE, score_stand_in

BASELINE = [
    "HfO2",
    "ZrO2",
    "Al2O3",
    "SiO2",
    "TiO2",
    "ThO2",
    "La2O3",
    "BaTiO3",
    "BeO",
    "Y2O3",
    "Ta2O5",
]


@pytest.fixture(scope="module")
def snapshots() -> Snapshots:
    return load_snapshots()


@pytest.fixture(scope="module")
def baseline(snapshots: Snapshots) -> dict[str, LoadedGroup]:
    return load_groups(BASELINE, snapshots=snapshots)


def test_calibration_pairs_are_listed_with_n_and_mae(
    baseline: dict[str, LoadedGroup], snapshots: Snapshots
) -> None:
    rep = calibrate(baseline, snapshots)
    # Nine oxides carry an experimental median; TBmBJ exists for six of them (sample bundle).
    assert rep.pbe.n == 9 and rep.tbmbj.n == 6
    assert sorted(rep.tbmbj.without_pair) == ["BeO", "La2O3", "Y2O3"]
    for m in (rep.tbmbj, rep.pbe):
        assert m.mae is not None and m.mae == pytest.approx(sum(p.abs_error for p in m.pairs) / m.n)
        for p in m.pairs:
            assert p.abs_error == pytest.approx(abs(p.computed - p.experimental_median))
    assert rep.tbmbj.mae is not None
    assert rep.conflict_tolerance_ev == pytest.approx(round(2 * rep.tbmbj.mae, 3))
    assert len(rep.data_sha256) == 64 and set(rep.snapshot_shas) >= {"jarvis_dft_3d", "expt_gap"}
    tho2 = next(p for p in rep.tbmbj.pairs if p.composition == "ThO2")
    assert tho2.experimental_n == 2  # the owner's conflicting compendium rows stay in, shown


def test_calibration_hash_changes_with_the_data(
    baseline: dict[str, LoadedGroup], snapshots: Snapshots
) -> None:
    full = calibrate(baseline, snapshots)
    fewer = calibrate({k: v for k, v in baseline.items() if k != "HfO2"}, snapshots)
    assert full.data_sha256 != fewer.data_sha256


def test_stand_in_run_is_labeled_and_byte_stable(tmp_path: Path) -> None:
    first = run_validation(score_stand_in, scorer_name="stand_in", out_dir=tmp_path)
    assert first["scorer"]["name"] == "stand_in" and NOTE in first["scorer"]["note"]
    tables = {t["table"]: t for t in first["yim"]["tables"]}
    assert set(tables) == {1, 2, 3}
    for t in tables.values():
        assert t["n_ranked"] + len(t["excluded"]) + len(t["absent"]) == t["n_in_table"]
        assert t["absent"] == []
    negatives = {n["composition"]: n["status"] for n in first["yim"]["negatives"]}
    assert negatives == {
        "BeO": "excluded",
        "TiCdO3": "excluded",
        "Ta2Cd2O7": "excluded",
        "HfPbO3": "excluded",
        "ZrPbO3": "excluded",
    }
    assert {r["composition"] for r in first["yim"]["no_abstract"]} >= {"Li4CO4", "NaIO3", "LaYO3"}
    assert (
        first["recall"]["k"] == 5 and first["negative_controls"]["baseline_oxides"]["all_handled"]
    )
    a = (tmp_path / "validation.json").read_text()
    run_validation(score_stand_in, scorer_name="stand_in", out_dir=tmp_path)
    assert (tmp_path / "validation.json").read_text() == a
    cal = json.loads((tmp_path / "band_gap_calibration.json").read_text())
    assert cal["data_sha256"] == first["calibration_sha256"]
