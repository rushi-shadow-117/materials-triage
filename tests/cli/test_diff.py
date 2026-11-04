"""Rank changes are attributed to every applicable cause, in a fixed order."""

from __future__ import annotations

from pathlib import Path

import pytest

from materials_triage.cli import rundiff as d
from materials_triage.records.bundle import (
    EvidenceHit,
    EvidenceLabel,
    Exclusion,
    ExclusionRule,
    ProvenanceBundle,
)

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "fixtures" / "bundles" / "sample_bundle.json"


@pytest.fixture
def a() -> ProvenanceBundle:
    return ProvenanceBundle.model_validate_json(SAMPLE.read_text())


def _swap(bundle: ProvenanceBundle, x: str, y: str) -> ProvenanceBundle:
    b = bundle.model_copy(deep=True)
    rx = next(c for c in b.candidates if c.composition == x)
    ry = next(c for c in b.candidates if c.composition == y)
    rx.rank, ry.rank = ry.rank, rx.rank
    return b


def test_identical_runs_have_no_changes(a: ProvenanceBundle) -> None:
    report = d.diff(a, a)
    assert report.changes == [] and report.unchanged == len(a.candidates)
    assert "0 composition(s) changed" in d.to_markdown(report)


def test_config_change_is_named_with_the_setting_that_differs(a: ProvenanceBundle) -> None:
    b = _swap(a, "Al2O3", "HfO2")
    b.run.config_sha = "other"
    b.criteria.effective_settings = {**b.criteria.effective_settings, "weights": {"band_gap": 2.0}}
    report = d.diff(a, b)
    by = {c.composition: c for c in report.changes}
    assert set(by) == {"Al2O3", "HfO2"}
    assert (
        by["HfO2"].causes == ["config"]
        and "weights: {} -> {'band_gap': 2.0}" in by["HfO2"].detail[0]
    )
    assert by["HfO2"].rank_a == 2 and by["HfO2"].rank_b == 1 and by["HfO2"].delta == "-1"


def test_model_change_is_causal_only_through_labels(a: ProvenanceBundle) -> None:
    b = _swap(a, "Al2O3", "HfO2")
    b.run.model_version = "other-model"
    report = d.diff(a, b)
    by = {c.composition: c for c in report.changes}
    assert by["HfO2"].causes == ["unattributed"]
    assert "model changed, no label change (not causal)" in by["HfO2"].detail
    hit = a.evidence[0]
    b.evidence.append(
        hit.model_copy(update={"composition": "Al2O3", "label": EvidenceLabel.BULK_SYNTHESIZED})
    )
    report = d.diff(a, b)
    by = {c.composition: c for c in report.changes}
    assert by["Al2O3"].causes == ["model"] and "evidence labels" in by["Al2O3"].detail[0]


def test_data_change_is_a_record_hash_difference(a: ProvenanceBundle) -> None:
    b = _swap(a, "Al2O3", "HfO2")
    hf = next(c for c in b.candidates if c.composition == "HfO2")
    assert hf.group.hazard is not None
    hf.group.hazard.provenance.raw_sha256 = "deadbeef"
    report = d.diff(a, b)
    by = {c.composition: c for c in report.changes}
    assert by["HfO2"].causes == ["data"]
    assert by["Al2O3"].causes == ["displaced"] and by["Al2O3"].detail == [
        "displaced_by HfO2 (data)"
    ]


def test_candidate_set_and_exclusion_transitions(a: ProvenanceBundle) -> None:
    b = a.model_copy(deep=True)
    b.candidates = [c for c in b.candidates if c.composition != "Al2O3"]
    for c in b.candidates:
        if c.rank is not None:
            c.rank -= 1
    zr = next(c for c in b.candidates if c.composition == "ZrO2")
    zr.rank = None
    zr.excluded = Exclusion(rule=ExclusionRule.STABILITY_CUTOFF, detail="x")
    report = d.diff(a, b)
    by = {c.composition: c for c in report.changes}
    assert by["Al2O3"].causes == ["candidate_set"] and by["Al2O3"].rank_b is None
    assert by["ZrO2"].excluded_b == "stability.cutoff" and by["ZrO2"].delta == "n/a"
    assert by["HfO2"].causes == ["displaced"]
    text = d.to_markdown(report)
    assert "| Al2O3 | 1 | absent | n/a | candidate_set |" in text
    assert "| ZrO2 | 5 | stability.cutoff | n/a |" in text
    assert "Anchors:" in text and (
        "SiO2: would place 1st of 9, above Al2O3 -> would place 1st of 9, above Al2O3" in text
    )


def test_hazard_policy_edit_counts_as_config(a: ProvenanceBundle) -> None:
    b = _swap(a, "Al2O3", "HfO2")
    b.run.policy_version = "abc123"
    report = d.diff(a, b)
    by = {c.composition: c for c in report.changes}
    assert by["HfO2"].causes == ["config"] and "policy_version: 0 -> abc123" in by["HfO2"].detail[0]
    assert isinstance(EvidenceHit, type)


def test_cross_checks_fetched_in_one_run_follow_the_config_change(a: ProvenanceBundle) -> None:
    """Enrichment follows rank, so a config change can fetch a row's literature in one run
    only. That is not a data change: no record present in both runs differs."""
    b = _swap(a, "HfO2", "ZrO2")
    b.run.config_sha = "different"
    hf = next(c for c in b.candidates if c.composition == "HfO2")
    hf.group = hf.group.model_copy(update={"literature": None})
    by = {c.composition: c for c in d.diff(a, b).changes}
    assert by["HfO2"].causes == ["config"]
    assert any("enrichment follows rank" in x for x in by["HfO2"].detail)
    same_config = _swap(a, "HfO2", "ZrO2")
    same_config.candidates = [
        c.model_copy(update={"group": c.group.model_copy(update={"literature": None})})
        if c.composition == "HfO2"
        else c
        for c in same_config.candidates
    ]
    by = {c.composition: c for c in d.diff(a, same_config).changes}
    assert "data" in by["HfO2"].causes
