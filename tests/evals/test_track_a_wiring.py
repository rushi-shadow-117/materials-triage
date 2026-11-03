"""Validation against Track A's scorer. Skips on a branch without the scorer."""

from pathlib import Path

import pytest
from validation import track_a
from validation.report import run_validation

pytestmark = pytest.mark.skipif(not track_a.available(), reason="Track A scorer not merged")


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
