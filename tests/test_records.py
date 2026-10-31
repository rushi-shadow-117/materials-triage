from datetime import UTC, datetime

import pytest

from materials_triage.records import Ids, MissingReason, Polymorph, Provenance, Value
from materials_triage.records.matching import match_polymorphs

PROV = Provenance(
    source="materials_project",
    source_record_id="mp-1",
    raw_response_id=None,
    raw_sha256="0" * 64,
    fetched_at=datetime.now(UTC),
)


def test_zero_is_a_value_not_missing() -> None:
    v = Value[float](value=0.0, unit="eV/atom", method="GGA_GGA+U_R2SCAN", provenance=PROV)
    assert v.value == 0.0 and v.value is not None and v.missing_reason is None


def test_missing_needs_a_reason_and_present_cannot_have_one() -> None:
    with pytest.raises(ValueError):
        Value[float](value=None, unit="eV", provenance=PROV)
    with pytest.raises(ValueError):
        Value[float](value=1.0, unit="eV", missing_reason=MissingReason.ABSENT, provenance=PROV)
    v = Value[float](
        value=None, unit="eV", missing_reason=MissingReason.NA_SENTINEL, provenance=PROV
    )
    assert v.value is None


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValueError):
        Polymorph(
            composition="HfO2",
            spacegroup_number=14,
            spacegroup_symbol="P2_1/c",
            ids=Ids(),
            observed=None,
            bogus=1,
        )  # type: ignore[call-arg]


def _poly(
    comp: str, spg: int | None, icsd: list[int], mp: str | None = None, jid: str | None = None
) -> Polymorph:
    return Polymorph(
        composition=comp,
        spacegroup_number=spg,
        spacegroup_symbol=None,
        ids=Ids(mp=mp, jarvis_jid=jid, icsd=icsd),
        observed=None,
    )


def test_icsd_match_wins_over_spacegroup() -> None:
    mp = [
        _poly("ThO2", 225, [61586, 236586], mp="mp-643"),
        _poly("ThO2", 62, [246705], mp="mp-1102569"),
    ]
    jarvis = [
        _poly("ThO2", 62, [], jid="JVASP-153820"),
        _poly("ThO2", 225, [647528, 61586], jid="JVASP-1169"),
    ]
    matches = match_polymorphs(mp, jarvis)
    rules = {(m.left.ids.mp, m.right.ids.jarvis_jid): m.rule.value for m in matches}
    assert rules[("mp-643", "JVASP-1169")] == "icsd_intersection"
    assert rules[("mp-1102569", "JVASP-153820")] == "composition_spacegroup"


def test_no_match_without_spacegroup_or_icsd() -> None:
    assert match_polymorphs([_poly("HfO2", None, [])], [_poly("HfO2", 14, [])]) == []
