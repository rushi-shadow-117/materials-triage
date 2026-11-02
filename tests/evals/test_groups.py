"""Every recorded composition assembles into a group from cassettes with the network off."""

import pytest
from validation.groups import (
    LoadedGroup,
    load_groups,
    load_snapshots,
    no_abstract_compositions,
    recorded_compositions,
)
from validation.yim import load_yim

NO_ABSTRACT_PER_WIRE_FINDINGS = {  # docs/wire-findings.md, Track 0 recordings
    "Ta2Cd2O7",
    "Ta4Ag2O11",
    "LiAlO2",
    "Ba3P4O13",
    "CaB4O7",
    "HfTe3O8",
    "Li3BrO",
    "Li4CO4",
    "Mg4H2O5",
    "Y2Si2O7",
}


@pytest.fixture(scope="module")
def all_groups() -> dict[str, LoadedGroup]:
    return load_groups(snapshots=load_snapshots())


def test_every_recorded_composition_loads_without_network(
    all_groups: dict[str, LoadedGroup],
) -> None:
    assert len(all_groups) == len(recorded_compositions()) == 61
    for key, lg in all_groups.items():
        assert lg.group.composition == key
        assert lg.group.polymorphs, key
        for p in lg.group.polymorphs:
            for v in p.hull_energy.values():
                assert (v.value is None) == (v.missing_reason is not None)


def test_yim_set_is_a_subset_and_has_no_snapshot_gaps_outside_the_oxides(
    all_groups: dict[str, LoadedGroup],
) -> None:
    yim = load_yim()
    assert set(yim.compositions()) <= set(all_groups)
    with_expt = {k for k, g in all_groups.items() if g.group.experimental_gaps is not None}
    assert with_expt <= {"HfO2", "ZrO2", "TiO2", "ThO2", "La2O3", "BaTiO3", "BeO", "Y2O3", "Ta2O5"}


def test_no_abstract_set_matches_the_recording_note(
    all_groups: dict[str, LoadedGroup],
) -> None:
    states = no_abstract_compositions(all_groups)
    assert {k for k, s in states.items() if s == "no_match"} == NO_ABSTRACT_PER_WIRE_FINDINGS
    # Two more compositions matched works that carry no abstract (manifest: LaYO3 2 of 2,
    # NaIO3 3 of 3 without abstract). Same tier, distinct sub-state.
    assert {k for k, s in states.items() if s == "no_abstract"} == {"LaYO3", "NaIO3"}


def test_hazard_is_none_where_no_pubchem_cassette_exists(
    all_groups: dict[str, LoadedGroup],
) -> None:
    assert all_groups["HfO2"].group.hazard is not None
    assert all_groups["HfO2"].group.hazard.cid == 292779
    assert all_groups["NbCl3O"].group.hazard is None
    assert all_groups["TiCdO3"].group.hazard is None


def test_unknown_key_is_an_error_not_a_fetch() -> None:
    with pytest.raises(KeyError, match="NeverRecorded"):
        load_groups(["NeverRecorded"], snapshots=load_snapshots())
