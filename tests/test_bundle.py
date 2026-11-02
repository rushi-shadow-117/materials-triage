from datetime import UTC, datetime
from uuid import uuid4

import pytest

from materials_triage.records import Ids, Polymorph, Provenance, Value
from materials_triage.records.bundle import (
    BUNDLE_VERSION,
    Candidate,
    ConfirmedCriteria,
    CriterionScore,
    Exclusion,
    FetchMode,
    ProvenanceBundle,
    RunMetadata,
    ScoreBreakdown,
)
from materials_triage.records.groups import build_group


def _prov(mp_id: str) -> Provenance:
    return Provenance(
        source="materials_project",
        source_record_id=mp_id,
        raw_response_id=None,
        raw_sha256="b" * 64,
        fetched_at=datetime.now(UTC),
    )


def _poly(mp_id: str, comp: str, hull: float) -> Polymorph:
    p = _prov(mp_id)
    return Polymorph(
        composition=comp,
        spacegroup_number=225,
        spacegroup_symbol="Fm-3m",
        ids=Ids(mp=mp_id),
        observed=True,
        theoretical=False,
        hull_energy={"GGA_GGA+U_R2SCAN": Value[float](value=hull, unit="eV/atom", provenance=p)},
        provenance=[p],
    )


def _run() -> RunMetadata:
    return RunMetadata(
        run_id=uuid4(),
        started_at=datetime.now(UTC),
        finished_at=None,
        config_sha="c" * 64,
        profile_name="gate_dielectric_on_si",
        profile_version="0",
        policy_version="0",
        prompt_hash=None,
        model_version=None,
        provider=None,
        source_versions={"materials_project": "2026.09.28"},
        fetch_mode=FetchMode.REPLAY,
        partial=False,
    )


def test_minimal_bundle_round_trips_and_ranks() -> None:
    hfo2 = build_group("HfO2", [_poly("mp-352", "HfO2", 0.0)])
    tho2 = build_group("ThO2", [_poly("mp-643", "ThO2", 0.0)])
    score = ScoreBreakdown(
        total=0.8,
        criteria=[
            CriterionScore(
                criterion="stability",
                raw_value=0.0,
                raw_unit="eV/atom",
                source="GGA_GGA+U_R2SCAN",
                normalized=1.0,
                weight=1.0,
                contribution=1.0,
                missing=False,
            )
        ],
        band_gap_source="tbmbj",
    )
    bundle = ProvenanceBundle(
        run=_run(),
        criteria=ConfirmedCriteria(
            request_text="oxide dielectrics",
            parsed_by="criteria_file",
            confirmed_at=None,
            mode="candidate_list",
            candidate_list=["HfO2", "ThO2"],
            effective_settings={},
        ),
        candidates=[
            Candidate(composition="HfO2", group=hfo2, score=score, rank=1, excluded=None),
            Candidate(
                composition="ThO2",
                group=tho2,
                score=None,
                rank=None,
                excluded=Exclusion(
                    rule="hazard.radioactive",
                    detail="Th has no stable isotope",
                    source_ref="config/hazard_policy.yaml#radioactive_exclude",
                ),
            ),
        ],
    )
    text = bundle.model_dump_json()
    back = ProvenanceBundle.model_validate_json(text)
    assert back.bundle_version == BUNDLE_VERSION
    assert [c.composition for c in back.ranked()] == ["HfO2"]
    assert [c.composition for c in back.excluded()] == ["ThO2"]
    assert back.candidates[0].group.polymorphs[0].hull_energy["GGA_GGA+U_R2SCAN"].value == 0.0


def test_unknown_fields_rejected_everywhere() -> None:
    with pytest.raises(ValueError):
        RunMetadata(**{**_run().model_dump(), "extra_field": 1})  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        Exclusion(rule="x", detail="y", why="z")  # type: ignore[call-arg]
