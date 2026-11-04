"""Validation against Track A's scorer on the merged main."""

from pathlib import Path

from validation import track_a
from validation.groups import load_groups
from validation.report import YimLikeRun, run_validation

from materials_triage.config import schema as cs
from materials_triage.config.schema import default_paths


def test_track_a_validation_run_is_labeled_and_byte_stable(tmp_path: Path) -> None:
    first = run_validation(track_a.score_with_track_a, scorer_name="track_a", out_dir=tmp_path)
    assert first["scorer"]["name"] == "track_a"
    assert "Track A scorer" in first["scorer"]["note"]
    tables = {t["table"]: t for t in first["yim"]["tables"]}
    assert set(tables) == {1, 2, 3}
    for t in tables.values():
        assert t["n_ranked"] + len(t["excluded"]) + len(t["absent"]) == t["n_in_table"]
        assert t["absent"] == []
    for n in first["yim"]["negatives"]:
        assert n["status"] in ("excluded", "flagged"), n
    assert first["negative_controls"]["yim_set"]["all_handled"] is True
    assert first["negative_controls"]["baseline_oxides"]["all_handled"] is True
    text = (tmp_path / "validation.json").read_text()
    run_validation(track_a.score_with_track_a, scorer_name="track_a", out_dir=tmp_path)
    assert (tmp_path / "validation.json").read_text() == text


def test_yim_like_run_reports_beside_the_default_without_changing_the_profile(
    tmp_path: Path,
) -> None:
    like = YimLikeRun(
        score=track_a.score_with_track_a_yim_like, description=track_a.yim_like_description()
    )
    report = run_validation(
        track_a.score_with_track_a, scorer_name="track_a", out_dir=tmp_path, yim_like=like
    )
    block = report["yim_like"]
    assert block["weights"] == track_a.YIM_LIKE_WEIGHTS
    assert block["label"].startswith("Yim-like configuration")
    assert block["config_sha"] != report["scorer"]["config_sha"]
    assert {t["table"] for t in block["tables"]} == {1, 2, 3}
    default_tables = {t["table"]: t for t in report["yim"]["tables"]}
    for t in block["tables"]:
        assert t["n_in_table"] == default_tables[t["table"]]["n_in_table"]
        assert t["n_ranked"] + len(t["excluded"]) + len(t["absent"]) == t["n_in_table"]
    # The profile file on disk is what both runs load; only the query weights differ.
    data = cs.load_yaml(default_paths()["scoring_profile"])
    assert data["weights"]["values"]["dielectric_constant"] == 0.0
    assert data["weights"]["values"]["evidence"] == 1.0

    # In the Yim-like bundle the dielectric criterion carries weight and, where MP has a DFPT
    # value, contributes; evidence carries none and hazard sits at the site floor.
    groups = load_groups(["HfO2", "ZrO2", "Al2O3"])
    default = track_a.score_with_track_a(groups)
    yim_like = track_a.score_with_track_a_yim_like(groups)
    assert default.criteria.effective_settings["weights"] == {}
    assert yim_like.criteria.effective_settings["effective_weights"] == track_a.YIM_LIKE_WEIGHTS
    assert yim_like.run.run_id != default.run.run_id
    assert "YIM-LIKE" in yim_like.run.note and "YIM-LIKE" not in default.run.note
    by_criterion = {
        c.criterion: c for cand in yim_like.candidates if cand.score for c in cand.score.criteria
    }
    assert by_criterion["dielectric_constant"].weight == 1.0
    assert by_criterion["evidence"].weight == 0.0
    assert by_criterion["hazard"].weight == 0.1
    contributing = [
        c
        for cand in yim_like.candidates
        if cand.score
        for c in cand.score.criteria
        if c.criterion == "dielectric_constant" and not c.missing
    ]
    if track_a.yim_like_target_band()[0] is not None:
        assert contributing, "no candidate's dielectric constant contributed"
        assert all(c.normalized is not None for c in contributing)
