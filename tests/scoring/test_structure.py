"""Molecular solids are excluded by structural dimensionality (Larsen 2019 via pymatgen,
CrystalNN bonds); missing never excludes (Track G item 1)."""

from __future__ import annotations

from materials_triage.adapters import mp
from materials_triage.cli.wiring import CassetteFetch
from materials_triage.records import MissingReason, Value
from materials_triage.records.bundle import ExclusionRule
from materials_triage.records.structure import METHOD, dimensionality_value
from materials_triage.scoring.polymorphs import select_scored
from tests.scoring.conftest import run

FETCH = CassetteFetch()


def _dim(mp_id: str) -> Value[int]:
    [call] = mp.plan_structure([mp_id])
    raw = FETCH(call)
    assert raw is not None, f"no recorded structure for {mp_id}"
    [record] = [r for r in mp.structure_records(raw) if r.source_record_id == mp_id]
    return dimensionality_value(record)


def test_recorded_structures_give_molecular_and_network_dimensionality() -> None:
    co2, h2o, hfo2 = _dim("mp-20066"), _dim("mp-697111"), _dim("mp-352")
    assert (co2.value, h2o.value, hfo2.value) == (0, 0, 3)
    assert co2.method == METHOD and co2.provenance.source_record_id == "mp-20066"
    assert _dim("mp-20066") == co2  # deterministic for the same structure


def test_dimensionality_zero_excludes_after_the_hazard_rules(
    baseline_groups, dielectric_profile, site, policy, references, echa
) -> None:  # type: ignore[no-untyped-def]
    groups = {k: g.model_copy(deep=True) for k, g in baseline_groups.items()}
    for comp in ("HfO2", "ThO2"):
        scored = select_scored(groups[comp])
        assert scored is not None and scored.dimensionality is not None
        scored.dimensionality = scored.dimensionality.model_copy(update={"value": 0})
    r = run(groups, dielectric_profile, site, policy, references, echa)
    hf = next(c for c in r.candidates if c.composition == "HfO2")
    assert hf.rank is None and hf.excluded is not None
    assert hf.excluded.rule is ExclusionRule.STRUCTURE_MOLECULAR
    assert "dimensionality 0 (Larsen 2019, CrystalNN bonds) on mp-352" in hf.excluded.detail
    assert hf.score is not None and hf.score.dimensionality is not None
    th = next(c for c in r.candidates if c.composition == "ThO2")
    assert th.excluded is not None and th.excluded.rule is ExclusionRule.HAZARD_RADIOACTIVE
    log = next(e for e in r.decision_log if e.step == "score")
    assert "structure.molecular" in log.detail["also_excluded_by"]["ThO2"]


def test_missing_dimensionality_never_excludes(
    baseline_groups, dielectric_profile, site, policy, references, echa
) -> None:  # type: ignore[no-untyped-def]
    groups = {k: g.model_copy(deep=True) for k, g in baseline_groups.items()}
    scored = select_scored(groups["HfO2"])
    assert scored is not None and scored.dimensionality is not None
    scored.dimensionality = Value[int](
        value=None,
        unit="1",
        method=METHOD,
        missing_reason=MissingReason.NOT_COMPUTED,
        provenance=scored.dimensionality.provenance,
    )
    groups["ZrO2"] = groups["ZrO2"].model_copy(deep=True)
    zr = select_scored(groups["ZrO2"])
    assert zr is not None
    zr.dimensionality = None
    r = run(groups, dielectric_profile, site, policy, references, echa)
    by = {c.composition: c for c in r.candidates}
    assert by["HfO2"].rank is not None and by["ZrO2"].rank is not None
    assert by["ZrO2"].score is not None
    assert by["ZrO2"].score.dimensionality_note == "structure not fetched (summary-level row)"
    assert by["HfO2"].score is not None and by["HfO2"].score.dimensionality is not None
    assert by["HfO2"].score.dimensionality.missing_reason is MissingReason.NOT_COMPUTED
