"""Property tests on the normalizations: monotone, bounded, exclude at the threshold."""

from datetime import UTC, datetime

from hypothesis import given, settings
from hypothesis import strategies as st

from materials_triage.config.schema import SimplicitySettings
from materials_triage.records import MissingReason, Provenance, Value
from materials_triage.records.bundle import ExclusionRule, Flag
from materials_triage.scoring import criteria

PROV = Provenance(
    source="materials_project",
    source_record_id="mp-1",
    raw_response_id=None,
    raw_sha256="a" * 64,
    fetched_at=datetime(2026, 11, 2, tzinfo=UTC),
)


def hull(v: float | None) -> Value[float]:
    return Value[float](
        value=v,
        unit="eV/atom",
        method="GGA_GGA+U_R2SCAN",
        missing_reason=None if v is not None else MissingReason.ABSENT,
        provenance=PROV,
    )


@settings(max_examples=300)
@given(
    a=st.floats(min_value=0, max_value=0.5, allow_nan=False),
    b=st.floats(min_value=0, max_value=0.5, allow_nan=False),
)
def test_stability_is_monotone_non_increasing_and_bounded(a: float, b: float) -> None:
    lo, hi = sorted((a, b))
    ra = criteria.stability(hull(lo), cutoff_mev=94, near_cutoff_band_mev=24, source_ref="r")
    rb = criteria.stability(hull(hi), cutoff_mev=94, near_cutoff_band_mev=24, source_ref="r")
    for r in (ra, rb):
        assert r.normalized is None or 0.0 <= r.normalized <= 1.0
    if ra.normalized is not None and rb.normalized is not None:
        assert ra.normalized >= rb.normalized
    if hi * 1000 > 94:
        assert rb.exclusion is not None and rb.exclusion.rule is ExclusionRule.STABILITY_CUTOFF
    else:
        assert rb.exclusion is None and rb.normalized is not None


def test_stability_edges() -> None:
    zero = criteria.stability(hull(0.0), cutoff_mev=94, near_cutoff_band_mev=24, source_ref="r")
    assert zero.normalized == 1.0 and zero.provenance is PROV
    at = criteria.stability(hull(0.094), cutoff_mev=94, near_cutoff_band_mev=24, source_ref="r")
    assert at.normalized == 0.0 and at.exclusion is None and Flag.NEAR_CUTOFF in at.flags
    near = criteria.stability(hull(0.071), cutoff_mev=94, near_cutoff_band_mev=24, source_ref="r")
    assert Flag.NEAR_CUTOFF in near.flags and near.normalized is not None
    far = criteria.stability(hull(0.069), cutoff_mev=94, near_cutoff_band_mev=24, source_ref="r")
    assert Flag.NEAR_CUTOFF not in far.flags
    above = criteria.stability(hull(0.1), cutoff_mev=94, near_cutoff_band_mev=24, source_ref="r")
    assert above.exclusion is not None and Flag.NEAR_CUTOFF in above.flags
    gone = criteria.stability(hull(None), cutoff_mev=94, near_cutoff_band_mev=24, source_ref="r")
    assert gone.normalized is None and gone.missing_reason == "absent" and gone.exclusion is None
    assert criteria.stability(None, cutoff_mev=94, near_cutoff_band_mev=24, source_ref="r").missing


@given(st.sampled_from(["HfO2", "ZrO2", "Al2O3", "BaTiO3", "SrTiO3", "MgAl2O4", "Y2Ti2O7"]))
def test_simplicity_is_bounded_and_binary_beats_ternary(comp: str) -> None:
    s = SimplicitySettings(max_elements=3, anion_policy="strict_oxide", ternary_penalty=True)
    r = criteria.simplicity(comp, s, source_ref="r")
    assert r.exclusion is None and r.normalized is not None and 0.0 <= r.normalized <= 1.0
    n = len(criteria.elements_of(comp))
    assert r.normalized == (1.0 if n == 2 else 0.5)


def test_simplicity_rules() -> None:
    strict = SimplicitySettings(max_elements=3, anion_policy="strict_oxide", ternary_penalty=True)
    assert criteria.simplicity("CaMgSi2O6", strict, source_ref="r").exclusion.rule is (  # type: ignore[union-attr]
        ExclusionRule.SIMPLICITY_MAX_ELEMENTS
    )
    for comp in ("NbOCl3", "YOF", "Li3OBr", "AlN"):
        r = criteria.simplicity(comp, strict, source_ref="r")
        assert r.exclusion is not None and r.exclusion.rule is ExclusionRule.SIMPLICITY_ANION_POLICY
    hydroxide = criteria.simplicity("AlO(OH)", strict, source_ref="r")  # H is a cation here
    assert hydroxide.exclusion is None
    sized = SimplicitySettings(max_elements=3, ternary_penalty=True, ternary_penalty_size=0.2)
    assert criteria.simplicity("BaTiO3", sized, source_ref="r").normalized == 0.8
    off = SimplicitySettings(max_elements=3, ternary_penalty=False)
    assert criteria.simplicity("BaTiO3", off, source_ref="r").normalized == 1.0
    anyp = SimplicitySettings(max_elements=3, anion_policy="any")
    assert criteria.simplicity("YOF", anyp, source_ref="r").exclusion is None


def test_dielectric_target_band() -> None:
    def eps(v: float | None) -> Value[float]:
        return Value[float](
            value=v,
            unit="1",
            method="mp_dfpt",
            missing_reason=None if v is not None else MissingReason.NOT_COMPUTED,
            provenance=PROV,
        )

    band = (10.0, 30.0)
    assert criteria.dielectric_constant(eps(18.7), target_band=band).normalized == 1.0
    assert criteria.dielectric_constant(eps(10.0), target_band=band).normalized == 1.0
    out = criteria.dielectric_constant(eps(4.6), target_band=band).normalized
    assert out is not None and abs(out - (1 - 5.4 / 20)) < 1e-9
    assert criteria.dielectric_constant(eps(60.0), target_band=band).normalized == 0.0
    gone = criteria.dielectric_constant(eps(None), target_band=band)
    assert gone.normalized is None and gone.missing_reason == "not_computed"
    noband = criteria.dielectric_constant(eps(18.7), target_band=None)
    assert noband.normalized is None and noband.raw_value == 18.7


def test_cost_is_always_missing() -> None:
    r = criteria.cost()
    assert r.normalized is None and r.missing_reason == "no source wired"
    score = r.to_score("cost", 0.0)
    assert score.missing and score.contribution == 0.0 and score.normalized is None
