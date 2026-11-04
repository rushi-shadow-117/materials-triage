"""The fake judge, the owner-grading sample file, the agreement rate, and pre-registration."""

import json
from pathlib import Path

from evals.judge import FakeJudge, agreement_rate, caveat_terms, write_judge_sample
from evals.preregistration import compare, preregister
from evals.schema import JudgeVerdict

from materials_triage.records.bundle import Caveat, CaveatId
from tests.evals.bundles import bundle, candidate


def _bundle():  # type: ignore[no-untyped-def]
    c = candidate("HfO2", 1)
    c.caveats = [
        Caveat(id=CaveatId.BAND_OFFSETS_NOT_CHECKED),
        Caveat(id=CaveatId.HAZARD_UNKNOWN, subject="Hf"),
    ]
    return bundle([c])


def test_fake_judge_gives_reasons() -> None:
    b = _bundle()
    assert caveat_terms(b) == ["band_offsets_not_checked", "hazard_unknown"]
    j = FakeJudge()
    good = "HfO2 leads. Caveat: band offsets not checked; hazard unknown for Hf."
    v = j.judge("caveat_presence", good, b)
    assert v.verdict == "pass" and v.judge == "fake" and "every caveat" in v.reason
    v = j.judge("caveat_presence", "HfO2 leads. Caveat: band offsets not checked.", b)
    assert v.verdict == "fail" and "hazard_unknown" in v.reason
    v = j.judge("pi_summary_level", good, b)
    assert v.verdict == "pass"
    v = j.judge("pi_summary_level", "HfO2 (mp-352) " + "word " * 100, b)
    assert v.verdict == "fail" and "record ids" in v.reason


def test_judge_sample_round_trips_to_an_agreement_rate(tmp_path: Path) -> None:
    rows = [
        (
            "A1",
            1,
            JudgeVerdict(item="caveat_presence", verdict="pass", reason="ok | fine", judge="fake"),
        ),
        (
            "A1",
            1,
            JudgeVerdict(item="pi_summary_level", verdict="fail", reason="long", judge="fake"),
        ),
        (
            "A2",
            1,
            JudgeVerdict(item="caveat_presence", verdict="judge_declined", reason="x", judge="m"),
        ),
    ]
    path = tmp_path / "judge_sample.md"
    write_judge_sample(rows, path)
    assert agreement_rate(path) == {"rows": 3, "graded": 0, "agreed": 0, "agreement_rate": None}
    text = (
        path.read_text()
        .replace("| ok / fine |  |", "| ok / fine | pass |")
        .replace("| long |  |", "| long | pass |")
    )
    path.write_text(text)
    assert agreement_rate(path) == {"rows": 3, "graded": 2, "agreed": 1, "agreement_rate": 0.5}


def test_preregistration_records_and_compares(tmp_path: Path) -> None:
    path = tmp_path / "prereg.json"
    assert compare(path) is None
    rec = preregister(path, scorer_name="track_a")
    [data] = json.loads(path.read_text())["entries"]
    assert data["config_sha"] == rec["config_sha"] and len(data["config_sha"]) == 64
    assert set(data["snapshot_shas"]) >= {"jarvis_dft_3d", "expt_gap"}
    cmp = compare(path)
    assert cmp is not None and cmp["config_tuned_after_preregistration"] is False
    assert cmp["data_unchanged"] is True and cmp["config_files_changed"] == []
    data["config_sha"] = "0" * 64
    data["config_files"]["hazard_policy.yaml"] = "tampered"
    path.write_text(json.dumps(data))  # a pre-entries file: one bare record
    cmp = compare(path)
    assert cmp is not None and cmp["config_tuned_after_preregistration"] is True
    assert cmp["config_files_changed"] == ["hazard_policy.yaml"]
    assert [h["label"] for h in cmp["history"]] == ["initial (Track E)"]
    # a second entry keeps the first and becomes the comparison baseline
    preregister(path, scorer_name="track_a", label="owner decision after Track G")
    cmp = compare(path)
    assert cmp is not None and cmp["config_tuned_after_preregistration"] is False
    assert [h["label"] for h in cmp["history"]] == [
        "initial (Track E)",
        "owner decision after Track G",
    ]
    assert cmp["history"][0]["config_sha"] == "0" * 64
